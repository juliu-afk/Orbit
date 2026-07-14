"""Fable 5 tools — P2-2 semantic transfer + P0 deviation recording (V15.2).

Register as MCP tools so agents can:
- semantic_transfer_find: find cross-language equivalents of a reference
- semantic_transfer_link: link two implementations as semantically equivalent
- deviation_record: record a deviation from plan during task execution
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger("orbit.tools.fable5")


async def semantic_transfer_find(params: dict) -> list[dict]:
    """Find cross-language semantically equivalent implementations.

    Thariq: "The best reference is source code — even in another language."

    Args:
        params: {reference: str, target_language?: str}
    Returns:
        List of equivalent code nodes with language and description
    """
    from orbit.graph.meta_graph import SemanticTransfer

    reference = str(params.get("reference", ""))
    target_lang = str(params.get("target_language", "")) or None
    st = SemanticTransfer()
    return st.find(reference, target_lang)


async def semantic_transfer_link(params: dict) -> dict:
    """Link two implementations as semantically equivalent.

    Args:
        params: {source: str, target: str, source_language?: str, target_language?: str, description?: str}
    Returns:
        {status: "linked"}
    """
    from orbit.graph.meta_graph import SemanticTransfer

    st = SemanticTransfer()
    st.link(
        source=str(params.get("source", "")),
        target=str(params.get("target", "")),
        source_lang=str(params.get("source_language", "")),
        target_lang=str(params.get("target_language", "")),
        description=str(params.get("description", "")),
    )
    return {"status": "linked"}


async def deviation_record(params: dict) -> dict:
    """Record a deviation from plan during task execution (P0 Fable 5).

    Args:
        params: {task_id: str, planned: str, actual: str, reason: str,
                 alternatives?: [str], severity?: "major"|"critical", file_refs?: [str]}
    Returns:
        {status: "recorded"} or {status: "skipped"}
    """
    from orbit.integration.wiring import get_wiring

    wiring = get_wiring()
    if wiring is None:
        return {"status": "skipped", "reason": "wiring not initialized"}

    wiring.record_deviation(
        task_id=str(params.get("task_id", "")),
        planned=str(params.get("planned", "")),
        actual=str(params.get("actual", "")),
        reason=str(params.get("reason", "")),
        alternatives=params.get("alternatives"),
        severity=str(params.get("severity", "major")),
        file_refs=params.get("file_refs"),
    )
    return {"status": "recorded"}


# Tool schemas for MCP registration
SEMANTIC_TRANSFER_SCHEMAS = [
    {
        "name": "semantic_transfer_find",
        "description": "Find cross-language semantically equivalent implementations of a code reference",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reference": {"type": "string", "description": "Reference code identifier to look up"},
                "target_language": {"type": "string", "description": "Filter by target language (optional)"},
            },
            "required": ["reference"],
        },
    },
    {
        "name": "semantic_transfer_link",
        "description": "Link two implementations as semantically equivalent across languages",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source reference implementation path"},
                "target": {"type": "string", "description": "Target re-implementation path"},
                "source_language": {"type": "string", "description": "Language of source (e.g., rust)"},
                "target_language": {"type": "string", "description": "Language of target (e.g., python)"},
                "description": {"type": "string", "description": "What behavior/pattern is equivalent"},
            },
            "required": ["source", "target"],
        },
    },
    {
        "name": "deviation_record",
        "description": "Record a deviation from the implementation plan during task execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Current task ID"},
                "planned": {"type": "string", "description": "What was originally planned"},
                "actual": {"type": "string", "description": "What was actually done"},
                "reason": {"type": "string", "description": "Why the deviation occurred"},
                "alternatives": {"type": "array", "items": {"type": "string"}, "description": "Alternative approaches considered"},
                "severity": {"type": "string", "enum": ["major", "critical"], "description": "Deviation severity"},
                "file_refs": {"type": "array", "items": {"type": "string"}, "description": "Files involved"},
            },
            "required": ["task_id", "planned", "actual", "reason"],
        },
    },
]

HANDLER_MAP = {
    "semantic_transfer_find": semantic_transfer_find,
    "semantic_transfer_link": semantic_transfer_link,
    "deviation_record": deviation_record,
}


def register_fable5_tools(registry) -> int:
    """Register all Fable 5 tools into the given ToolRegistry.

    Returns: number of tools registered.
    """
    count = 0
    for schema in SEMANTIC_TRANSFER_SCHEMAS:
        name = schema["name"]
        handler = HANDLER_MAP.get(name)
        if handler is None:
            continue
        try:
            registry.register_tool(
                name=name,
                toolset="fable5",
                schema=schema,
                handler=handler,
                concurrency="safe",
            )
            count += 1
        except Exception:
            logger.warning("fable5_tool_register_failed", name=name, exc_info=True)
    logger.info("fable5_tools_registered", count=count)
    return count
