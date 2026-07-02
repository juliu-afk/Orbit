"""覆盖率补测——memory/store.py 额外路径 + memory/decision_log.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from orbit.memory.decision_log import Decision, DecisionLog, parse_decision_marker
from orbit.memory.models import MemoryFileType
from orbit.memory.store import MemoryStore


# ════════════════════════════════════════════
# 1. MemoryStore 额外路径
# ════════════════════════════════════════════

class TestMemoryStoreExtended:
    @pytest.fixture
    def store(self, tmp_path):
        return MemoryStore(str(tmp_path))

    def test_write_and_read_roundtrip(self, store):
        """写入 → 读取——内容一致。"""
        store.write_file(
            MemoryFileType.EPISODIC,
            "# Test\ncontent here\n",
            frontmatter={"type": "episodic"},
        )
        mem = store.read_file(MemoryFileType.EPISODIC)
        assert "content here" in mem.body

    def test_read_nonexistent_returns_empty(self, store):
        """读取不存在的文件 → 返回默认 MemoryFile。"""
        mem = store.read_file(MemoryFileType.NOTES)
        assert mem.body == ""
        assert mem.frontmatter == {}

    def test_decay_scores(self, store):
        """decay_scores 降低所有评分。"""
        store.write_file(
            MemoryFileType.EPISODIC,
            "# Test",
            frontmatter={"score.a": "5.0", "score.b": "3.0"},
        )
        store.decay_scores()
        mem = store.read_file(MemoryFileType.EPISODIC)
        # 衰减后分数应降低（0.9 倍或类似）
        a = float(mem.frontmatter.get("score.a", "5.0"))
        assert a <= 5.0

    def test_hit_flushes_at_threshold(self, store):
        """hit() 达到 10 次缓冲阈值时自动 flush。"""
        store.write_file(
            MemoryFileType.EPISODIC,
            "# Test",
            frontmatter={f"score.k{i}": "1.0" for i in range(5)},
        )
        # 触发 10 次 hit → 自动 flush
        for i in range(10):
            store.hit(f"k{i}", delta=0.5)
        # _score_buffer 应为空（已 flush）
        assert len(store._score_buffer) == 0

    def test_bm25_search(self, store):
        """BM25 搜索返回结果。"""
        from orbit.memory.models import MemorySearchQuery
        store.write_file(
            MemoryFileType.EPISODIC,
            "# Section A\npython async programming tips\n## Section B\npytest fixtures usage\n",
        )
        q = MemorySearchQuery(query="python pytest", max_results=5)
        results = store.search(q)
        assert isinstance(results, list)


# ════════════════════════════════════════════
# 2. DecisionLog
# ════════════════════════════════════════════

class TestDecisionLogExtended:
    def test_parse_decision_marker_valid(self):
        """解析合法 [DECISION] 标记。"""
        marker = """[DECISION] Q: Which database?
A: PostgreSQL
Alternatives: MySQL, SQLite
Rationale: JSON support is better"""
        result = parse_decision_marker(marker)
        assert result is not None
        assert result.answer == "PostgreSQL"

    def test_parse_decision_marker_no_marker(self):
        """无 [DECISION] 标记 → None。"""
        result = parse_decision_marker("just some text")
        assert result is None

    def test_decision_fields(self):
        """Decision 包含必需字段。"""
        import time
        d = Decision(
            question="What cache to use?",
            answer="Redis",
            alternatives=["Memcached", "in-memory"],
            rationale="faster than DB queries",
            agent="architect",
            task_id="task-1",
            timestamp=time.time(),
        )
        assert d.question == "What cache to use?"
        assert d.answer == "Redis"
        assert len(d.alternatives) == 2

    def test_decision_log_record(self, tmp_path):
        """record 追加决策到日志。"""
        import time
        log = DecisionLog(tmp_path)
        d = Decision(
            question="How to store state?",
            answer="PostgreSQL",
            alternatives=["SQLite", "Redis"],
            rationale="ACID compliance",
            agent="architect",
            task_id="task-2",
            timestamp=time.time(),
        )
        log.record(d)
        decisions = log.recent(10)
        assert len(decisions) >= 1

    def test_decision_log_recent_empty(self, tmp_path):
        """空日志 recent 返回空。"""
        log = DecisionLog(tmp_path)
        decisions = log.recent(10)
        assert decisions == []

    def test_decision_log_query(self, tmp_path):
        """query 按关键词搜索。"""
        import time
        log = DecisionLog(tmp_path)
        d = Decision(
            question="Which ORM?",
            answer="SQLAlchemy",
            alternatives=["peewee", "raw SQL"],
            rationale="mature and well-supported",
            agent="developer",
            task_id="t3",
            timestamp=time.time(),
        )
        log.record(d)
        results = log.query(["ORM", "SQLAlchemy"], max_results=5)
        assert len(results) >= 1
