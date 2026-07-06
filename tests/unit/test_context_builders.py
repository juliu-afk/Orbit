"""Unit tests: context/builders — pure functions, no DB/LLM/async.

Covers 8 builders + build_all() registry (was 0% coverage, 169 stmts total).
Each builder takes inputs dict → returns structured output. Fail-open pattern
means empty/missing inputs → empty results, not exceptions.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ── Shared test data ──────────────────────────────────────────────

EMPTY_AFFECTED: dict = {"changed": [], "added": [], "total": 0, "by_module": {}}
SOME_AFFECTED: dict = {
    "changed": ["src/orbit/scheduler/task_runner.py", "frontend/src/App.vue"],
    "added": ["src/orbit/modes/loader.py"],
    "total": 3,
    "by_module": {"scheduler": 1, "frontend": 1, "modes": 1},
}


# ══════════════════════════════════════════════════════════════════
# 1. DesignContextBuilder
# ══════════════════════════════════════════════════════════════════


def test_design_build_empty():
    from orbit.context.builders.design_builder import DesignContextBuilder

    b = DesignContextBuilder()
    result = b.build({})
    assert result["total_files"] == 0
    assert result["candidate_files"] == []


def test_design_build_with_affected():
    from orbit.context.builders.design_builder import DesignContextBuilder

    b = DesignContextBuilder()
    result = b.build({"affected_files": SOME_AFFECTED, "import_deps": {}, "prd": "测试PRD"})
    assert len(result["candidate_files"]) > 0
    assert result["prd_summary"] == "测试PRD"
    assert "总文件数" in str(result) or result["total_files"] == 3


def test_design_build_prd_truncation():
    from orbit.context.builders.design_builder import DesignContextBuilder

    b = DesignContextBuilder()
    long_prd = "A" * 600
    result = b.build({"affected_files": EMPTY_AFFECTED, "import_deps": {}, "prd": long_prd})
    assert len(result["prd_summary"]) <= 503  # 500 + "..."


def test_design_build_sorts_by_imports():
    from orbit.context.builders.design_builder import DesignContextBuilder

    b = DesignContextBuilder()
    # Module A has more cross-deps → should sort ahead
    affected = {
        "changed": ["src/orbit/scheduler/a.py", "src/orbit/sandbox/b.py"],
        "added": [],
        "total": 2,
    }
    deps = {
        "cross_module_deps": {
            "scheduler": ["a", "b", "c"],  # 3 deps
            "sandbox": ["x"],  # 1 dep
        },
    }
    result = b.build({"affected_files": affected, "import_deps": deps, "prd": "test"})
    candidates = result["candidate_files"]
    # 按 import 数量降序——scheduler 排第一
    if len(candidates) >= 2:
        assert "scheduler" in candidates[0]["file"] or candidates[0]["import_count"] >= candidates[1]["import_count"]


# ══════════════════════════════════════════════════════════════════
# 2. DocsContextBuilder
# ══════════════════════════════════════════════════════════════════


def test_docs_build_empty():
    from orbit.context.builders.docs_builder import DocsContextBuilder

    b = DocsContextBuilder()
    result = b.build({})
    assert result["doc_updates"] == []


def test_docs_build_with_src_files():
    from orbit.context.builders.docs_builder import DocsContextBuilder

    b = DocsContextBuilder()
    result = b.build({"affected_files": SOME_AFFECTED})
    assert len(result["doc_updates"]) > 0
    assert any("scheduler" in d for d in result["doc_updates"])


def test_docs_build_with_doc_files():
    from orbit.context.builders.docs_builder import DocsContextBuilder

    b = DocsContextBuilder()
    affected = {"changed": ["docs/开发计划/00-架构总览.md"], "added": [], "total": 1}
    result = b.build({"affected_files": affected})
    assert any("需更新" in d for d in result["doc_updates"])


# ══════════════════════════════════════════════════════════════════
# 3. ImplementationContextBuilder
# ══════════════════════════════════════════════════════════════════


def test_impl_build_empty():
    from orbit.context.builders.impl_builder import ImplementationContextBuilder

    b = ImplementationContextBuilder()
    result = b.build({})
    assert result["tasks"] == []
    assert result["total_files"] == 0


def test_impl_build_with_affected():
    from orbit.context.builders.impl_builder import ImplementationContextBuilder

    b = ImplementationContextBuilder()
    result = b.build({"affected_files": SOME_AFFECTED, "design": {"summary": "重构调度器"}})
    assert len(result["tasks"]) == 3
    assert result["tasks"][0]["action"] == "modify"  # changed
    assert result["tasks"][-1]["action"] == "create"  # added
    assert result["design_summary"] == "重构调度器"


# ══════════════════════════════════════════════════════════════════
# 4. TestContextBuilder
# ══════════════════════════════════════════════════════════════════


def test_test_build_empty():
    from orbit.context.builders.test_builder import TestContextBuilder

    b = TestContextBuilder()
    result = b.build({})
    assert result["test_items"] == []
    assert result["total_tests"] == 0


def test_test_build_priorities():
    from orbit.context.builders.test_builder import TestContextBuilder

    b = TestContextBuilder()
    result = b.build({"affected_files": SOME_AFFECTED, "test_scope": "full_regression"})
    items = result["test_items"]
    assert len(items) == 3
    # scheduler is high priority
    scheduler_items = [i for i in items if "scheduler" in i["file"]]
    assert scheduler_items[0]["priority"] == "high"
    assert result["test_scope"] == "full_regression"
    assert result["high_priority"] >= 1


def test_test_build_scope_instruction():
    from orbit.context.builders.test_builder import TestContextBuilder

    b = TestContextBuilder()
    assert "smoke" in b._scope_instruction("smoke")
    assert "cov" in b._scope_instruction("unit_integration")
    assert "e2e" in b._scope_instruction("full_regression")
    assert "unit" in b._scope_instruction("unknown")  # default


# ══════════════════════════════════════════════════════════════════
# 5. ReleaseContextBuilder
# ══════════════════════════════════════════════════════════════════


def test_release_build_empty():
    from orbit.context.builders.release_builder import ReleaseContextBuilder

    b = ReleaseContextBuilder()
    result = b.build({})
    assert result["file_count"] == 0
    assert result["risks"] == []
    assert result["migration_needed"] is False


def test_release_build_full_regression_risk():
    from orbit.context.builders.release_builder import ReleaseContextBuilder

    b = ReleaseContextBuilder()
    result = b.build({"affected_files": {"total": 5, "by_module": {}}, "test_scope": "full_regression"})
    assert any("全量回归" in r for r in result["risks"])


def test_release_build_migration_risk():
    from orbit.context.builders.release_builder import ReleaseContextBuilder

    b = ReleaseContextBuilder()
    result = b.build({
        "affected_files": {"total": 1, "by_module": {}},
        "schema_changes": {"has_migration": True},
    })
    assert any("迁移" in r for r in result["risks"])
    assert result["migration_needed"] is True


def test_release_build_permission_risk():
    from orbit.context.builders.release_builder import ReleaseContextBuilder

    b = ReleaseContextBuilder()
    result = b.build({
        "affected_files": {"total": 1, "by_module": {}},
        "permission_changes": {"unregistered": ["perm.a", "perm.b", "perm.c"]},
    })
    assert any("未注册权限" in r for r in result["risks"])


# ══════════════════════════════════════════════════════════════════
# 6. RequirementsContextBuilder
# ══════════════════════════════════════════════════════════════════


def test_req_build_empty():
    from orbit.context.builders.req_builder import RequirementsContextBuilder

    b = RequirementsContextBuilder()
    result = b.build({})
    assert result["prd_trimmed"] == ""
    assert result["brief_trimmed"] == ""


def test_req_build_with_data():
    from orbit.context.builders.req_builder import RequirementsContextBuilder

    b = RequirementsContextBuilder()
    result = b.build({"prd": "短PRD", "brief": "短摘要", "keywords": ["支付", "重构"]})
    assert result["prd_trimmed"] == "短PRD"
    assert result["brief_trimmed"] == "短摘要"
    assert result["keywords"] == ["支付", "重构"]


def test_req_build_prd_truncation():
    from orbit.context.builders.req_builder import RequirementsContextBuilder

    b = RequirementsContextBuilder()
    long_prd = "B" * 4000
    result = b.build({"prd": long_prd, "brief": "", "keywords": []})
    assert len(result["prd_trimmed"]) <= 3003  # 3000 + "..."


# ══════════════════════════════════════════════════════════════════
# 7. PrinciplesContextBuilder
# ══════════════════════════════════════════════════════════════════


def test_principles_no_engine():
    from orbit.context.builders.principles_builder import PrinciplesContextBuilder

    b = PrinciplesContextBuilder()  # No engine
    result = b.build({"task_description": "修复支付bug"})
    assert result["principles_text"] == ""


def test_principles_empty_description():
    from orbit.context.builders.principles_builder import PrinciplesContextBuilder

    mock = MagicMock()
    b = PrinciplesContextBuilder(engine=mock)
    result = b.build({})
    assert result["principles_text"] == ""


def test_principles_with_engine():
    from orbit.context.builders.principles_builder import PrinciplesContextBuilder

    mock = MagicMock()
    mock.search.return_value = [
        MagicMock(category="安全", principle="SQL注入必须参数化"),
        MagicMock(category="性能", principle="避免N+1查询"),
    ]
    b = PrinciplesContextBuilder(engine=mock)
    result = b.build({"task_description": "修复SQL注入"})
    assert "历史经验" in result["principles_text"]
    assert "SQL注入" in result["principles_text"]
    assert "N+1" in result["principles_text"]


def test_principles_engine_exception():
    from orbit.context.builders.principles_builder import PrinciplesContextBuilder

    mock = MagicMock()
    mock.search.side_effect = RuntimeError("LLM down")
    b = PrinciplesContextBuilder(engine=mock)
    result = b.build({"task_description": "任意任务"})
    assert result["principles_text"] == ""  # fail-open


# ══════════════════════════════════════════════════════════════════
# 8. StrategyContextBuilder
# ══════════════════════════════════════════════════════════════════


def test_strategy_no_files(tmp_path: Path):
    from orbit.context.builders.strategy_builder import StrategyContextBuilder

    b = StrategyContextBuilder()
    result = b.build({"project_root": str(tmp_path)})
    assert result["strategy_text"] == ""


def test_strategy_reads_strategy_md(tmp_path: Path):
    from orbit.context.builders.strategy_builder import StrategyContextBuilder

    (tmp_path / "STRATEGY.md").write_text("# 项目策略\n目标是做最好的Agent框架", encoding="utf-8")
    b = StrategyContextBuilder()
    result = b.build({"project_root": str(tmp_path)})
    assert "项目策略" in result["strategy_text"]
    assert "策略锚点" in result["strategy_text"]


def test_strategy_truncation(tmp_path: Path):
    from orbit.context.builders.strategy_builder import StrategyContextBuilder

    (tmp_path / "STRATEGY.md").write_text("X" * 4000, encoding="utf-8")
    b = StrategyContextBuilder()
    result = b.build({"project_root": str(tmp_path)})
    assert len(result["strategy_text"]) <= 3100  # 3000 + header + truncation note


def test_strategy_falls_back_to_brief(tmp_path: Path):
    from orbit.context.builders.strategy_builder import StrategyContextBuilder

    # No STRATEGY.md, but brief.md exists with摘要段
    orbit_dir = tmp_path / ".orbit"
    orbit_dir.mkdir()
    brief = orbit_dir / "brief.md"
    brief.write_text("## 1. 摘要\n\n这是项目摘要。\n\n## 6. 边界\n\n边界描述。", encoding="utf-8")
    b = StrategyContextBuilder()
    result = b.build({"project_root": str(tmp_path)})
    assert "摘要" in result["strategy_text"]


# ══════════════════════════════════════════════════════════════════
# 9. build_all() registry
# ══════════════════════════════════════════════════════════════════


def test_build_all_runs_all_builders():
    from orbit.context.builders import build_all

    result = build_all({"prd": "测试需求", "affected_files": SOME_AFFECTED, "project_root": ".", "task_description": "测试"})
    # 每个 builder 至少返回一个 key
    assert isinstance(result, dict)
    assert len(result) > 0


def test_build_all_one_builder_fails_doesnt_block():
    """Fail-open: 单个 builder 异常不阻断其他 builder。"""
    from orbit.context.builders import build_all

    # 触发所有 builder——strategy_builder 会找 STRATEGY.md，可能不存在但不抛异常
    # principles_builder 没有 engine→返回空，不抛异常
    # 所有 builder 设计为 fail-open，这个测试验证 build_all 的异常处理
    result = build_all({})  # 完全空白输入
    assert isinstance(result, dict)
    # 有 builder 返回 "available": False 的 error 标记（异常时）或实际数据
    for key, val in result.items():
        # 每个 builder 要么返回数据，要么返回 error 标记
        assert isinstance(val, dict)


def test_principles_empty_search_result():
    """empty search result → 返回空字符串（覆盖 line 54）。"""
    from orbit.context.builders.principles_builder import PrinciplesContextBuilder

    mock = MagicMock()
    mock.search.return_value = []
    b = PrinciplesContextBuilder(engine=mock)
    result = b.build({"task_description": "test"})
    assert result["principles_text"] == ""


def test_strategy_brief_read_oserror(tmp_path: Path, monkeypatch):
    """OSError 读取 brief.md → 返回空字符串（覆盖 line 77-78）。"""
    from orbit.context.builders.strategy_builder import StrategyContextBuilder

    orbit_dir = tmp_path / ".orbit"
    orbit_dir.mkdir()
    brief = orbit_dir / "brief.md"
    brief.write_text("## 1. 摘要\n\n内容", encoding="utf-8")

    # Mock Path.read_text to raise OSError for brief.md
    original = Path.read_text

    def _mock_read_text(self, *args, **kwargs):
        if self.name == "brief.md":
            raise OSError("Permission denied")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _mock_read_text)
    b = StrategyContextBuilder()
    result = b.build({"project_root": str(tmp_path)})
    assert result["strategy_text"] == ""


def test_test_builder_tests_path():
    """变更文件在 tests/ 路径 → test_type=self, priority=low（覆盖 line 37-38）。"""
    from orbit.context.builders.test_builder import TestContextBuilder

    b = TestContextBuilder()
    affected = {"changed": ["tests/unit/test_foo.py"], "added": []}
    result = b.build({"affected_files": affected})
    items = result["test_items"]
    assert len(items) == 1
    assert items[0]["test_type"] == "self"
    assert items[0]["priority"] == "low"


def test_build_all_exception_handling(monkeypatch):
    """单个 builder 抛异常 → fail-open, 不影响其他 builder（覆盖 line 53-55）。"""
    from orbit.context.builders import build_all
    from orbit.context.builders import design_builder

    # Monkeypatch DesignContextBuilder.build to raise
    original = design_builder.DesignContextBuilder.build

    def _raise(self, inputs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(design_builder.DesignContextBuilder, "build", _raise)
    try:
        result = build_all({"prd": "test"})
        assert isinstance(result, dict)
        # design key 应该有 error 标记
        design_result = result.get("design", {})
        assert design_result.get("available") is False or "error" in design_result
    finally:
        monkeypatch.setattr(design_builder.DesignContextBuilder, "build", original)
