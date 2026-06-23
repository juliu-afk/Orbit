"""Step 5.5 PR #2——工具注册中心单元测试。"""

import pytest

from orbit.tools.models import ToolSchema
from orbit.tools.registry import (
    PermissionError,
    RateLimitError,
    ToolDeprecatedError,
    ToolNotFoundError,
    ToolRegistry,
)


def _echo_handler(params: dict) -> dict:
    return params


class TestToolRegistry:
    """工具注册——权限/限流/版本/废弃。"""

    def test_register_and_invoke(self) -> None:
        reg = ToolRegistry()
        reg.register(
            ToolSchema(name="query", version="1.0.0", allowed_agents=["QA"]),
            _echo_handler,
        )
        result = reg.invoke("query", {"key": "val"}, agent_name="QA")
        assert result == {"key": "val"}

    def test_permission_denied(self) -> None:
        reg = ToolRegistry()
        reg.register(
            ToolSchema(name="admin_tool", version="1.0.0", allowed_agents=["Admin"]),
            _echo_handler,
        )
        with pytest.raises(PermissionError):
            reg.invoke("admin_tool", {}, agent_name="QA")  # QA 不在白名单

    def test_empty_allowed_agents_allows_all(self) -> None:
        """空白名单 = 所有 Agent 可调用。"""
        reg = ToolRegistry()
        reg.register(ToolSchema(name="public", version="1.0.0"), _echo_handler)
        result = reg.invoke("public", {"x": 1}, agent_name="Anyone")
        assert result == {"x": 1}

    def test_rate_limit_enforced(self) -> None:
        """限流 2/min——第 3 次抛 RateLimitError。"""
        reg = ToolRegistry()
        reg.register(
            ToolSchema(name="limited", version="1.0.0", rate_limit=2),
            _echo_handler,
        )
        reg.invoke("limited", {}, agent_name="A")  # 1
        reg.invoke("limited", {}, agent_name="A")  # 2
        with pytest.raises(RateLimitError):
            reg.invoke("limited", {}, agent_name="A")  # 3 → 超限

    def test_get_latest_version(self) -> None:
        reg = ToolRegistry()
        reg.register(ToolSchema(name="x", version="1.0.0"), _echo_handler)
        reg.register(ToolSchema(name="x", version="2.0.0"), _echo_handler)
        assert reg.get_latest_version("x") == "2.0.0"

    def test_invoke_specific_version(self) -> None:
        reg = ToolRegistry()
        v1_called = []

        def v1_handler(p: dict) -> dict:
            v1_called.append(1)
            return p

        reg.register(ToolSchema(name="x", version="1.0.0"), v1_handler)
        reg.register(ToolSchema(name="x", version="2.0.0"), _echo_handler)
        reg.invoke("x", {}, agent_name="A", version="1.0.0")
        assert len(v1_called) == 1

    def test_tool_not_found(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(ToolNotFoundError):
            reg.invoke("nonexistent", {}, agent_name="A")

    def test_deprecated_tool_raises(self) -> None:
        reg = ToolRegistry()
        reg.register(
            ToolSchema(
                name="old", version="1.0.0",
                deprecated=True, deprecated_message="迁移到 new:v2",
            ),
            _echo_handler,
        )
        with pytest.raises(ToolDeprecatedError):
            reg.invoke("old", {}, agent_name="A")

    def test_list_tools(self) -> None:
        reg = ToolRegistry()
        reg.register(ToolSchema(name="a", version="1.0.0", description="工具 A"), _echo_handler)
        reg.register(ToolSchema(name="b", version="2.0.0", description="工具 B"), _echo_handler)
        tools = reg.list_tools()
        assert len(tools) == 2
        names = {t["name"] for t in tools}
        assert names == {"a", "b"}

    def test_get_invocations(self) -> None:
        reg = ToolRegistry()
        reg.register(ToolSchema(name="q", version="1.0.0"), _echo_handler)
        reg.invoke("q", {"a": 1}, agent_name="QA")
        reg.invoke("q", {"b": 2}, agent_name="QA")
        invs = reg.get_invocations()
        assert len(invs) == 2
        assert invs[0]["status"] == "success"
