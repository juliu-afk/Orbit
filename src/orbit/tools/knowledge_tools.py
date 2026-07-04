"""知识库工具——Agent 按需加载领域知识（Inkeep 借鉴 #3）。

WHY: Inkeep 的 Skill on-demand 加载——Agent 通过 tool 主动拉取知识，
而非全量预注入 prompt。减少上下文膨胀。
"""

from __future__ import annotations

from typing import Any

from orbit.knowledge.engine import KnowledgeEngine

# P2-4: 模块级单例——避免每次 tool call 都重建 KnowledgeEngine（含 DB 连接）
_knowledge_engine: KnowledgeEngine | None = None


def _get_engine() -> KnowledgeEngine:
    global _knowledge_engine
    if _knowledge_engine is None:
        _knowledge_engine = KnowledgeEngine()
    return _knowledge_engine


# JSON Schema——LLM 可见
LOAD_KNOWLEDGE_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "load_knowledge",
        "description": (
            "按需从知识图谱加载领域知识。仅在需要了解特定概念时调用，不要预加载。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": (
                        "知识领域: accounting(会计) | taxation(税务) | "
                        "auditing(审计) | compliance(合规) | software(软件工程)"
                    ),
                },
                "concept": {
                    "type": "string",
                    "description": "概念名，如 'CurrentRatio' 'DoubleEntry' 'Voucher'",
                },
            },
            "required": ["domain", "concept"],
        },
    },
}


def load_knowledge_handler(params: dict[str, Any]) -> dict[str, Any]:
    """load_knowledge tool 的实际执行函数。

    Args:
        params: {"domain": "accounting", "concept": "CurrentRatio"}

    Returns:
        {"found": true, "content": "...", "source_uri": "..."} 或
        {"found": false, "message": "概念 'X' 在领域 'Y' 中未找到"}
    """
    domain = params.get("domain", "")
    concept = params.get("concept", "")

    if not domain or not concept:
        return {
            "found": False,
            "message": "domain 和 concept 均为必填参数",
        }

    engine = _get_engine()
    result = engine.query_structured(domain, concept)
    return result


# ── AST 自注册 ────────────────────────────────────────────
# 被 ToolRegistry.discover() 扫描到 → 自动 import 触发注册

try:
    from orbit.tools.registry import get_registry

    _registry = get_registry()
    _registry.register(
        name="load_knowledge",
        toolset="knowledge",
        schema=LOAD_KNOWLEDGE_SCHEMA,
        handler=load_knowledge_handler,
        concurrency="safe",
        max_result_chars=8000,  # 知识片段通常 < 8KB
    )
except Exception:
    pass  # fail-open——load_knowledge 是便利工具，不是核心路径
