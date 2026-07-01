"""审计工厂——创建测试用审计条目。

用于快速构造 AuditEntry 和 CostRecord。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def create_audit_entry(
    trace_id: str | None = None,
    event: str = "task.state_change",
    task_id: str = "",
    details: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """创建审计条目 dict。

    Args:
        trace_id: 追踪 ID（None→自动生成 UUID）
        event: 事件类型
        task_id: 关联任务 ID
        details: 事件详情
    """
    if trace_id is None:
        trace_id = str(uuid.uuid4())

    return {
        "trace_id": trace_id,
        "event": event,
        "task_id": task_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": details or {},
        **kwargs,
    }


def create_cost_record(
    model: str = "deepseek/deepseek-v4-pro",
    prompt_tokens: int = 100,
    completion_tokens: int = 200,
    cost_usd: float = 0.0001,
    task_id: str = "",
) -> dict[str, Any]:
    """创建成本记录 dict。

    Args:
        model: 使用的模型
        prompt_tokens: 输入 token 数
        completion_tokens: 输出 token 数
        cost_usd: 美元成本
        task_id: 关联任务 ID
    """
    return {
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "cost_usd": cost_usd,
        "task_id": task_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
