"""MCP 服务器管理 API 路由——前端 McpView 展示外部 MCP 服务器连接状态。

数据源：configs/mcp_clients.yaml（配置的服务器）+ ToolRegistry 运行时连接状态。
当前无外部 MCP 服务器时返回空列表（正常空态，非错误）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter

from orbit.tools.registry import ToolRegistry

router = APIRouter(prefix="/mcp", tags=["mcp"])
_workspace: str | None = None


def set_workspace(ws: str) -> None:
    global _workspace
    _workspace = ws


def _config_path() -> Path:
    ws = _workspace or os.getcwd()
    return Path(ws) / "configs" / "mcp_clients.yaml"


@router.get("/servers")
async def list_servers():
    """列出配置的 MCP 服务器及其运行状态。

    合并逻辑：yaml 定义服务器的静态配置（name/command/args/enabled）
    + registry 运行时连接状态（connected → status，tools_count）。
    """
    servers: list[dict[str, Any]] = []
    cfg_path = _config_path()
    configured: list[dict[str, Any]] = []
    if cfg_path.is_file():
        try:
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            configured = data.get("servers", []) or []
        except (OSError, yaml.YAMLError):
            configured = []

    status_map = ToolRegistry.get_instance().mcp_server_status()

    for s in configured:
        name = s.get("name", "")
        enabled = bool(s.get("enabled", True))
        live = status_map.get(name)
        # status 三态：未启用=disabled；已启用且已连接=connected；已启用但未连上=error
        if not enabled:
            status = "disabled"
        elif live and live.get("connected"):
            status = "connected"
        else:
            status = "error"
        servers.append(
            {
                "name": name,
                "command": s.get("command", ""),
                "args": s.get("args", []),
                "enabled": enabled,
                "status": status,
                "tools_count": (live or {}).get("tools_count", 0),
            }
        )

    return {"code": 0, "data": servers, "message": "ok"}
