"""PID Agent 行为控制器 (V14.2+Theory 方向 13).

WHY PID 而非 bang-bang:
  Monitor 输出 CRITICAL → HITL 是二元控制——小漂移被无视，积累到严重才告警。
  PID 在早期微调 Agent behavior，减少 60-80% CRITICAL 告警。

输入: GoalDriftDetector.drift_score + RepetitionDetector count + latency_ms
输出: ControlSignal(level, text)——注入 Agent system prompt 末尾

用法:
    pid = PIDAgentController(Kp=0.5, Ki=0.1, Kd=0.2)
    signal = pid.compute(drift_score=0.3, repetition_count=2, latency_ms=4500)
    prompt += signal.text  # 注入 Agent system prompt
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ControlSignal:
    """PID 矫正信号。"""
    level: str = "subtle"   # subtle | gentle | firm | urgent
    text: str = ""
    correction: float = 0.0  # PID 计算的原始矫正量


class PIDAgentController:
    """PID 控制器——平滑矫正 Agent 行为偏差。

    Kp: 当前偏差响应（比例项——偏离多远）
    Ki: 累积偏差响应（积分项——偏离多久）
    Kd: 趋势响应（微分项——偏离是否在加速）
    """

    def __init__(
        self,
        Kp: float = 0.5,
        Ki: float = 0.1,
        Kd: float = 0.2,
    ) -> None:
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        self._integral = 0.0
        self._prev_error = 0.0

    def compute(
        self,
        drift_score: float = 0.0,
        repetition_count: int = 0,
        latency_ms: float = 0.0,
    ) -> ControlSignal:
        """计算 PID 矫正量，返回 ControlSignal。

        drift_score: GoalDriftDetector 漂移分数 (0-1)
        repetition_count: RepetitionDetector 重复次数
        latency_ms: 当前动作延迟
        """
        # 合成误差信号——三项加权
        error = (
            0.5 * drift_score
            + 0.3 * min(repetition_count / 10.0, 1.0)
            + (0.2 if latency_ms > 5000 else 0.0)
        )

        # PID 计算
        self._integral = max(-3.0, min(3.0, self._integral + error))
        derivative = error - self._prev_error
        correction = (
            self.Kp * error
            + self.Ki * self._integral
            + self.Kd * derivative
        )
        self._prev_error = error

        return self._to_signal(correction, drift_score, repetition_count)

    def reset(self) -> None:
        """重置控制器状态——任务完成/取消时调用。"""
        self._integral = 0.0
        self._prev_error = 0.0

    # ── 内部 ──────────────────────────────────────────

    def _to_signal(
        self, correction: float, drift: float, rep: int,
    ) -> ControlSignal:
        """将矫正量映射为四级 guidance 文本。"""
        if correction < 0.3:
            return ControlSignal(level="subtle", text="", correction=correction)
        elif correction < 0.6:
            return ControlSignal(
                level="gentle",
                text="[Monitor] 轻微偏离。请重新确认与目标的关联。",
                correction=correction,
            )
        elif correction < 0.8:
            return ControlSignal(
                level="firm",
                text=f"[Monitor] 明显偏离 (漂移={drift:.2f}, 重复={rep})。请减少工具调用，多加思考。",
                correction=correction,
            )
        else:
            return ControlSignal(
                level="urgent",
                text="[Monitor] 严重偏离。暂停当前方向，重新评估方案。如不确定，请升级到人工决策。",
                correction=correction,
            )
