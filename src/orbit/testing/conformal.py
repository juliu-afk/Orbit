"""Inductive Conformal Prediction (V14.2+Theory 方向 16).

用法:
    cp = ConformalPredictor(alpha=0.05)
    cp.calibrate([(task1, code1, True), ...])
    reliable = cp.predict("task", [candidate_a, candidate_b])
"""
from __future__ import annotations
import math

class ConformalPredictor:
    def __init__(self, alpha: float = 0.05) -> None:
        if not 0 < alpha < 1:
            raise ValueError(f"alpha must be in (0, 1), got {alpha}")
        self.alpha = alpha
        self._calibration_scores: list[float] = []
        self._n_cal: int = 0

    def calibrate(self, calibration_data: list[tuple[str, str, bool]]) -> None:
        scores = sorted(self._nonconformity(task, code, success) for task, code, success in calibration_data)
        self._calibration_scores = scores
        self._n_cal = len(scores)

    def predict(self, task: str, candidates: list[str]) -> list[str]:
        """返回1-α置信预测集。每个候选按代码特征评分——校准集已编码成功/失败分布。"""
        if self._n_cal == 0 or not candidates:
            return list(candidates)
        idx = max(1, min(math.ceil((1 - self.alpha) * (self._n_cal + 1)), self._n_cal))
        threshold = self._calibration_scores[idx - 1]
        return [c for c in candidates if self._nonconformity(task, c) <= threshold]

    def p_value(self, task: str, code: str) -> float:
        if self._n_cal == 0:
            return 1.0
        score = self._nonconformity(task, code)
        count_ge = sum(1 for s in self._calibration_scores if s >= score)
        return (count_ge + 1) / (self._n_cal + 1)

    @staticmethod
    def _nonconformity(task: str, code: str, success: bool | None = None) -> float:
        """非一致性评分——越低越好。task 参数影响评分以区分不同任务上下文。"""
        base = 0.0
        if success is not None:
            base = 0.0 if success else 3.0
        lint = code.lower().count("error") * 0.5
        length = len(code) / 5000.0
        # task-code 语义距离——共享词越少越不一致（P1-1修复: task 参与计算）
        task_words = set(task.lower().split()) if task else set()
        code_words = set(code.lower().split())
        overlap = len(task_words & code_words) / max(len(task_words | code_words), 1)
        semantic_penalty = (1.0 - overlap) * 0.5 if task_words else 0.0
        return base + lint + length + semantic_penalty
