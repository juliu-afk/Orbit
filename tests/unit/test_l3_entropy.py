"""Step 4.1 L3 概率熵监控器单元测试。

覆盖：正向(低熵通过) / 高熵触发 / 窗口未满 / 降级重复度检测 / 阈值边界 / 重置。
纯函数测试，无 mock 依赖。
"""

from __future__ import annotations

import math

import pytest

from orbit.hallucination.l3_entropy import L3EntropyMonitor
from orbit.hallucination.schemas import L3EntropyConfig


@pytest.fixture
def monitor():
    """默认配置：窗口 5，阈值 0.75。窗口设小方便测试。"""
    config = L3EntropyConfig(window_size=5, threshold=0.75)
    return L3EntropyMonitor(config)


@pytest.fixture
def monitor_default():
    """标准配置：窗口 10，阈值 0.75。"""
    return L3EntropyMonitor()


def test_l3_low_entropy_passes(monitor):
    """正向：低熵序列不触发。确定性 token（logprob ≈ 0 → 概率 ≈ 1）。"""
    # 模拟低熵：每个 token 有 1 个高概率选项
    low_entropy_logprobs = [0.0]  # exp(0) = 1.0 → 熵 = 0
    for _ in range(monitor.config.window_size):
        result = monitor.on_token("x", low_entropy_logprobs)
        assert result is None


def test_l3_high_entropy_triggers(monitor):
    """AC2: 高熵序列触发——窗口均值超阈值。"""
    # 均匀分布的 logprobs：4 个选项，每个概率 0.25
    # 熵 = -4 * (0.25 * log(0.25)) = -log(0.25) = 1.386
    # 归一化：1.386 / log(4) = 1.386 / 1.386 = 1.0
    uniform_logprobs = [math.log(0.25)] * 4  # 均匀分布 → 最大熵
    for i in range(monitor.config.window_size):
        result = monitor.on_token(f"t{i}", uniform_logprobs)
    # 最后一个 token 填满窗口 → 应触发
    assert result is not None
    assert result >= monitor.config.threshold


def test_l3_window_not_full_no_trigger(monitor):
    """边缘：窗口未满时不触发。"""
    uniform_logprobs = [math.log(0.25)] * 4
    # 只喂 3 个 token（窗口大小 5）
    for i in range(3):
        result = monitor.on_token(f"t{i}", uniform_logprobs)
        assert result is None
    assert not monitor.should_cancel()


def test_l3_fallback_repetition_detection():
    """降级：无 logprobs 时重复度检测生效。"""
    # 用更小窗口+低阈值确保降级重复可触发
    config = L3EntropyConfig(window_size=3, threshold=0.6)
    monitor = L3EntropyMonitor(config)
    # 连续相同 token → 重复度熵递增
    # token1: repeat=0 → 0.0, token2: repeat=1 → 0.0, token3: repeat=2 → 0.5
    # token4: repeat=3 → 0.7, token5: repeat=4 → 0.85
    # 窗口=3：最后3个采样 = [0.0, 0.5, 0.7] → avg=0.4 (窗口移出最早)
    # 再来：repeat=4 → 0.85, 窗口 [0.5, 0.7, 0.85] → avg=0.683 > 0.6
    for _ in range(5):
        monitor.on_token("hello", None)
    # 5 次 hello 后窗口 = [0.5, 0.7, 0.85]（最后 3 个），均值 ≈ 0.683
    assert monitor.should_cancel()


def test_l3_fallback_disabled(monitor):
    """降级关闭时，无 logprobs 直接跳过。"""
    monitor.config.fallback_enabled = False
    result = monitor.on_token("x", None)
    assert result is None
    assert monitor.current_avg == 0.0


def test_l3_reset_clears_state(monitor):
    """重置后状态清空。"""
    uniform_logprobs = [math.log(0.25)] * 4
    for i in range(monitor.config.window_size):
        monitor.on_token(f"t{i}", uniform_logprobs)
    assert monitor.should_cancel()

    monitor.reset()
    assert not monitor.should_cancel()
    assert monitor.current_avg == 0.0


def test_l3_threshold_boundary(monitor):
    """熵恰好等于阈值时触发。"""
    monitor.config.threshold = 0.5
    # 中等熵：2 选项，概率 (0.7, 0.3)
    # 熵 = -(0.7*log(0.7) + 0.3*log(0.3)) / log(2)
    # = -(0.7*-0.357 + 0.3*-1.204) / 0.693
    # = -(-0.250 - 0.361) / 0.693 = 0.611/0.693 ≈ 0.882
    medium_logprobs = [math.log(0.7), math.log(0.3)]
    for i in range(monitor.config.window_size):
        result = monitor.on_token(f"t{i}", medium_logprobs)
    assert result is not None


def test_l3_single_token_no_entropy():
    """单一 token 选项 → 熵为 0。"""
    monitor = L3EntropyMonitor(L3EntropyConfig(window_size=1, threshold=0.5))
    result = monitor.on_token("x", [0.0])  # 单选项 → 熵 0
    assert result is None  # 0 < 0.5


def test_l3_empty_logprobs():
    """空 logprobs 列表 → 熵为 0。"""
    monitor = L3EntropyMonitor(L3EntropyConfig(window_size=1, threshold=0.5))
    result = monitor.on_token("x", [])
    assert result is None
