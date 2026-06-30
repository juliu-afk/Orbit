"""决策日志单元测试——US-B5 业务层减熵."""

# ruff: noqa: S101  # 允许 plain assert

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from orbit.memory.decision_log import Decision, DecisionLog, parse_decision_marker


class TestDecisionLog:
    """DecisionLog 读写+检索+冲突检测."""

    def _make_log(self) -> tuple[DecisionLog, Path]:
        """创建指向临时目录的 DecisionLog."""
        d = tempfile.mkdtemp()
        log = DecisionLog(storage_dir=d)
        return log, Path(d)

    def _decision(
        self,
        question: str = "用什么缓存",
        answer: str = "Redis",
        alternatives: list[str] | None = None,
        rationale: str = "需要持久化+高可用",
        agent: str = "architect",
        task_id: str = "task-001",
    ) -> Decision:
        return Decision(
            question=question,
            answer=answer,
            alternatives=alternatives or ["SQLite", "Memcached"],
            rationale=rationale,
            agent=agent,
            task_id=task_id,
            timestamp=time.time(),
        )

    # ── 基础读写 ──────────────────────────────────────

    def test_record_and_retrieve(self):
        """记录一条决策，通过 recent() 取回验证字段."""
        log, _tmp = self._make_log()
        d = self._decision()
        log.record(d)

        recent = log.recent(10)
        assert len(recent) == 1
        assert recent[0].question == "用什么缓存"
        assert recent[0].answer == "Redis"
        assert recent[0].rationale == "需要持久化+高可用"
        assert recent[0].agent == "architect"
        assert recent[0].task_id == "task-001"
        assert "SQLite" in recent[0].alternatives
        assert "Memcached" in recent[0].alternatives

    def test_record_appends_jsonl(self):
        """每条记录追加一行 JSON，文件行数等于记录数."""
        log, tmp = self._make_log()
        log.record(self._decision(question="Q1"))
        log.record(self._decision(question="Q2"))

        lines = (tmp / "decisions.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        obj1 = json.loads(lines[0])
        assert obj1["question"] == "Q1"
        obj2 = json.loads(lines[1])
        assert obj2["question"] == "Q2"

    # ── 关键词检索 ────────────────────────────────────

    def test_query_by_keyword(self):
        """按关键词检索，OR 逻辑，匹配 question/answer/alternatives/rationale."""
        log, _tmp = self._make_log()
        log.record(self._decision(question="用什么缓存", answer="Redis"))
        log.record(self._decision(question="用什么数据库", answer="PostgreSQL"))
        log.record(self._decision(question="前端框架选型", answer="React"))

        # 匹配第一个（question 含"缓存"）
        results = log.query(["缓存"])
        assert len(results) == 1
        assert results[0].answer == "Redis"

        # 匹配第二个（question 含"数据库"）
        results = log.query(["数据库"])
        assert len(results) == 1
        assert results[0].answer == "PostgreSQL"

        # Redis + React 都含"Re"，但 PostgreSQL 也含"re" → 3 个
        results = log.query(["Re"])
        assert len(results) == 3

    def test_query_case_insensitive(self):
        """检索大小写不敏感."""
        log, _tmp = self._make_log()
        log.record(self._decision(question="Use Redis or SQLite", answer="Redis"))
        results = log.query(["redis"])
        assert len(results) == 1
        assert results[0].answer == "Redis"

    def test_query_empty_keywords(self):
        """空关键词返回空列表."""
        log, _tmp = self._make_log()
        log.record(self._decision())
        assert log.query([]) == []

    def test_query_max_results(self):
        """max_results 限制返回条数."""
        log, _tmp = self._make_log()
        for i in range(10):
            log.record(self._decision(question=f"Q{i}", answer=f"A{i}"))
        results = log.query(["Q"], max_results=3)
        assert len(results) == 3

    # ── 冲突检测 ──────────────────────────────────────

    def test_find_conflicts(self):
        """相似问题不同答案→检测到冲突."""
        log, _tmp = self._make_log()
        log.record(self._decision(question="用什么缓存", answer="Redis"))
        log.record(self._decision(question="用什么缓存", answer="Memcached"))

        conflicts = log.find_conflicts("用什么缓存", threshold=0.5)
        assert len(conflicts) == 1
        assert len(conflicts[0]) == 2
        answers = {d.answer for d in conflicts[0]}
        assert answers == {"Redis", "Memcached"}

    def test_find_no_conflicts_same_answer(self):
        """相似问题相同答案→无冲突."""
        log, _tmp = self._make_log()
        log.record(self._decision(question="用什么缓存", answer="Redis"))
        log.record(self._decision(question="选什么缓存", answer="Redis"))

        conflicts = log.find_conflicts("缓存", threshold=0.3)
        assert len(conflicts) == 0

    def test_find_no_conflicts_different_questions(self):
        """不同问题不同答案→无冲突."""
        log, _tmp = self._make_log()
        log.record(self._decision(question="用什么缓存", answer="Redis"))
        log.record(self._decision(question="前端框架选型", answer="React"))

        conflicts = log.find_conflicts("用什么缓存", threshold=0.5)
        assert len(conflicts) == 0

    def test_find_conflicts_jaccard_similarity(self):
        """Jaccard 相似度低于 threshold 的不视为冲突."""
        log, _tmp = self._make_log()
        log.record(self._decision(question="用什么缓存", answer="Redis"))
        log.record(self._decision(question="今天天气怎么样", answer="晴天"))

        # 高阈值应当排除完全不相关的问题
        conflicts = log.find_conflicts("用什么缓存", threshold=0.7)
        assert len(conflicts) == 0

    # ── 空日志 ────────────────────────────────────────

    def test_empty_log_returns_empty(self):
        """空日志时各种查询均返回空."""
        log, _tmp = self._make_log()
        assert log.query(["缓存"]) == []
        assert log.find_conflicts("用什么缓存") == []
        assert log.recent(10) == []

    # ── recent ────────────────────────────────────────

    def test_recent_returns_newest_first(self):
        """recent() 按时间倒序返回."""
        log, _tmp = self._make_log()
        d1 = self._decision(question="Q1", answer="A1")  # 默认 timestamp 最大
        d2 = self._decision(question="Q2", answer="A2")
        d3 = self._decision(question="Q3", answer="A3")
        # 手动调整时间戳顺序
        d1.timestamp = 300.0
        d2.timestamp = 100.0
        d3.timestamp = 200.0
        log.record(d1)
        log.record(d2)
        log.record(d3)

        recent = log.recent(3)
        assert recent[0].question == "Q1"  # 300
        assert recent[1].question == "Q3"  # 200
        assert recent[2].question == "Q2"  # 100

    def test_recent_n(self):
        """recent(n) 返回不超过 n 条."""
        log, _tmp = self._make_log()
        for i in range(10):
            log.record(self._decision(question=f"Q{i}", answer=f"A{i}"))
        assert len(log.recent(3)) == 3
        assert len(log.recent(100)) == 10


class TestParseDecisionMarker:
    """[DECISION] 标记解析."""

    def test_parse_full(self):
        text = """我们决定用 Redis 做缓存。
[DECISION] Q: 用什么缓存
A: Redis
Alternatives: SQLite, Memcached
Rationale: 需要持久化+高可用
"""
        d = parse_decision_marker(text)
        assert d is not None
        assert d.question == "用什么缓存"
        assert d.answer == "Redis"
        assert d.rationale == "需要持久化+高可用"
        assert "SQLite" in d.alternatives
        assert "Memcached" in d.alternatives

    def test_parse_no_marker(self):
        """无标记返回 None."""
        assert parse_decision_marker("hello world") is None

    def test_parse_marker_only_no_details(self):
        """标记后无 Q/A 返回 None."""
        assert parse_decision_marker("[DECISION]") is None

    def test_parse_inline_q(self):
        """Q: 与 [DECISION] 在同一行."""
        text = " [DECISION] Q: 用什么缓存\nA: Redis\n"
        d = parse_decision_marker(text)
        assert d is not None
        assert d.question == "用什么缓存"
        assert d.answer == "Redis"

    def test_parse_optional_fields(self):
        """Alternatives 和 Rationale 可选."""
        text = "[DECISION] Q: 用什么缓存\nA: Redis\n"
        d = parse_decision_marker(text)
        assert d is not None
        assert d.question == "用什么缓存"
        assert d.answer == "Redis"
        assert d.alternatives == []
        assert d.rationale == ""

    def test_parse_empty_alternatives(self):
        """Alternatives 为空字符串时解析为空列表."""
        text = "[DECISION] Q: 用什么\nA: Redis\nAlternatives: \n"
        d = parse_decision_marker(text)
        assert d is not None
        assert d.alternatives == []

    def test_parse_multiple_decisions_first_only(self):
        """只解析第一条 [DECISION] 标记."""
        text = "[DECISION] Q: Q1\nA: A1\n\n[DECISION] Q: Q2\nA: A2\n"
        d = parse_decision_marker(text)
        assert d is not None
        assert d.question == "Q1"
        assert d.answer == "A1"
