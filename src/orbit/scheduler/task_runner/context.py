"""TaskRunner 上下文构建 Mixin——_run_scoping + _build_context。

从 task_runner.py 拆分。
"""

from __future__ import annotations

import json as _json
from typing import Any

import structlog

from orbit.agents.context import TaskContext

logger = structlog.get_logger("orbit.scheduler.runner")


def _decide_test_scope(affected_files: dict) -> str:
    """从变更范围决定测试粒度."""
    changed = affected_files.get("changed", [])
    added = affected_files.get("added", [])
    total = affected_files.get("total", 0)
    if not changed and not added:
        return "unit_only"
    if total <= 3:
        return "unit_integration"
    return "unit_integration_e2e"


# V15.3 US2: 跨 Agent 上下文字段契约——spawn_task 时注入，全链路消费
# chat.py → runner.py(**kwargs) → context dict → PromptBuilder._build_context()
# WHY 显式定义: 接口契约文档——新增字段必须在此注册，避免隐性耦合
_TASK_CTX_NEW_FIELDS: dict[str, str] = {
    "conversation_history": "",    # _build_history_block() 输出
    "handoff_summary": "",         # 交接摘要（T2 模型生成，≤500 tokens）
    "session_id": "",              # 来源 session（跨 session 检索用）
    "user_goal": "",               # 用户原始目标（防漂移）
}


class TaskContextMixin:
    async def _run_scoping(self, task_id: str, context: dict[str, Any]) -> str:
        """SCOPING 状态——确定性变更范围分析 (Phase 2 Token节省).

        纯规则引擎——git diff + Python AST，0 LLM 调用。
        输出变更范围报告，决定后续测试粒度。
        fail-open: 任何异常返回 generic 报告，不阻塞任务。
        """
        import json as _json

        try:
            from orbit.context.scanners.affected_files import AffectedFilesScanner
            from orbit.context.scanners.import_deps import ImportDependencyScanner
        except ImportError:
            logger.warning("scoping_scanner_import_failed", task_id=task_id)
            return _json.dumps({"test_scope": "unit_integration", "note": "scanner_unavailable"})

        project_path = context.get("project_path", ".")
        scope_report: dict[str, Any] = {}

        # 扫描 1: git diff → 受影响文件
        try:
            af_scanner = AffectedFilesScanner()
            scope_report["affected_files"] = af_scanner.scan(project_path)
        except Exception as e:
            logger.warning("scoping_affected_files_failed", error=str(e))
            scope_report["affected_files"] = {"error": str(e), "total": 0}

        # 扫描 2: Python AST → import 依赖
        try:
            deps_scanner = ImportDependencyScanner()
            affected = scope_report.get("affected_files", {})
            changed = affected.get("changed", []) + affected.get("added", [])
            scope_report["import_deps"] = deps_scanner.scan(project_path, affected_files=changed)
        except Exception as e:
            logger.warning("scoping_import_deps_failed", error=str(e))
            scope_report["import_deps"] = {"error": str(e)}

        # 决策测试粒度
        affected = scope_report.get("affected_files", {})
        scope_report["test_scope"] = _decide_test_scope(affected)

        context["scope_report"] = scope_report
        # 注入 L2——供 Architect/Developer/Reviewer/QA 消费
        context.setdefault("l2", {})["scope_report"] = scope_report

        # v0.21: 接入 Context Builder 链——消费 scope_report 产出多维度上下文
        # WHY: PR #201 新增 9 个 Builder 但从未集成——scoping 后有结构化数据可消费
        try:
            from orbit.context.builders import build_all

            builder_inputs: dict[str, Any] = {
                "prd": context.get("prd", ""),
                "brief": context.get("brief", ""),
                "project_root": project_path,
                "affected_files": scope_report.get("affected_files", {}),
                "import_deps": scope_report.get("import_deps", {}),
                "test_scope": scope_report.get("test_scope", "unit_integration"),
                "keywords": context.get("keywords", []),
                "design": scope_report.get("design", {}),
            }
            builder_output = build_all(builder_inputs)
            scope_report["builder_context"] = builder_output
            context.setdefault("l2", {})["builder_context"] = builder_output
            logger.debug(
                "context_builders_complete",
                task_id=task_id,
                builders=len(builder_output),
            )
        except Exception:
            logger.debug("context_builders_failed", task_id=task_id)

        logger.info(
            "scoping_complete",
            task_id=task_id,
            files=affected.get("total", 0),
            test_scope=scope_report["test_scope"],
        )
        return _json.dumps(scope_report)


    def _build_context(self, task_id: str, context: dict[str, Any]) -> Any:
        """构建 L1-L5 TaskContext——G2 渐进式: 默认仅 Stage 1.

        WHY 渐进式: grill-me 模式——先给最少上下文，失败/不确定时再升级。
        Stage 1: L1+L3 核心字段 ~2K tokens（始终构建）。
        Stage 2: L2+L4 图谱+工作记忆（_run_agent 失败时 ctx.load_stage()）。
        Stage 3: L5 长期记忆（Agent 显式请求时）。
        """
        # G2: Stage 1 只构建 L1+L3——L2/L4/L5 延迟到 load_stage()
        # fast_lane 任务不会触发 Stage 2+，省 60-80% token
        return TaskContext(
            task_id=task_id,
            agent_name=context.get("agent_name", ""),
            model_tier=context.get("model_tier", ""),
            l1="遵循小企业会计准则; 禁止直接操作总账; 金额使用 Decimal",
            l2={},  # G2: 延迟到 Stage 2
            l3={
                "state": context.get("state", "UNKNOWN"),
                "prd": context.get("prd", ""),
                "artifacts": context.get("artifacts", {}),
            },
            l4={},  # G2: 延迟到 Stage 2
            l5=[],  # G2: 延迟到 Stage 3
        )

