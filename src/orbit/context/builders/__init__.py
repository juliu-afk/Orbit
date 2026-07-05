"""Context Builder——映射 Token 节省报告 Phase 2 的 7 个脚本.

每个 Builder 是纯函数——输入结构化数据，输出可直接注入 Agent context 的 dict。
不用 LLM——正则/AST/文件系统操作。

v0.21: build_all() 接入 _run_scoping()——消费 scope_report 产出多维度上下文，
供 Architect/Developer/Reviewer/QA 各阶段 Agent 消费。
"""

from __future__ import annotations

from typing import Any

from orbit.context.builders.debug_builder import DebugContextBuilder
from orbit.context.builders.design_builder import DesignContextBuilder
from orbit.context.builders.docs_builder import DocsContextBuilder
from orbit.context.builders.impl_builder import ImplementationContextBuilder
from orbit.context.builders.principles_builder import PrinciplesContextBuilder
from orbit.context.builders.release_builder import ReleaseContextBuilder
from orbit.context.builders.req_builder import RequirementsContextBuilder
from orbit.context.builders.strategy_builder import StrategyContextBuilder
from orbit.context.builders.test_builder import TestContextBuilder

# 全部 Builder 注册表——按优先级排序（strategy 第一：Agent 最先看到项目目标）
_BUILDERS: list[tuple[str, Any]] = [
    ("strategy", StrategyContextBuilder()),
    ("requirements", RequirementsContextBuilder()),
    ("design", DesignContextBuilder()),
    ("implementation", ImplementationContextBuilder()),
    ("test", TestContextBuilder()),
    ("debug", DebugContextBuilder()),
    ("docs", DocsContextBuilder()),
    ("principles", PrinciplesContextBuilder()),
    ("release", ReleaseContextBuilder()),
]


def build_all(inputs: dict[str, Any]) -> dict[str, Any]:
    """运行全部 Context Builder——fail-open：单个 builder 异常不阻断其他。

    Args:
        inputs: 含 prd/brief/affected_files/import_deps/project_root/design 等字段

    Returns:
        {"strategy": {...}, "requirements": {...}, ...} —— 每个 key 对应一个 builder 输出
    """
    result: dict[str, Any] = {}
    for name, builder in _BUILDERS:
        try:
            output = builder.build(inputs)
            if output:  # 空 dict/section 跳过
                result[name] = output
        except Exception:
            # Builder 不可用时静默降级——不阻断任务
            result[name] = {"error": "builder_failed", "available": False}
    return result
