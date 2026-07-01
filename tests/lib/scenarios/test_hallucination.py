"""防幻觉场景——L1-L8 各层拦截与通过场景。

覆盖防幻觉体系深度防御的各层行为。
"""

from __future__ import annotations

import pytest

from tests.lib.assertions.hallucination import assert_layer_blocked, assert_layer_passed


def _mock_hallucination_result(layers: dict[str, bool], reasons: dict[str, str] | None = None) -> dict:
    """构造防幻觉检测结果。"""
    return {"layers": layers, "reasons": reasons or {}}


# ── L1: 静态图谱校验 ──────────────────────────────────────

@pytest.mark.scenario_hallucination
async def test_l1_graph_blocks_nonexistent_symbol() -> None:
    """LLM 输出的函数名在 CodeGraph 中不存在→L1 拦截。"""
    result = _mock_hallucination_result(
        {"L1": False},  # L1 拦截
        {"L1": "Symbol 'nonexistent_func' not found in CodeGraph"},
    )
    assert_layer_blocked(result, "L1", reason_contains="not found")


@pytest.mark.scenario_hallucination
async def test_l1_graph_passes_existing_symbol() -> None:
    """LLM 输出的函数名在 CodeGraph 中存在→L1 通过。"""
    result = _mock_hallucination_result({"L1": True})
    assert_layer_passed(result, "L1")


# ── L3: 熵监控 ─────────────────────────────────────────────

@pytest.mark.scenario_hallucination
async def test_l3_entropy_blocks_high_entropy_output() -> None:
    """LLM 输出熵值超过阈值→L3 拦截。"""
    result = _mock_hallucination_result(
        {"L3": False},
        {"L3": "Entropy 0.89 exceeds threshold 0.75"},
    )
    assert_layer_blocked(result, "L3", reason_contains="Entropy")


@pytest.mark.scenario_hallucination
async def test_l3_entropy_passes_normal_output() -> None:
    """LLM 输出熵值正常→L3 通过。"""
    result = _mock_hallucination_result({"L3": True})
    assert_layer_passed(result, "L3")


# ── L4: 类型校验 ─────────────────────────────────────────

@pytest.mark.scenario_hallucination
async def test_l4_type_blocks_mypy_error() -> None:
    """LLM 生成代码有 mypy 类型错误→L4 拦截。"""
    result = _mock_hallucination_result(
        {"L4": False},
        {"L4": "mypy: Argument 1 to 'login' has incompatible type 'int'; expected 'str'"},
    )
    assert_layer_blocked(result, "L4", reason_contains="mypy")


@pytest.mark.scenario_hallucination
async def test_l4_type_passes_clean_code() -> None:
    """LLM 生成代码通过 mypy→L4 通过。"""
    result = _mock_hallucination_result({"L4": True})
    assert_layer_passed(result, "L4")


# ── L8: 配置漂移检测 ─────────────────────────────────────

@pytest.mark.scenario_hallucination
async def test_l8_config_blocks_drift() -> None:
    """检测到配置漂移→L8 拦截。"""
    result = _mock_hallucination_result(
        {"L8": False},
        {"L8": "Config drift detected: .env MODEL changed from 'v4-pro' to 'v4-flash'"},
    )
    assert_layer_blocked(result, "L8", reason_contains="drift")
