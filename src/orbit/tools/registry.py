"""工具注册中心 (Step 5.5 PR #2).

声明式工具注册——权限隔离 + 滑动窗口限流 + 版本管理 + 废弃检测。
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from typing import Any

import structlog

from orbit.tools.models import ToolInvocation, ToolSchema

logger = structlog.get_logger("orbit.tools")

ToolHandler = Callable[[dict[str, Any]], Any]


class PermissionError(Exception):
    """调用方不在 allowed_agents 白名单中。"""


class RateLimitError(Exception):
    """超出工具调用限流。"""


class ToolNotFoundError(Exception):
    """工具不存在或版本不匹配。"""


class ToolDeprecatedError(Exception):
    """工具已废弃, 返回迁移指引。"""


class ToolRegistry:
    """工具注册中心——注册/查询/调用。

    用法:
        reg = ToolRegistry()
        reg.register(
            ToolSchema(name="query_knowledge", version="1.0.0",
                       allowed_agents=["QAAgent"], rate_limit=10),
            handler=lambda params: knowledge_store.query(**params),
        )
        result = reg.invoke("query_knowledge", {"concept": "CurrentRatio"},
                            agent_name="QAAgent")
    """

    def __init__(self) -> None:
        # 工具注册: name -> list[(version, schema, handler)]
        self._tools: dict[str, list[tuple[str, ToolSchema, ToolHandler]]] = {}
        # 限流状态: "name:version:agent" -> deque[timestamp]
        self._rate_limiters: dict[str, deque[float]] = {}
        # 调用审计
        self._invocations: list[ToolInvocation] = []

    def register(self, schema: ToolSchema, handler: ToolHandler) -> None:
        """注册工具——同一 name 可注册多版本。"""
        self._tools.setdefault(schema.name, []).append(
            (schema.version, schema, handler)
        )
        logger.info("tool_registered", name=schema.name, version=schema.version)

    def get_schema(self, name: str, version: str | None = None) -> ToolSchema:
        """获取工具 Schema——version 为空时返回最新版本。"""
        entries = self._tools.get(name)
        if not entries:
            raise ToolNotFoundError(f"工具不存在: {name}")
        if version:
            for v, schema, _ in entries:
                if v == version:
                    return schema
            raise ToolNotFoundError(f"工具 {name} 版本 {version} 不存在")
        # 返回最新版本
        entries.sort(key=lambda e: _version_key(e[0]), reverse=True)
        return entries[0][1]

    def get_latest_version(self, name: str) -> str:
        return self.get_schema(name).version

    def invoke(
        self, name: str, params: dict[str, Any],
        agent_name: str, version: str | None = None,
    ) -> Any:
        """调用工具——权限检查 + 限流检查 + 执行 + 审计。

        Raises:
            ToolNotFoundError: 工具/版本不存在
            PermissionError: 调用方不在白名单
            RateLimitError: 超出限流
            ToolDeprecatedError: 工具已废弃
        """
        start = time.time()
        schema = self.get_schema(name, version)

        # 废弃检查
        if schema.deprecated:
            raise ToolDeprecatedError(
                f"工具 {name} 已废弃: {schema.deprecated_message}"
            )

        # 权限检查——允许空白名单 (所有 Agent 可调用)
        if schema.allowed_agents and agent_name not in schema.allowed_agents:
            inv = ToolInvocation(
                tool_name=name, tool_version=schema.version,
                agent_name=agent_name, parameters=params,
                status="permission_denied",
                error=f"Agent {agent_name} 不在 {name} 白名单中",
                timestamp=start,
            )
            self._invocations.append(inv)
            raise PermissionError(inv.error)

        # 限流检查
        if schema.rate_limit > 0:
            key = f"{name}:{schema.version}:{agent_name}"
            if not self._check_rate_limit(key, schema.rate_limit):
                inv = ToolInvocation(
                    tool_name=name, tool_version=schema.version,
                    agent_name=agent_name, parameters=params,
                    status="rate_limited",
                    error=f"工具 {name} 已达限流 ({schema.rate_limit}/min)",
                    timestamp=start,
                )
                self._invocations.append(inv)
                raise RateLimitError(inv.error)

        # 执行 handler
        handler = self._get_handler(name, schema.version)
        try:
            result = handler(params)
            status = "success"
            error = ""
        except Exception as e:
            result = None
            status = "error"
            error = str(e)

        inv = ToolInvocation(
            tool_name=name, tool_version=schema.version,
            agent_name=agent_name, parameters=params,
            result=result, error=error, status=status,
            duration_ms=(time.time() - start) * 1000,
            timestamp=start,
        )
        self._invocations.append(inv)
        return result

    def get_invocations(self, limit: int = 50) -> list[dict[str, Any]]:
        return [i.to_dict() for i in self._invocations[-limit:]]

    def list_tools(self) -> list[dict[str, Any]]:
        """列出所有工具（每个 name 返回最新版本）。"""
        result = []
        for name in self._tools:
            schema = self.get_schema(name)
            result.append({
                "name": schema.name,
                "latest_version": schema.version,
                "description": schema.description,
                "deprecated": schema.deprecated,
                "rate_limit": schema.rate_limit,
            })
        return result

    # ── 内部 ─────────────────────────────────────────────

    def _get_handler(self, name: str, version: str) -> ToolHandler:
        entries = self._tools.get(name, [])
        for v, _, handler in entries:
            if v == version:
                return handler
        raise ToolNotFoundError(f"工具 {name} v{version} handler 缺失")

    def _check_rate_limit(self, key: str, limit: int) -> bool:
        """滑动窗口限流检查——窗口 60 秒, 清洗过期后判断。"""
        now = time.time()
        dq = self._rate_limiters.get(key)
        if dq is None:
            dq = deque()
            self._rate_limiters[key] = dq
        # 清洗窗口外记录
        cutoff = now - 60
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= limit:
            return False
        dq.append(now)
        return True


def _version_key(version: str) -> tuple[int, ...]:
    """semver 字符串 → 可排序元组。"""
    try:
        return tuple(int(x) for x in version.split("."))
    except (ValueError, AttributeError):
        return (0,)
