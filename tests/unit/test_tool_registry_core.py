"""tools/registry/core.py extended unit tests — pure helpers + registry ops.
Coverage sprint B2-1: 70% → >=80%.

Targets: _path_to_module, _version_key, get_registry, ToolRegistry.register/get_tool.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orbit.tools.models import ToolPermission, ToolSchema
from orbit.tools.registry.core import (
    ToolRegistry,
    _path_to_module,
    _version_key,
    get_registry,
)


# ── _path_to_module ───────────────────────────────────────


class TestPathToModule:
    """Test _path_to_module() — file path → Python module path."""

    def test_src_orbit_path(self):
        """Standard src/orbit/... path → orbit.module.name."""
        assert _path_to_module("src/orbit/tools/filesystem.py") == "orbit.tools.filesystem"

    def test_orbit_prefix_path(self):
        """Path with orbit/ directly."""
        assert _path_to_module("orbit/api/routes.py") == "orbit.api.routes"

    def test_no_orbit_no_src(self):
        """Path without orbit/ or src/ — falls back to orbit.tools.<stem>."""
        assert _path_to_module("/some/random/tool.py") == "orbit.tools.tool"

    def test_windows_backslash(self):
        """Windows-style paths converted correctly."""
        result = _path_to_module("src\\orbit\\services\\calc.py")
        # Path normalizes slashes
        assert "orbit.services.calc" in result

    def test_nested_deep(self):
        """Deep nesting preserved."""
        assert _path_to_module("src/orbit/a/b/c/d/module.py") == "orbit.a.b.c.d.module"


# ── _version_key ──────────────────────────────────────────


class TestVersionKey:
    """Test _version_key() — semver string → sortable tuple."""

    def test_semver(self):
        assert _version_key("1.2.3") == (1, 2, 3)

    def test_major_only(self):
        assert _version_key("2") == (2,)

    def test_two_components(self):
        assert _version_key("3.14") == (3, 14)

    def test_sorting(self):
        """Higher versions sort higher."""
        versions = ["0.9.0", "1.0.0", "1.0.1", "1.1.0", "2.0.0"]
        result = sorted(versions, key=_version_key)
        assert result == ["0.9.0", "1.0.0", "1.0.1", "1.1.0", "2.0.0"]

    def test_invalid_fallback(self):
        """Non-semver strings → (0,)."""
        assert _version_key("not-a-version") == (0,)
        assert _version_key("") == (0,)

    def test_none_fallback(self):
        """None → (0,)."""
        assert _version_key(None) == (0,)  # type: ignore[arg-type]


# ── get_registry ──────────────────────────────────────────


class TestGetRegistry:
    """Test get_registry() — global singleton access."""

    def test_returns_same_instance(self):
        """Multiple calls return same instance."""
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2


# ── ToolRegistry.register ─────────────────────────────────


class TestToolRegistryRegister:
    """Test ToolRegistry.register() — tool registration + query."""

    @pytest.fixture
    def registry(self):
        """Clean registry instance."""
        return ToolRegistry()

    def test_register_and_get(self, registry):
        """Register a tool → can retrieve via get_schema()."""
        schema = ToolSchema(
            name="test_tool",
            version="1.0.0",
            description="A test tool",
            parameters={"x": {"type": "integer"}},
            permissions=[ToolPermission.READ],
        )

        async def handler(params):
            return {"result": params["x"] * 2}

        registry.register(schema, handler)

        result = registry.get_schema("test_tool")
        assert result is not None
        assert result.name == "test_tool"

    def test_register_duplicate_replaces(self, registry):
        """Registering same name twice replaces old handler."""
        schema_v1 = ToolSchema(name="dup", version="1.0.0", description="v1", permissions=[ToolPermission.READ])
        schema_v2 = ToolSchema(name="dup", version="2.0.0", description="v2", permissions=[ToolPermission.READ])

        async def handler_v1(params):
            return "v1"

        async def handler_v2(params):
            return "v2"

        registry.register(schema_v1, handler_v1)
        registry.register(schema_v2, handler_v2)

        tool = registry.get_schema("dup")
        assert tool.version == "2.0.0"

    def test_get_tool_not_found(self, registry):
        """Non-existent tool → KeyError."""
        with pytest.raises(Exception):
            registry.get_schema("nonexistent")

    def test_list_tools(self, registry):
        """list_tools() returns all registered tool schemas."""
        s1 = ToolSchema(name="t1", version="1.0.0", description="one", permissions=[ToolPermission.READ])
        s2 = ToolSchema(name="t2", version="1.0.0", description="two", permissions=[ToolPermission.WRITE])

        async def handler(params):
            return None

        registry.register(s1, handler)
        registry.register(s2, handler)

        tools = registry.list_tools()
        assert len(tools) >= 2

    def test_register_with_parameters(self, registry):
        """Schema with complex parameters is stored."""
        schema = ToolSchema(
            name="complex",
            version="1.0.0",
            description="Has parameters",
            parameters={
                "file_path": {"type": "string", "description": "Path to file"},
                "recursive": {"type": "boolean", "description": "Recurse into dirs", "default": False},
            },
            permissions=[ToolPermission.READ],
            allowed_agents=["developer", "qa"],
            timeout_seconds=30,
            is_async=True,
        )

        async def handler(params):
            return {"ok": True}

        registry.register(schema, handler)
        result = registry.get_schema("complex")
        assert result is not None
        assert result.parameters["file_path"]["type"] == "string"
        assert result.timeout_seconds == 30
        assert result.is_async is True

    def test_register_preserves_allowed_agents(self, registry):
        """allowed_agents list is preserved."""
        schema = ToolSchema(
            name="restricted",
            version="1.0.0",
            description="Restricted tool",
            permissions=[ToolPermission.READ],
            allowed_agents=["architect", "qa"],
        )

        async def handler(params):
            return None

        registry.register(schema, handler)
        result = registry.get_schema("restricted")
        assert "architect" in result.allowed_agents
        assert "qa" in result.allowed_agents

    def test_get_tool_names(self, registry):
        """list_tools() returns list of tool dicts with names."""
        s1 = ToolSchema(name="alpha", version="1.0.0", description="a", permissions=[ToolPermission.READ])

        async def handler(params):
            return None

        registry.register(s1, handler)

        tools = registry.list_tools()
        names = [t.get("name") if isinstance(t, dict) else t for t in tools]
        assert "alpha" in names
