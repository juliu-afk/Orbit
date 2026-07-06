"""Unit tests: BudgetAllocator (was 16%, 38 stmts) — Token budget distribution."""

from __future__ import annotations

from unittest.mock import MagicMock

from orbit.goal.budget_allocator import BudgetAllocator


def _task(id: str, desc: str = "", deps: list[str] | None = None):
    t = MagicMock()
    t.id = id
    t.description = desc
    t.depends_on = deps or []
    return t


def test_allocate_empty_tasks():
    ba = BudgetAllocator()
    result = ba.allocate([], 100000)
    assert result == {}


def test_allocate_zero_budget():
    ba = BudgetAllocator()
    t = _task("t1")
    result = ba.allocate([t], 0)
    assert result == {t.id: 0}


def test_allocate_negative_budget():
    ba = BudgetAllocator()
    t = _task("t1")
    result = ba.allocate([t], -100)
    assert result == {t.id: 0}


def test_allocate_tight_budget():
    """预算不够每人最低 → 均分。"""
    ba = BudgetAllocator(min_per_task=5000)
    tasks = [_task(f"t{i}") for i in range(10)]
    result = ba.allocate(tasks, total_budget=10000)
    # 10 tasks × 5000 min = 50000 > 8500 allocatable → 均分
    for tid, budget in result.items():
        assert budget > 0
        assert budget <= 5000


def test_allocate_normal():
    """预算充足 → 按权重分配。"""
    ba = BudgetAllocator(min_per_task=1000)
    tasks = [
        _task("t_impl", "实现 JWT 中间件", deps=["auth"]),
        _task("t_test", "写单元测试", deps=["t_impl"]),
    ]
    result = ba.allocate(tasks, total_budget=50000)
    # 实现任务权重更高 → 预算更多
    assert result["t_impl"] > result["t_test"]


def test_compute_weight_implement():
    ba = BudgetAllocator()
    t = _task("t1", "实现支付模块", deps=["db", "api"])
    w = ba._compute_weight(t)
    assert w > 1.5  # 1.0 + 2*0.5 = 2.0, ×1.5 = 3.0


def test_compute_weight_test():
    ba = BudgetAllocator()
    t = _task("t1", "写单元测试")
    w = ba._compute_weight(t)
    assert w < 1.0  # 1.0 × 0.7 = 0.7


def test_compute_weight_doc():
    ba = BudgetAllocator()
    t = _task("t1", "更新 README 文档")
    w = ba._compute_weight(t)
    assert w < 0.5  # 1.0 × 0.3 = 0.3


def test_compute_weight_min():
    """权重不低于 0.2。"""
    ba = BudgetAllocator()
    t = _task("t1", "DDL 迁移 + 文档 + 测试")
    w = ba._compute_weight(t)
    assert w >= 0.2


def test_compute_weight_no_desc():
    ba = BudgetAllocator()
    t = _task("t1")
    assert ba._compute_weight(t) == 1.0
