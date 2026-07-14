"""Domain Action 工具路由器 (V15.2).

将大量独立工具按领域分组——每个领域暴露一个 MCP tool，
通过 action 参数路由到具体操作。避免 context 中列出全量工具。

对标: GenOrca/unreal-mcp Domain Action 模式。
253 个动作 → 21 个 MCP tool。LLM 更易理解。

Usage:
    router = DomainActionRouter()
    router.register_domain("file", {"read": read_handler, "write": write_handler})
    result = await router.dispatch("file", {"action": "read", "path": "/tmp/x"})
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

import structlog

logger = structlog.get_logger("orbit.tools.domain")

# 每个领域最大动作数——超过则建议拆分
MAX_ACTIONS_PER_DOMAIN = 30

ActionHandler = Callable[..., Any]


class DomainActionRouter:
    """按领域分组的工具路由器。

    WHY: 工具数增长后（Orbit 已 20+ MCP 工具），逐一列出
    消耗 context。Domain Action 将同领域操作收敛为一个 tool。
    """

    def __init__(self) -> None:
        self._domains: dict[str, dict[str, ActionHandler]] = defaultdict(dict)

    def register(
        self, domain: str, action: str, handler: ActionHandler
    ) -> None:
        """注册一个领域动作。

        Args:
            domain: 领域名（如 "file", "graph", "agent"）
            action: 动作名（如 "read", "write", "delete"）
            handler: 处理函数
        """
        if len(self._domains[domain]) >= MAX_ACTIONS_PER_DOMAIN:
            logger.warning(
                "domain_action_limit",
                domain=domain,
                count=len(self._domains[domain]),
            )
        self._domains[domain][action] = handler
        logger.debug("domain_action_registered", domain=domain, action=action)

    def unregister(self, domain: str, action: str | None = None) -> None:
        """注销领域或动作——action=None 时移除整个领域。

        WHY: 动态注册场景（插件/脚本）需要清理，防止内存泄漏。
        """
        if action is None:
            self._domains.pop(domain, None)
            logger.debug("domain_unregistered", domain=domain)
        else:
            self._domains.get(domain, {}).pop(action, None)
            logger.debug("domain_action_unregistered", domain=domain, action=action)

    def actions_for(self, domain: str) -> list[str]:
        """返回领域内所有可用动作名——供 LLM 生成 schema。"""
        return list(self._domains.get(domain, {}).keys())

    def domain_count(self) -> int:
        return len(self._domains)

    def total_actions(self) -> int:
        return sum(len(actions) for actions in self._domains.values())

    def has_domain(self, domain: str) -> bool:
        return domain in self._domains

    async def dispatch(
        self, domain: str, params: dict
    ) -> Any:
        """路由到具体动作。

        Args:
            domain: 领域名
            params: 含 "action" 键的参数 dict

        Returns:
            处理函数的返回值

        Raises:
            ValueError: 领域或动作不存在
        """
        action = params.get("action", "")
        if not action:
            raise ValueError(f"缺少 'action' 参数。可用动作: {self.actions_for(domain)}")

        handler = self._domains.get(domain, {}).get(action)
        if handler is None:
            available = self.actions_for(domain)
            raise ValueError(
                f"领域 '{domain}' 中无动作 '{action}'。可用: {available}"
            )

        return await handler(params)

    def generate_mcp_schema(self, domain: str) -> dict:
        """为领域生成 MCP tool schema——供 list_tools 使用。

        返回格式与 ToolRegistry.register() 兼容。
        """
        actions = self.actions_for(domain)
        if not actions:
            return {}

        return {
            "name": f"{domain}_tool",
            "description": f"{domain} 领域操作。action: {'/'.join(actions)}",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": actions,
                        "description": f"要执行的 {domain} 操作",
                    },
                    "params": {
                        "type": "object",
                        "description": "操作参数",
                    },
                },
                "required": ["action"],
            },
        }
