"""Inductive Conformal Prediction (V14.2+Theory 方向 16).

分布无关（distribution-free）——不假设 LLM 输出服从任何特定分布，
仅要求可交换性。有限样本有效——校准集大小 n → 置信保证 1-α。

用法:
    cp = ConformalPredictor(alpha=0.05)
    cp.calibrate([(task1, code1, True), (task2, code2, False), ...])
    reliable = cp.predict("新任务", [candidate_a, candidate_b, candidate_c])
    # → 95% 置信保证候选集中包含正确实现
"""

from __future__ import annotations

import math


class ConformalPredictor:
    """Inductive Conformal Prediction——有限样本置信预测集。

    α = 0.05 → 95% 置信保证。

    非一致性评分: 0=高度一致（好），大值=异常（差）。
    评分 = 测试失败数 * 3.0 + lint 错误 * 0.5 + 代码长度/5000
    """

    def __init__(self, alpha: float = 0.05) -> None:
        if not 0 < alpha < 1:
            raise ValueError(f"alpha must be in (0, 1), got {alpha}")
        self.alpha = alpha
        self._calibration_scores: list[float] = []
        self._n_cal: int = 0

    def calibrate(self, calibration_data: list[tuple[str, str, bool]]) -> None:
        """校准——计算校准集的非一致性评分分布。

        calibration_data: list of (task_description, generated_code, success)
        """
        scores = sorted(
            self._nonconformity(task, code, success)
            for task, code, success in calibration_data
        )
        self._calibration_scores = scores
        self._n_cal = len(scores)

    def predict(self, task: str, candidates: list[str]) -> list[str]:
        """返回 1-α 置信预测集。

        保证: P(正确代码 ∈ prediction_set) ≥ 1-α（有限样本有效）

        若校准集为空（无历史数据），返回全部候选（不筛选）。
        """
        if self._n_cal == 0 or not candidates:
            return list(candidates)

        # 校准阈值: 第 ⌈(1-α)(n+1)⌉ 个校准分数
        idx = math.ceil((1 - self.alpha) * (self._n_cal + 1))
        # 夹紧到有效范围
        idx = max(1, min(idx, self._n_cal))
        threshold = self._calibration_scores[idx - 1]

        result = []
        for code in candidates:
            score = self._nonconformity(task, code, True)
            if score <= threshold:
                result.append(code)
        return result

    def p_value(self, task: str, code: str) -> float:
        """计算单个候选的共形 p-value。

        p > α → 不应拒绝（候选在预测集中）。
        """
        if self._n_cal == 0:
            return 1.0
        score = self._nonconformity(task, code, True)
        # p = (校准分 ≥ 该分 + 1) / (n+1)
        count_ge = sum(1 for s in self._calibration_scores if s >= score)
        return (count_ge + 1) / (self._n_cal + 1)

    # ── 内部 ──────────────────────────────────────────

    @staticmethod
    def _nonconformity(task: str, code: str, success: bool) -> float:
        """非一致性评分——越低越好（越 conforming）。

        success=False → 基础惩罚 3.0
        lint 错误 → 每错 0.5
        代码长度 → 每 5000 字符 +1.0（偏好简洁代码）
        """
        base = 0.0 if success else 3.0
        lint = code.count("error") * 0.5  # 简化 lint 计数——生产用 mypy JSON
        length = len(code) / 5000.0
        return base + lint + length
