"""决策日志覆盖补全测试——JSONL 完整性、错误恢复、边界格式.

US-B5 业务层减熵，覆盖现有测试未触及的 _load_all 异常路径.
"""

# ruff: noqa: S101  # 允许 plain assert

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from orbit.memory.decision_log import Decision, DecisionLog, parse_decision_marker


class TestDecisionLogLoadErrorPaths:
    """_load_all 异常路径——损坏 JSON、IO 错误."""

    @pytest.fixture
    def log(self, tmp_path: Path) -> DecisionLog:
        return DecisionLog(storage_dir=str(tmp_path))

    def test_corrupt_json_line_skipped(self, log: DecisionLog, tmp_path: Path) -> None:
        """JSONL 中含损坏行时跳过，不阻断正常行读取."""
        # 写入有效+无效+有效三条
        valid1 = json.dumps(
            {
                "question": "Q1",
                "answer": "A1",
                "alternatives": [],
                "rationale": "",
                "agent": "dev",
                "task_id": "t1",
                "timestamp": 100.0,
            },
            ensure_ascii=False,
        )
        corrupt = "not-json-at-all"
        valid2 = json.dumps(
            {
                "question": "Q2",
                "answer": "A2",
                "alternatives": [],
                "rationale": "",
                "agent": "dev",
                "task_id": "t2",
                "timestamp": 200.0,
            },
            ensure_ascii=False,
        )
        jsonl_path = tmp_path / "decisions.jsonl"
        jsonl_path.write_text(f"{valid1}\n{corrupt}\n{valid2}\n", encoding="utf-8")

        # 读取——损坏行应被跳过
        results = log.query(["Q"])
        assert len(results) == 2
        questions = {r.question for r in results}
        assert questions == {"Q1", "Q2"}

    def test_load_all_os_error_returns_empty(self, log: DecisionLog, tmp_path: Path) -> None:
        """文件不可读时 _load_all 返回空列表."""
        jsonl_path = tmp_path / "decisions.jsonl"
        jsonl_path.unlink(missing_ok=True)
        jsonl_path.mkdir()  # 目录代替文件 → read_text 抛 OSError

        assert log.query(["anything"]) == []
        assert log.find_conflicts("anything") == []
        assert log.recent(10) == []

    def test_record_empty_alternatives(self, log: DecisionLog) -> None:
        """alternatives 为空列表时 JSON 序列化正常."""
        d = Decision(
            question="Q",
            answer="A",
            alternatives=[],
            rationale="",
            agent="dev",
            task_id="t1",
            timestamp=time.time(),
        )
        log.record(d)
        recent = log.recent(1)
        assert len(recent) == 1
        assert recent[0].alternatives == []


class TestDecisionLogConflictEdgeCases:
    """find_conflicts 边界."""

    @pytest.fixture
    def log(self, tmp_path: Path) -> DecisionLog:
        return DecisionLog(storage_dir=str(tmp_path))

    def _decision(
        self,
        question: str = "用什么缓存",
        answer: str = "Redis",
        agent: str = "architect",
    ) -> Decision:
        return Decision(
            question=question,
            answer=answer,
            alternatives=[],
            rationale="",
            agent=agent,
            task_id="t1",
            timestamp=time.time(),
        )

    def test_find_conflicts_empty_question(self, log: DecisionLog) -> None:
        """空问题不匹配任何已有决策——无冲突."""
        log.record(self._decision(question="用什么缓存", answer="Redis"))
        conflicts = log.find_conflicts("", threshold=0.3)
        assert conflicts == []


class TestParseDecisionMarkerEdgeCases:
    """[DECISION] 标记解析边界——空、空白."""

    def test_parse_empty_text(self) -> None:
        """空文本返回 None."""
        assert parse_decision_marker("") is None

    def test_parse_whitespace_only(self) -> None:
        """纯空白文本返回 None."""
        assert parse_decision_marker("   \n  \t  ") is None
