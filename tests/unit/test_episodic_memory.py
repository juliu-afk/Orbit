"""Unit tests: EpisodicMemory — graph-structured event storage (was 0% coverage, 80 stmts).

Uses in-memory SQLite — no filesystem, fast, isolated per test.
"""

from __future__ import annotations

import pytest

from orbit.memory.episodic import (
    EpisodicEvent,
    EpisodicMemory,
    EventImportance,
    RelationType,
)


@pytest.fixture
def em():
    """Fresh in-memory episodic memory per test."""
    m = EpisodicMemory(":memory:")
    yield m
    m.close()


# ── record_event ─────────────────────────────────────────────────


def test_record_event_basic(em):
    """记录事件 → 返回 EpisodicEvent 含 id。"""
    ev = em.record_event(task_id="t1", title="审计调整被否定")
    assert ev.id != ""
    assert ev.task_id == "t1"
    assert ev.title == "审计调整被否定"
    assert ev.importance == EventImportance.MEDIUM


def test_record_event_full(em):
    """记录完整事件——所有字段。"""
    ev = em.record_event(
        task_id="t2",
        title="支付超时",
        description="支付宝回调超时 30s",
        agent_role="developer",
        importance=EventImportance.CRITICAL,
        outcome="failure",
        tags=["payment", "timeout"],
        context_snapshot={"api": "alipay"},
    )
    assert ev.importance == EventImportance.CRITICAL
    assert ev.outcome == "failure"
    assert "payment" in ev.tags
    assert ev.context_snapshot["api"] == "alipay"


def test_record_event_idempotent(em):
    """同 task_id + title → INSERT OR REPLACE，不抛异常。"""
    ev1 = em.record_event(task_id="t1", title="重复事件")
    ev2 = em.record_event(task_id="t1", title="重复事件")
    assert ev1.id == ev2.id  # 相同 id——确定性哈希


# ── get_timeline ─────────────────────────────────────────────────


def test_timeline_ordered(em):
    """get_timeline 按时间升序返回。"""
    em.record_event(task_id="t1", title="第一步")
    em.record_event(task_id="t1", title="第二步")
    em.record_event(task_id="t1", title="第三步")
    tl = em.get_timeline("t1")
    assert len(tl) == 3
    assert tl[0].title == "第一步"
    assert tl[-1].title == "第三步"


def test_timeline_task_isolation(em):
    """get_timeline 只返回指定 task_id 的事件。"""
    em.record_event(task_id="t1", title="T1 事件")
    em.record_event(task_id="t2", title="T2 事件")
    tl = em.get_timeline("t1")
    assert len(tl) == 1
    assert tl[0].task_id == "t1"


def test_timeline_limit(em):
    """limit 参数限制返回数量。"""
    for i in range(10):
        em.record_event(task_id="t1", title=f"事件{i}")
    tl = em.get_timeline("t1", limit=3)
    assert len(tl) == 3


# ── add_relation + find_related ──────────────────────────────────


def test_add_and_find_relation(em):
    """添加关系 → find_related 按关系类型检索。"""
    ev1 = em.record_event(task_id="t1", title="原因")
    ev2 = em.record_event(task_id="t1", title="结果")
    em.add_relation(ev2.id, ev1.id, RelationType.CAUSED_BY, description="因果链")

    related = em.find_related(ev2.id, relation_type=RelationType.CAUSED_BY)
    assert len(related) == 1
    assert related[0].title == "原因"


def test_find_related_all_types(em):
    """find_related 不指定类型 → 返回所有关系。"""
    ev1 = em.record_event(task_id="t1", title="A")
    ev2 = em.record_event(task_id="t1", title="B")
    em.add_relation(ev1.id, ev2.id, RelationType.FOLLOWED_BY)
    em.add_relation(ev1.id, ev2.id, RelationType.RELATED_TO)
    related = em.find_related(ev1.id)
    assert len(related) == 2


# ── search_by_tags ───────────────────────────────────────────────


def test_search_by_tags(em):
    """按标签搜索——LIKE 匹配。"""
    em.record_event(task_id="t1", title="审计调整", tags=["audit", "AR"])
    em.record_event(task_id="t1", title="支付超时", tags=["payment"])
    results = em.search_by_tags(["audit"])
    assert len(results) == 1
    assert results[0].title == "审计调整"


def test_search_by_multiple_tags(em):
    """多标签 OR 搜索。"""
    em.record_event(task_id="t1", title="E1", tags=["audit"])
    em.record_event(task_id="t1", title="E2", tags=["payment"])
    results = em.search_by_tags(["audit", "payment"])
    assert len(results) == 2


# ── get_critical_events ──────────────────────────────────────────


def test_critical_events(em):
    """get_critical_events 只返回 CRITICAL/HIGH 事件。"""
    em.record_event(task_id="t1", title="关键", importance=EventImportance.CRITICAL)
    em.record_event(task_id="t1", title="重要", importance=EventImportance.HIGH)
    em.record_event(task_id="t1", title="普通", importance=EventImportance.MEDIUM)
    em.record_event(task_id="t1", title="背景", importance=EventImportance.LOW)
    critical = em.get_critical_events(task_id="t1")
    assert len(critical) == 2
    importances = {e.importance for e in critical}
    assert importances == {EventImportance.CRITICAL, EventImportance.HIGH}


def test_critical_events_all_tasks(em):
    """get_critical_events 不指定 task_id → 跨任务。"""
    em.record_event(task_id="t1", title="CRIT1", importance=EventImportance.CRITICAL)
    em.record_event(task_id="t2", title="HIGH1", importance=EventImportance.HIGH)
    critical = em.get_critical_events()
    assert len(critical) == 2


# ── all ──────────────────────────────────────────────────────────


def test_all_events(em):
    """all() 返回所有事件（最多 100）。"""
    for i in range(5):
        em.record_event(task_id="t1", title=f"事件{i}")
    events = em.all()
    assert len(events) == 5


# ── edge cases ───────────────────────────────────────────────────


def test_empty_timeline(em):
    """空任务 → 空列表。"""
    assert em.get_timeline("nonexistent") == []


def test_search_single_tag_no_match(em):
    """标签搜索无匹配 → 空列表。"""
    em.record_event(task_id="t1", title="E1", tags=["audit"])
    assert em.search_by_tags(["nonexistent"]) == []


def test_empty_related(em):
    """无关系 → 空列表。"""
    ev = em.record_event(task_id="t1", title="孤立事件")
    assert em.find_related(ev.id) == []
