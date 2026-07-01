"""安全权限数据模型。

5 层 deny-wins 架构:
  1. agent_role — Architect 不可写文件
  2. tool_category — 读写分类自动判定
  3. path_scope — workspace guard
  4. sandbox — Docker 隔离
  5. global_deny — 硬拒绝列表
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class PermissionLayer(StrEnum):
    """权限层枚举——从高到低。高序号 = 更优先（deny-wins）。"""

    AGENT_ROLE = "agent_role"  # 第1层: 角色权限
    TOOL_CATEGORY = "tool_category"  # 第2层: 工具分类
    PATH_SCOPE = "path_scope"  # 第3层: 路径范围
    SANDBOX = "sandbox"  # 第4层: 沙箱隔离
    GLOBAL_DENY = "global_deny"  # 第5层: 全局拒绝（最高优先级）


class ToolCategory(StrEnum):
    """工具分类——用于并发安全 + 权限判定。"""

    READ_ONLY = "read_only"  # grep/glob/read_file——可并发
    WRITE = "write"  # write_file/edit_file——串行
    SHELL = "shell"  # exec_command——必须串行+沙箱
    SENSITIVE = "sensitive"  # .env/credentials——全局拒绝


class SecurityPolicy(BaseModel):
    """单个 Agent 的安全策略。

    每层可以是 allow 列表或 deny 列表。
    deny 优先——显式拒绝覆盖所有 allow。
    """

    agent_role: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)  # glob patterns
    denied_paths: list[str] = Field(default_factory=list)  # glob patterns
    require_sandbox: bool = True  # shell 命令必须经沙箱
    sandbox_verified: bool = False  # P1-3: 调用方确认已走沙箱隔离（用于 exec_command 检查）
