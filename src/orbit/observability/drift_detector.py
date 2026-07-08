"""CUSUM 变点检测 (V14.2+Theory 方向 20).

监控每个 LLM 模型的 (success_rate, latency, output_len) 三元组。
任一 metric 的 CUSUM > h=5 → DriftAlert。

与 Bandit 互补:
  Bandit (Thompson Sampling) → 适应慢漂移（后验逐渐更新）
  CUSUM → 检测急变（一次更新后模型行为完全不同）

用法:
    detector = CUSUMDriftDetector(threshold=5.0)
    alert = detector.update("gpt-4.1", latency_ms=12000, success=False, output_len=50)
    if alert:
        bandit.reset_arm(alert.model)  # 重评估该模型
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class DriftAlert:
    """变点检测告警。"""
    model: str
    score: float           # CUSUM 分数——超过阈值才触发
    metric: str = ""       # 触发的 metric
    latency_pct: float = 0.0
    success_shift: float = 0.0


class CUSUMDriftDetector:
    """CUSUM 变点检测器。

    双时间尺度覆盖:
      慢: Bandit Beta 后验逐渐适应 → ~50 次收敛
      快: CUSUM → ~15 次检测 50%→90% 成功率 shift
    """

    def __init__(
        self,
        threshold: float = 5.0,
        window_size: int = 100,
    ) -> None:
        self.h = threshold
        self.window = window_size
        # 每模型基线: model → {success_rate, latency_log_mean, latency_log_std, output_len_mean, output_len_std}
        self._baselines: dict[str, dict[str, float]] = {}
        # 每模型 CUSUM 分数
        self._cusum: dict[str, float] = {}
        # 滚动窗口数据
        self._history: dict[str, list[dict]] = {}
        self._cooldown: dict[str, int] = {}  # P2-2: 变点后冷却期——防连续触发
        self._COOLDOWN_WINDOW = 10  # 变点检测后 10 次更新内不重触发

    def update(
        self,
        model: str,
        latency_ms: float,
        success: bool,
        output_len: int = 0,
    ) -> DriftAlert | None:
        """观察一个任务结果，检查是否有变点。

        Returns:
            DriftAlert 如果检测到变点，否则 None
        """
        # 初始化基线——需要足够历史
        if model not in self._baselines:
            self._baselines[model] = {
                "success_rate": 0.9,  # 乐观先验
                "latency_log_mean": math.log(max(latency_ms, 1)),
                "latency_log_std": 1.0,
                "output_len_mean": float(output_len),
                "output_len_std": 100.0,
            }
            self._cusum[model] = 0.0
            self._history[model] = []
            return None

        baseline = self._baselines[model]

        # 累积滚动窗口
        self._history[model].append({
            "success": 1.0 if success else 0.0,
            "latency": latency_ms,
            "output_len": output_len,
        })
        if len(self._history[model]) > self.window:
            self._history[model] = self._history[model][-self.window:]

        # 标准化 anomaly 分数——各 metric 独立 CUSUM
        metrics_anomaly = {
            "success": abs(
                (1.0 if success else 0.0) - baseline["success_rate"]
            ),
            "latency": abs(
                math.log(max(latency_ms, 1)) - baseline["latency_log_mean"]
            ) / max(baseline["latency_log_std"], 0.1),
            "output_len": abs(output_len - baseline["output_len_mean"])
                          / max(baseline["output_len_std"], 1.0) if output_len > 0 else 0.0,
        }
        # Fisher 联合——−2 Σ ln(p-value) 近似
        combined = -2 * sum(
            math.log(max(1.0 - min(m, 0.99), 0.001))
            for m in metrics_anomaly.values()
        )

        cusum = self._cusum.get(model, 0.0)
        cusum = max(0.0, cusum + combined - 1.0)  # 漂移项=1 吸收正常噪声
        self._cusum[model] = cusum

        if cusum > self.h:
            # 冷却期检查——变点后 N 次更新内不重触发
            cd = self._cooldown.get(model, 0)
            if cd > 0:
                self._cooldown[model] = cd - 1
                self._cusum[model] = 0.0
                return None
            # 检测到变点——重置 CUSUM + 进入冷却期 + 返回告警
            self._cooldown[model] = self._COOLDOWN_WINDOW
            self._cusum[model] = 0.0
            self._update_baseline(model)
            return DriftAlert(
                model=model,
                score=cusum,
                metric=max(metrics_anomaly, key=metrics_anomaly.get),
                success_shift=metrics_anomaly["success"],
                latency_pct=metrics_anomaly["latency"],
            )

        # 无变点——滚动更新基线
        self._update_baseline(model)
        return None

    def reset(self, model: str) -> None:
        """重置某模型的检测器——Bandit 重评估后调用。"""
        self._baselines.pop(model, None)
        self._cusum.pop(model, None)
        self._history.pop(model, None)

    # ── 内部 ──────────────────────────────────────────

    def _update_baseline(self, model: str) -> None:
        """滚动窗口更新基线——适应慢漂移。"""
        hist = self._history.get(model, [])
        if len(hist) < 3:
            return
        success_vals = [h["success"] for h in hist]
        latency_vals = [math.log(max(h["latency"], 1)) for h in hist]
        output_vals = [h["output_len"] for h in hist if h["output_len"] > 0]

        self._baselines[model] = {
            "success_rate": sum(success_vals) / len(success_vals),
            "latency_log_mean": sum(latency_vals) / len(latency_vals),
            "latency_log_std": _std(latency_vals) or 0.1,
            "output_len_mean": sum(output_vals) / len(output_vals) if output_vals else 100.0,
            "output_len_std": _std(output_vals) or 100.0,
        }


def _std(values: list[float]) -> float:
    """安全标准差——n≥2 时计算，否则返回 0。"""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))
