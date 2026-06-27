"""Actor 数据模型——对标 MiMo Code ActorRegistryTable.

WHY SQLite 而非 PostgreSQL: 子Agent 生命周期短暂（分钟级），
SQLite 零配置 + WAL 足够。
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, Field


class ActorStatus(StrEnum):
    """Actor 状态——对标 MiMo Code actor/registry.ts."""

    PENDING = "pending"  # 已分配，尚未启动
    RUNNING = "running"  # 正在执行
    IDLE = "idle"  # 执行完成（成功或失败）
    ZOMBIE = "zombie"  # 超时未响应（stale >5min）


class ActorOutcome(StrEnum):
    """Actor 执行结果。"""

    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"


class ActorRecord(BaseModel):
    """Actor 记录——存储在 SQLite actor_registry 表。

    WHY Pydantic: 序列化/反序列化 + 验证字段。
    """

    actor_id: str
    parent_task_id: str = ""  # 父任务 ID（根 Agent 创建）
    role: str = ""  # AgentRole value
    task: str = ""  # 任务描述
    status: ActorStatus = ActorStatus.PENDING
    outcome: ActorOutcome | None = None
    result: dict | None = None  # AgentOutput.result（完成时填充）
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    session_id: str | None = None  # 关联的会话 ID

    # 并发控制——对标 Claude Code subagent cap
    MAX_CONCURRENT: ClassVar[int] = 4
