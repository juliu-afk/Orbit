"""测试 ContextPrebuilder 基类 + 5 个子类 (Phase 2 Token节省)."""
from __future__ import annotations

import pytest

from orbit.context.prebuilder import ContextPrebuilder
from orbit.context.prebuilders.clarifier import ClarifierContextPrebuilder
from orbit.context.prebuilders.architect import ArchitectContextPrebuilder
from orbit.context.prebuilders.developer import DeveloperContextPrebuilder
from orbit.context.prebuilders.reviewer import ReviewerContextPrebuilder
from orbit.context.prebuilders.qa import QAContextPrebuilder


def make_raw_context(**overrides):
    """构造测试用 raw context——模拟 TaskContext.to_dict() 输出."""
    ctx = {
        "task_id": "test-001",
        "l1": "遵循会计准则; Decimal; 禁止硬编码密钥",
        "l2": {
            "affected_files": ["src/orbit/agents/react_agent.py", "frontend/src/App.vue"],
            "full_diff": "x" * 6000,  # 超大 diff
            "diff_summary": "修改 2 文件: react_agent.py + App.vue",
            "import_deps": {
                "cross_module_deps": {"agents": ["orbit.compression", "orbit.gateway"]},
            },
            "permission_changes": {
                "permissions_found": [{"file": "x.py", "line": 10, "permission": "admin:write"}],
                "unregistered": [],
            },
            "schema_changes": {"has_migration": True, "tables_added": ["new_table"]},
            "scope_report": {
                "affected_files": {"total": 2, "changed": ["a.py", "b.py"], "added": [], "deleted": []},
                "test_scope": "unit_integration",
            },
        },
        "l3": {"state": "CODING", "prd": "实现 context 预构建器"},
        "l4": {},
        "l5": [],
    }
    ctx.update(overrides)
    return ctx


# ── ContextPrebuilder 基类 ──────────────────────────────

class TestContextPrebuilderBase:
    """测试基类方法——通过具体子类测试（ABC 不可直接实例化）."""

    @staticmethod
    def _make_prebuilder():
        """用 ClarifierContextPrebuilder 测试基类方法——所有子类共享这些方法."""
        return ClarifierContextPrebuilder()

    def test_truncate_field_short(self):
        prebuilder = self._make_prebuilder()
        result = prebuilder._truncate_field("hello", max_chars=100)
        assert result == "hello"

    def test_truncate_field_long(self):
        prebuilder = self._make_prebuilder()
        long_text = "A" * 10000
        result = prebuilder._truncate_field(long_text, max_chars=100)
        assert len(result) < 200  # head+tail+标记 < 原始长度
        assert "truncated" in result

    def test_strip_keys(self):
        prebuilder = self._make_prebuilder()
        d = {"a": 1, "b": 2, "c": 3}
        result = prebuilder._strip_keys(d, {"b", "c"})
        assert result == {"a": 1}

    def test_build_for_role_returns_correct_type(self):
        cp = ContextPrebuilder.build_for_role("clarifier")
        assert isinstance(cp, ClarifierContextPrebuilder)
        cp = ContextPrebuilder.build_for_role("reviewer")
        assert isinstance(cp, ReviewerContextPrebuilder)
        cp = ContextPrebuilder.build_for_role("developer")
        assert isinstance(cp, DeveloperContextPrebuilder)

    def test_build_for_role_unknown_falls_back(self):
        cp = ContextPrebuilder.build_for_role("nonexistent")
        assert isinstance(cp, DeveloperContextPrebuilder)  # 兜底


# ── Clarifier ──────────────────────────────────────────

class TestClarifierContextPrebuilder:
    def test_strips_l2_code_context(self):
        cp = ClarifierContextPrebuilder()
        ctx = make_raw_context()
        result = cp.build(ctx)
        # Clarifier 应删除 l2（代码细节）
        assert "l2" not in result

    def test_truncates_prd(self):
        cp = ClarifierContextPrebuilder()
        ctx = make_raw_context()
        ctx["l3"]["prd"] = "X" * 5000
        result = cp.build(ctx)
        prd = result["l3"]["prd"]
        assert len(prd) <= 3200  # 3000 + 截断标记


# ── Architect ──────────────────────────────────────────

class TestArchitectContextPrebuilder:
    def test_strips_full_diff_and_source(self):
        cp = ArchitectContextPrebuilder()
        ctx = make_raw_context()
        result = cp.build(ctx)
        l2 = result.get("l2", {})
        assert "full_diff" not in l2
        assert "full_source" not in l2
        assert "file_contents" not in l2

    def test_injects_scope_summary(self):
        cp = ArchitectContextPrebuilder()
        ctx = make_raw_context()
        result = cp.build(ctx)
        l2 = result.get("l2", {})
        assert "scope_summary" in l2


# ── Developer ──────────────────────────────────────────

class TestDeveloperContextPrebuilder:
    def test_strips_full_diff(self):
        cp = DeveloperContextPrebuilder()
        ctx = make_raw_context()
        result = cp.build(ctx)
        l2 = result.get("l2", {})
        assert "full_diff" not in l2

    def test_limits_affected_files(self):
        cp = DeveloperContextPrebuilder()
        ctx = make_raw_context()
        ctx["l2"]["affected_files"] = ["f{}.py".format(i) for i in range(20)]
        result = cp.build(ctx)
        l2 = result.get("l2", {})
        assert len(l2.get("affected_files", [])) <= cp.MAX_AFFECTED_FILES


# ── Reviewer ──────────────────────────────────────────

class TestReviewerContextPrebuilder:
    def test_strips_full_diff(self):
        cp = ReviewerContextPrebuilder()
        ctx = make_raw_context()
        result = cp.build(ctx)
        l2 = result.get("l2", {})
        assert "full_diff" not in l2
        assert "full_source" not in l2

    def test_preserves_diff_summary(self):
        cp = ReviewerContextPrebuilder()
        ctx = make_raw_context()
        result = cp.build(ctx)
        l2 = result.get("l2", {})
        assert "diff_summary" in l2

    def test_truncates_long_diff_summary(self):
        cp = ReviewerContextPrebuilder()
        ctx = make_raw_context()
        ctx["l2"]["diff_summary"] = "X" * 5000
        result = cp.build(ctx)
        l2 = result.get("l2", {})
        assert len(l2.get("diff_summary", "")) <= 3200

    def test_injects_permission_summary(self):
        cp = ReviewerContextPrebuilder()
        ctx = make_raw_context()
        result = cp.build(ctx)
        l2 = result.get("l2", {})
        assert "permission_summary" in l2

    def test_injects_schema_summary(self):
        cp = ReviewerContextPrebuilder()
        ctx = make_raw_context()
        result = cp.build(ctx)
        l2 = result.get("l2", {})
        assert "schema_summary" in l2


# ── QA ─────────────────────────────────────────────────

class TestQAContextPrebuilder:
    def test_strips_full_diff(self):
        cp = QAContextPrebuilder()
        ctx = make_raw_context()
        result = cp.build(ctx)
        l2 = result.get("l2", {})
        assert "full_diff" not in l2

    def test_injects_test_scope_instruction(self):
        cp = QAContextPrebuilder()
        ctx = make_raw_context()
        result = cp.build(ctx)
        l2 = result.get("l2", {})
        assert "test_scope_instruction" in l2

    def test_scope_instruction_full_regression(self):
        instruction = QAContextPrebuilder._scope_instruction("full_regression")
        assert "全量回归" in instruction or "regression" in instruction.lower()

    def test_scope_instruction_smoke(self):
        instruction = QAContextPrebuilder._scope_instruction("smoke")
        assert "smoke" in instruction.lower() or "冒烟" in instruction
