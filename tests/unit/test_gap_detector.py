"""Unit tests: TestGapDetector — parameter boundary coverage analysis (was 0%, 40 stmts)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.graph.engines.test_gap_detector import (
    BOUNDARY_CASES,
    TestGap,
    TestGapDetector,
    _checker_any,
)


# ── _checker_any ─────────────────────────────────────────────────


def test_checker_any_match():
    """checker 在 covered set 中找到匹配值 → True。"""
    check = _checker_any(lambda v: v == 0)
    assert check({0, 1, 2}) is True


def test_checker_any_no_match():
    """checker 在 covered set 中未找到匹配 → False。"""
    check = _checker_any(lambda v: v < 0)
    assert check({1, 2, 3}) is False


def test_checker_any_empty():
    """covered set 为空 → False。"""
    check = _checker_any(lambda v: True)
    assert check(set()) is False


# ── BOUNDARY_CASES 结构 ──────────────────────────────────────────


def test_boundary_cases_coverage():
    """所有参数类型都有定义。"""
    assert "int" in BOUNDARY_CASES
    assert "str" in BOUNDARY_CASES
    assert "bool" in BOUNDARY_CASES
    assert "list" in BOUNDARY_CASES
    assert "dict" in BOUNDARY_CASES
    assert "float" in BOUNDARY_CASES


def test_boundary_cases_int():
    """int 类型覆盖: 0, 负数, 大整数。"""
    cases = BOUNDARY_CASES["int"]
    labels = {c[0] for c in cases}
    assert "值为0" in labels
    assert "负数" in labels


# ── _extract_covered_values ──────────────────────────────────────


def test_extract_values():
    """从测试数据提取指定参数的已知覆盖值。"""
    tests = [
        {"params": {"amount": 100}},
        {"params": {"amount": 0}},
        {"params": {"other": "x"}},
    ]
    values = TestGapDetector._extract_covered_values(tests, "amount")
    assert values == {100, 0}


def test_extract_values_empty():
    """无匹配参数 → 空 set。"""
    values = TestGapDetector._extract_covered_values([], "amount")
    assert values == set()


# ── detect ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detect_func_not_found():
    """函数在 code_graph 中不存在 → 空 gaps。"""
    mock = MagicMock()
    mock.get_function_info = AsyncMock(return_value=None)
    detector = TestGapDetector()
    gaps = await detector.detect(mock, "nonexistent_func")
    assert gaps == []


@pytest.mark.asyncio
async def test_detect_no_parameters():
    """函数无参数 → 空 gaps。"""
    mock = MagicMock()
    mock.get_function_info = AsyncMock(return_value={"parameters": {}})
    mock.find_tests_for = AsyncMock(return_value=[])
    detector = TestGapDetector()
    gaps = await detector.detect(mock, "no_args_func")
    assert gaps == []


@pytest.mark.asyncio
async def test_detect_with_gaps():
    """int 参数只测了正值 → 缺失 0 和负数边界。"""
    mock = MagicMock()
    mock.get_function_info = AsyncMock(return_value={
        "parameters": {"count": "int", "label": "str"},
    })
    mock.find_tests_for = AsyncMock(return_value=[
        {"params": {"count": 5, "label": "hello"}},
    ])
    detector = TestGapDetector()
    gaps = await detector.detect(mock, "calculate_score")
    # count(int): 只测了5 → 缺0和负数。label(str): 只测了hello → 缺空串和超长
    assert len(gaps) >= 1  # At least one param has gaps
    gap_params = {g.param_name for g in gaps}
    assert "count" in gap_params  # Missing 0 and negative


@pytest.mark.asyncio
async def test_detect_fully_covered():
    """bool 参数两种值都测了 → 无 gaps。"""
    mock = MagicMock()
    mock.get_function_info = AsyncMock(return_value={
        "parameters": {"flag": "bool"},
    })
    mock.find_tests_for = AsyncMock(return_value=[
        {"params": {"flag": True}},
        {"params": {"flag": False}},
    ])
    detector = TestGapDetector()
    gaps = await detector.detect(mock, "toggler")
    assert gaps == []
