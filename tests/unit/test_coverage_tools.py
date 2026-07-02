"""覆盖率补测——tools/registry.py (ToolRegistry)."""

from __future__ import annotations

import pytest

from orbit.tools.registry import ToolRegistry


class TestToolRegistry:
    def test_singleton(self):
        """get_instance() 返回同一个单例。"""
        a = ToolRegistry.get_instance()
        b = ToolRegistry.get_instance()
        assert a is b

    def test_register_tool_and_list(self):
        """register_tool → 角色可通过 list_for_role 获取。"""
        reg = ToolRegistry()
        reg.register_tool(
            name="read_file",
            toolset="fs",
            schema={"name": "read_file", "description": "read a file"},
            handler=lambda path: f"content of {path}",
        )
        # developer 角色包含 read_file
        schemas = reg.list_for_role("developer")
        names = [s.get("name") for s in schemas]
        assert "read_file" in names

    def test_list_unknown_role_returns_empty(self):
        """未定义角色 → 返回空列表——最小权限。"""
        reg = ToolRegistry()
        schemas = reg.list_for_role("unknown_role")
        assert schemas == []

    def test_clarifier_has_no_tools(self):
        """clarifier 角色 ROLE_TOOLS 为空——纯文本交互。"""
        reg = ToolRegistry()
        schemas = reg.list_for_role("clarifier")
        assert schemas == []

    def test_set_permission(self):
        """set_permission——注入权限引擎。"""
        reg = ToolRegistry()
        mock_perm = object()
        reg.set_permission(mock_perm)
        assert reg._permission is mock_perm

    def test_get_schemas(self):
        """get_schemas() 返回全部已注册工具 schema。"""
        reg = ToolRegistry()
        reg.register_tool(
            name="glob",
            toolset="search",
            schema={"name": "glob", "description": "find files"},
            handler=lambda p: [],
        )
        schemas = reg.get_schemas()
        assert len(schemas) >= 1

    def test_developer_has_all_basic_tools(self):
        """developer 角色预设读写+搜索工具。"""
        reg = ToolRegistry()
        reg.register_tool("read_file", "fs", {"name": "read_file"}, lambda: None)
        reg.register_tool("write_file", "fs", {"name": "write_file"}, lambda: None)
        reg.register_tool("grep", "search", {"name": "grep"}, lambda: None)
        reg.register_tool("glob", "search", {"name": "glob"}, lambda: None)

        schemas = reg.list_for_role("developer")
        names = {s.get("name") for s in schemas}
        assert "read_file" in names
        assert "write_file" in names

    def test_architect_read_only_tools(self):
        """architect 角色仅有只读工具——无 write_file。"""
        reg = ToolRegistry()
        reg.register_tool("read_file", "fs", {"name": "read_file"}, lambda: None)
        reg.register_tool("write_file", "fs", {"name": "write_file"}, lambda: None)

        schemas = reg.list_for_role("architect")
        names = {s.get("name") for s in schemas}
        assert "read_file" in names
        assert "write_file" not in names  # architect 无写权限
