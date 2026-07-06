"""工具注册中心 (Step 5.5 PR #2 + Phase 1 升级).

声明式工具注册——权限隔离 + 滑动窗口限流 + 版本管理 + 废弃检测
+ AST 自注册 + JSON Schema (LLM可见) + 并发安全判定 + Doom Loop 检测.

对标: Hermes tools/registry.py:44 discover_builtin_tools()
     + Claude Code leaked 43 tools
     + OpenCode processor.ts:350 Doom Loop
"""

from __future__ import annotations

import ast
import importlib
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from orbit.tools.models import ToolInvocation, ToolSchema

logger = structlog.get_logger("orbit.tools")

ToolHandler = Callable[[dict[str, Any]], Any]


# ── 新增异常 ────────────────────────────────────────────


class PermissionError(Exception):
    """调用方不在 allowed_agents 白名单中。"""


class RateLimitError(Exception):
    """超出工具调用限流。"""


class ToolNotFoundError(Exception):
    """工具不存在或版本不匹配。"""


class ToolDeprecatedError(Exception):
    """工具已废弃, 返回迁移指引。"""


class DoomLoopError(Exception):
    """检测到死循环——连续 3 次同工具同参数。"""


class WorkspaceViolationError(Exception):
    """文件路径在工作区外——对标 OpenClaw wrapToolWorkspaceRootGuard()。"""


# ── ToolEntry——Hermes 风格工具元数据 ──────────────────────


@dataclass
class ToolEntry:
    """工具完整元数据——schema + handler + 并发标记 三位一体.

    对标 Hermes ToolEntry dataclass.
    """

    name: str
    toolset: str  # "filesystem" | "shell" | "search"
    schema: dict  # JSON Schema (LLM 可见), OpenAI function calling 格式
    handler: Callable  # 实际执行函数 (async)
    check_fn: Callable[[], bool] | None = None  # 运行时可用性检查
    concurrency: str = "safe"  # "safe" | "serial" | "never_parallel"
    max_result_chars: int = 10000  # >10K → 截断 (AC6b)


# ── 工具调用追踪 ─────────────────────────────────────────


@dataclass
class ToolCall:
    """单次工具调用记录——Doom Loop 检测用."""

    name: str
    args: dict[str, Any]
    result_preview: str = ""  # 截断后的结果前 200 字符

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ToolCall):
            return NotImplemented
        return self.name == other.name and self.args == other.args


# ── ToolRegistry ─────────────────────────────────────────

