"""Session 数据模型——会话 + 聊天消息。

WHY dataclass 而非 Pydantic：registry 层纯数据传递，不参与 API 校验。
API 层用独立 Pydantic schema（见 api/routes/sessions.py）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionRecord:
    """会话记录——绑定一个项目。"""

    session_id: str  # UUID4 hex, 32 chars
    project_name: str  # FK → projects.name (denormalized)
    local_path: str = ""  # 项目路径，来自 projects 表 JOIN
    title: str = ""
    status: str = "active"  # active | archived
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_name": self.project_name,
            "local_path": self.local_path,
            "title": self.title,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class ChatMessageRecord:
    """聊天消息记录——归属一个 Session。

    V16.0 Phase A: role统一assistant + Part粒度 + 工具调用 + 持久化状态
    """

    session_id: str = ""
    role: str = ""  # user | assistant | system (统一为 assistant, 不再用 agent)
    content: str = ""
    candidates: list[dict[str, Any]] = field(default_factory=list)
    cross_project_warning: str | None = None
    created_at: float = 0.0
    id: int | None = None  # DB 自增，插入前为 None
    # V16.0 Phase A: 消息持久化 + Part粒度 + 结构化输出
    status: str = "sent"  # pending | sent | error
    parts: list[dict[str, Any]] = field(default_factory=list)  # [{"type":"text","content":""},{"type":"tool",...}]
    structured_output: str = ""  # JSON——PRD/其他结构化数据
    # V16.0 Phase E: Token追踪
    input_tokens: int = 0
    output_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "candidates": self.candidates,
            "cross_project_warning": self.cross_project_warning,
            "created_at": self.created_at,
            "status": self.status,
            "parts": self.parts,
            "structured_output": self.structured_output,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }
