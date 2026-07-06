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
                name="old",
                version="1.0.0",
                deprecated=True,
                deprecated_message="迁移到 new:v2",
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

    # -- 覆盖缺口 --

    def test_get_instance_singleton(self) -> None:
        """get_instance 返回同一实例。"""
        a = ToolRegistry.get_instance()
        b = ToolRegistry.get_instance()
        assert a is b

    def test_register_tool_new_api(self) -> None:
        """新 register_tool API——工具集+并发分类。"""
        reg = ToolRegistry()
        reg.register_tool(
            name="read",
            toolset="filesystem",
            schema={"name": "read", "parameters": {"path": "str"}},
            handler=_echo_handler,
        )
        schemas = reg.get_schemas()
        assert len(schemas) > 0

    def test_list_for_role_developer(self) -> None:
        """developer 角色可用的工具列表。"""
        reg = ToolRegistry()
        # 用新 API 注册——会自动添加到 ROLE_TOOLS
        reg.register_tool(
            name="read_file",
            toolset="filesystem",
            schema={"name": "read_file"},
            handler=_echo_handler,
        )
        tools = reg.list_for_role("developer")
        assert isinstance(tools, list)
        names = {t["name"] for t in tools}
        assert "read_file" in names

    def test_list_for_role_unknown(self) -> None:
        """未知角色 → 空列表（最小权限）。"""
        reg = ToolRegistry()
        tools = reg.list_for_role("nonexistent_role_xyz")
        assert tools == []

    def test_get_schema(self) -> None:
        reg = ToolRegistry()
        reg.register(ToolSchema(name="x", version="2.0.0"), _echo_handler)
        s = reg.get_schema("x")
        assert s is not None
        assert s.name == "x"
        assert s.version == "2.0.0"

    def test_get_schema_nonexistent(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(ToolNotFoundError):
            reg.get_schema("no_such_tool")

    def test_would_form_loop(self) -> None:
        reg = ToolRegistry()
        reg.record_tool_call("agent1", "edit", {"path": "a.py"})
        reg.record_tool_call("agent1", "edit", {"path": "a.py"})
        reg.record_tool_call("agent1", "edit", {"path": "a.py"})
        reg.record_tool_call("agent1", "edit", {"path": "a.py"})
        assert reg.would_form_loop("agent1", "edit", {"path": "a.py"}) is True

    def test_would_not_form_loop_yet(self) -> None:
        reg = ToolRegistry()
        reg.record_tool_call("agent1", "edit", {"path": "a.py"})
        assert reg.would_form_loop("agent1", "edit", {"path": "a.py"}) is False

    def test_clear_tool_history(self) -> None:
        reg = ToolRegistry()
        reg.record_tool_call("agent1", "edit", {"path": "a.py"})
        reg.clear_tool_history("agent1")
        assert reg.would_form_loop("agent1", "edit", {"path": "a.py"}) is False

    def test_should_parallelize_path_scoped(self) -> None:
        from orbit.tools.registry import ToolCall
        reg = ToolRegistry()
        calls = [
            ToolCall(name="edit_file", args={"path": "a.py"}),
            ToolCall(name="edit_file", args={"path": "b.py"}),
        ]
        parallel, serial = reg._should_parallelize(calls)
        # 不同路径 → 可并行
        assert len(parallel) == 2
        assert len(serial) == 0

    def test_should_parallelize_same_path_serial(self) -> None:
        from orbit.tools.registry import ToolCall
        reg = ToolRegistry()
        calls = [
            ToolCall(name="edit_file", args={"path": "a.py"}),
            ToolCall(name="edit_file", args={"path": "a.py"}),
        ]
        parallel, serial = reg._should_parallelize(calls)
        # 同路径 → 串行
        assert len(serial) > 0

    def test_should_parallelize_never_parallel(self) -> None:
        from orbit.tools.registry import ToolCall
        reg = ToolRegistry()
        calls = [
            ToolCall(name="exec_command", args={"cmd": "ls"}),
        ]
        parallel, serial = reg._should_parallelize(calls)
        assert len(parallel) == 0
        assert len(serial) > 0

    def test_version_key(self) -> None:
        from orbit.tools.registry import _version_key
        assert _version_key("2.0.0") > _version_key("1.0.0")
        assert _version_key("1.10.0") > _version_key("1.2.0")
        assert _version_key("1.0.0") == _version_key("1.0.0")
