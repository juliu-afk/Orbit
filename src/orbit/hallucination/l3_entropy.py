"""L3 概率熵监控器（Step 4.1）。

WHY L3：LLM 高熵意味着 token 概率分布均匀——模型在"猜"，输出不可靠。
在生成过程中逐 token 计算归一化熵，滑动窗口均值超阈值即触发熔断。

纯函数设计：无 IO、无数据库、无异步。纳秒级判定，不增加生成延迟。
PRD 技术约束：使用异步流式接口（acompletion(stream=True)），本监控器
被 LLMClient 流式回调调用（当前批次独立交付，流式集成留 Step 5.1）。

降级策略（ADR 风险1）：模型不返回 logprobs 时，切换为 token 重复度检测——
连续 N 个相同 token 视为高熵信号。
"""

from __future__ import annotations

import math
from collections import deque

from orbit.hallucination.schemas import L3EntropyConfig


class L3EntropyMonitor:
    """流式 token 熵监控器。

    用法（调度器/LLMClient 调用）：
        config = L3EntropyConfig(window_size=10, threshold=0.75)
        monitor = L3EntropyMonitor(config)
        for token, logprobs in stream:
            result = monitor.on_token(token, logprobs)
            if result is not None:
                raise HighEntropyError(entropy=result, threshold=config.threshold)
    """

    def __init__(self, config: L3EntropyConfig | None = None):
        self.config = config or L3EntropyConfig()
        # 滑动窗口：存最近 window_size 个采样点的熵值
        self._buffer: deque[float] = deque(maxlen=self.config.window_size)
        # 降级模式：无 logprobs 时记录最近 token 用于重复度检测
        self._last_token: str | None = None
        self._repeat_count: int = 0
        # 采样计数器（生产可按间隔采样减少计算开销，MVP 每 token 采样）
        self._token_count: int = 0

    def on_token(self, token: str, logprobs: list[float] | None) -> float | None:
        """处理一个 token，返回当前滑动窗口平均熵（超阈值时）或 None（正常）。

        Args:
            token: 当前 token 文本
            logprobs: 该 token 的 log 概率列表（来自 LLM logprobs 参数），
                      None 表示模型不支持 logprobs

        Returns:
            滑动窗口平均熵（≥ threshold 时），否则 None
        """
        self._token_count += 1

        if logprobs:
            entropy = self._compute_entropy(logprobs)
            self._buffer.append(entropy)
            # 重置降级状态（有 logprobs 就不需要降级）
            self._repeat_count = 0
        elif self.config.fallback_enabled:
            # 降级：基于重复度评估熵
            entropy = self._fallback_repetition(token)
            self._buffer.append(entropy)
        else:
            return None

        # 窗口未满不触发
        if len(self._buffer) < self.config.window_size:
            return None

        avg = sum(self._buffer) / len(self._buffer)
        if avg >= self.config.threshold:
            return avg
        return None

    def should_cancel(self) -> bool:
        """查询是否应取消生成（窗口满且均值超阈值）。

        WHY 独立方法：调用方可在不传 token 时检查状态（如超时检测）。
        """
        if len(self._buffer) < self.config.window_size:
            return False
        avg = sum(self._buffer) / len(self._buffer)
        return avg >= self.config.threshold

    @property
    def current_avg(self) -> float:
        """当前滑动窗口平均熵（窗口未满时返回 0.0）。"""
        if not self._buffer:
            return 0.0
        return sum(self._buffer) / len(self._buffer)

    def reset(self) -> None:
        """重置状态（新一轮生成开始时调用）。"""
        self._buffer.clear()
        self._last_token = None
        self._repeat_count = 0
        self._token_count = 0

    # ---- 内部 ----

    def _compute_entropy(self, logprobs: list[float]) -> float:
        """从 logprobs 计算归一化熵。

        WHY 归一化：不同模型 vocab 大小不同，归一化使阈值可跨模型比较。
        熵 = -Σ(p_i × log(p_i)) / log(N)，其中 p_i = exp(logprob_i)。
        归一化后取值范围 [0, 1]，0 = 完全确定，1 = 完全均匀。
        """
        if not logprobs:
            return 0.0
        # logprobs → probabilities
        probs = [math.exp(lp) for lp in logprobs]
        # 香农熵
        entropy = -sum(p * math.log(p) for p in probs if p > 0)
        # 归一化：除以最大可能熵 log(N)
        n = len(probs)
        if n <= 1:
            return 0.0
        max_entropy = math.log(n)
        return entropy / max_entropy

    def _fallback_repetition(self, token: str) -> float:
        """降级策略：基于 token 重复度估算熵。

        WHY：旧模型不返回 logprobs，重复输出相同 token 是幻觉的强信号。
        连续重复 → 高熵（不确定性高，模型在循环）。
        映射：重复 2 次 → 0.5，3 次 → 0.7，4+ 次 → 0.85。
        """
        if token == self._last_token:
            self._repeat_count += 1
        else:
            self._repeat_count = 0
            self._last_token = token

        # 映射重复次数到熵值
        if self._repeat_count >= 4:
            return 0.85
        elif self._repeat_count >= 3:
            return 0.70
        elif self._repeat_count >= 2:
            return 0.50
        return 0.0
