"""编辑摇摆检测单元测试——P1 业务层减熵."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from orbit.scheduler.edit_stability import EditStabilityDetector, FileEditRecord


class TestEditStabilityDetector:
    """EditStabilityDetector——覆盖 record_edit / check / cleanup."""

    def test_record_edit_new_file(self) -> None:
        """首次编辑文件——创建历史记录."""
        d = EditStabilityDetector()
        d.record_edit("file1.py")
        assert "file1.py" in d._history
        assert len(d._history["file1.py"]) == 1
        assert d._history["file1.py"][0].file_path == "file1.py"

    def test_record_edit_with_agent_and_functions(self) -> None:
        """记录带 agent_id 和 changed_functions 的编辑."""
        d = EditStabilityDetector()
        d.record_edit("file1.py", agent_id="agent-a", changed_functions=["func1", "func2"])
        rec = d._history["file1.py"][0]
        assert rec.agent_id == "agent-a"
        assert rec.changed_functions == ["func1", "func2"]

    def test_record_edit_trims_old_records(self) -> None:
        """7 天前的记录被裁剪."""
        d = EditStabilityDetector()
        old = datetime.now(UTC) - timedelta(days=8)
        d._history["f.py"] = [FileEditRecord("f.py", timestamp=old)]
        d.record_edit("f.py")  # 触发裁剪
        records = d._history["f.py"]
        assert len(records) == 1  # 只有新记录
        assert records[0].timestamp > old

    def test_record_edit_triggers_cleanup_when_over_capacity(self) -> None:
        """超 MAX_HISTORY_FILES 且达到 cooldown → 触发 _cleanup_stale."""
        d = EditStabilityDetector()
        d.MAX_HISTORY_FILES = 2
        d.CLEANUP_COOLDOWN = 1
        # 3 个文件各 1 次编辑 = 3 > 2 容量，且 edit_since_cleanup=3 >= 1
        d.record_edit("a.py")
        d.record_edit("b.py")
        d.record_edit("c.py")
        assert len(d._history) <= 2

    def test_check_below_threshold_returns_early(self) -> None:
        """编辑次数 < HIGH_ENTROPY_THRESHOLD(4) → 直接返回无高熵."""
        d = EditStabilityDetector()
        d.record_edit("f.py")
        d.record_edit("f.py")
        d.record_edit("f.py")
        report = d.check("f.py")
        assert report.edit_count == 3
        assert report.is_high_entropy is False
        assert report.suggestion == ""

    def test_check_detects_ping_pong(self) -> None:
        """同一函数被反复修改 → has_ping_pong=True."""
        d = EditStabilityDetector()
        for _ in range(4):
            d.record_edit("f.py", agent_id="a", changed_functions=["func_x"])
        report = d.check("f.py")
        assert report.is_high_entropy is True
        assert report.has_ping_pong is True
        assert "回弹模式" in report.suggestion

    def test_check_detects_conflicting_agents(self) -> None:
        """3+ Agent 编辑同一文件 → conflicting_agents 不为空."""
        d = EditStabilityDetector()
        for agent in ["a1", "a2", "a3"]:
            for _ in range(2):
                d.record_edit("f.py", agent_id=agent, changed_functions=["func1"])
        report = d.check("f.py")
        assert report.is_high_entropy is True
        assert len(report.conflicting_agents) >= 3
        assert "Agent" in report.suggestion

    def test_check_unknown_file(self) -> None:
        """未记录的文件 → 返回空报告."""
        d = EditStabilityDetector()
        report = d.check("nonexistent.py")
        assert report.edit_count == 0
        assert report.is_high_entropy is False
        assert report.suggestion == ""

    def test_get_high_entropy_files_returns_only_high(self) -> None:
        """get_high_entropy_files 只返回高熵文件."""
        d = EditStabilityDetector()
        d.record_edit("low.py")
        for _ in range(5):
            d.record_edit("high.py")
        reports = d.get_high_entropy_files()
        paths = [r.file_path for r in reports]
        assert "high.py" in paths
        assert "low.py" not in paths

    def test_cleanup_stale_removes_empty(self) -> None:
        """_cleanup_stale 删除空记录."""
        d = EditStabilityDetector()
        d._history["empty.py"] = []
        d._history["valid.py"] = [FileEditRecord("valid.py")]
        d._cleanup_stale()
        assert "empty.py" not in d._history
        assert "valid.py" in d._history

    def test_cleanup_stale_trims_when_over_capacity(self) -> None:
        """超 MAX_HISTORY_FILES → 删到 90% 容量."""
        d = EditStabilityDetector()
        d.MAX_HISTORY_FILES = 10
        for i in range(15):
            d._history[f"f{i}.py"] = [FileEditRecord(f"f{i}.py")]
        d._cleanup_stale()
        target = int(10 * 0.9)
        assert len(d._history) <= target

    def test_check_full_report_with_multiple_issues(self) -> None:
        """多个问题并存时 suggestion 含所有信息."""
        d = EditStabilityDetector()
        for agent in ["a1", "a2", "a3"]:
            for _ in range(2):
                d.record_edit("f.py", agent_id=agent, changed_functions=["func1"])
        report = d.check("f.py")
        assert report.is_high_entropy is True
        assert report.has_ping_pong is True
        assert len(report.conflicting_agents) >= 3
        assert "建议重新确认需求" in report.suggestion
