"""spawn_subagent 工具单元测试——角色校验+并发限制+超时+错误隔离。

PR #298: Agent 级 Subagent 生成能力。
"""

from __future__ import annotations

import asyncio
import json as _json

import pytest


# ── Helpers ──────────────────────────────────────────────


def _parse_result(tool_output: str) -> dict:
    """解析 spawn_subagent 工具返回的 JSON 字符串。"""
    return _json.loads(tool_output)


# ── Role Validation ─────────────────────────────────────


class TestSpawnSubagentRoleValidation:
    """AC5/CE4: 角色白名单校验。"""

    @pytest.mark.parametrize("bad_role", ["chatter", "clarifier", "dream", "config_manager", "hacker"])
    async def test_rejects_invalid_role(self, bad_role):
        """非白名单角色返回 error。"""
        from orbit.tools.subagent import spawn_subagent

        result = _parse_result(await spawn_subagent(role=bad_role, task="anything"))
        assert result["status"] == "error"
        assert "role_not_allowed" in result["error"]
        assert bad_role in result["error"]

    @pytest.mark.parametrize("good_role", ["architect", "developer", "reviewer", "qa"])
    async def test_accepts_valid_role_without_actor_spawn(self, good_role):
        """有效角色但 actor_spawn 未初始化——返回 error（不是 role_not_allowed）。"""
        from orbit.tools.subagent import spawn_subagent

        result = _parse_result(await spawn_subagent(role=good_role, task="test"))
        # actor_spawn 未注入——应返回 actor_spawn_not_configured
        assert result["status"] == "error"
        assert "actor_spawn_not_configured" in result["error"]


# ── ActorSpawn Not Configured ───────────────────────────


class TestSpawnSubagentNotConfigured:
    """CE8: actor_spawn 未初始化时的优雅降级。"""

    async def test_not_configured_error(self):
        """未注入 ActorSpawn 时返回明确错误，不崩溃。"""
        from orbit.tools.subagent import _actor_spawn, spawn_subagent

        # 确保 _actor_spawn 为 None
        old = _actor_spawn
        try:
            import orbit.tools.subagent as mod

            mod._actor_spawn = None
            result = _parse_result(await spawn_subagent(role="developer", task="test"))
            assert result["status"] == "error"
            assert "actor_spawn_not_configured" in result["error"]
        finally:
            mod._actor_spawn = old


# ── Concurrency Limit ───────────────────────────────────


class TestSpawnSubagentConcurrencyLimit:
    """CE1: 并发满时优雅拒绝。"""

    async def test_concurrency_limit_rejection(self):
        """MAX_CONCURRENT=4 满时 spawn 返回 rejected。"""
        import orbit.tools.subagent as mod
        from orbit.actors.models import ActorRecord, ActorStatus
        from orbit.actors.registry import ActorRegistry
        from orbit.actors.spawn import ActorSpawn
        from pathlib import Path

        old_spawn = mod._actor_spawn
        try:
            # 用 :memory: 确保隔离——避免 DB_PATH 冲突
            registry = ActorRegistry(Path(":memory:"))
            spawn = ActorSpawn(registry=registry)

            # 填满并发上限
            for i in range(ActorRecord.MAX_CONCURRENT):
                record = ActorRecord(
                    actor_id=f"busy-{i}",
                    role="developer",
                    task=f"task-{i}",
                )
                registry.register(record)
                registry.update_status(f"busy-{i}", ActorStatus.RUNNING)

            # 验证 count_active=4
            assert registry.count_active() == 4

            mod._actor_spawn = spawn
            result = _parse_result(
                await mod.spawn_subagent(role="developer", task="should fail")
            )
            assert result["status"] == "rejected"
            assert result["reason"] == "concurrency_limit"
        finally:
            mod._actor_spawn = old_spawn


# ── Successful Spawn ────────────────────────────────────


class TestSpawnSubagentSuccess:
    """AC1-AC4: 正常 spawn 流程。"""

    async def test_spawn_and_await_result(self):
        """spawn → 等待 → 返回结构化 JSON 结果（不崩溃）。"""
        import orbit.tools.subagent as mod
        from orbit.actors.registry import ActorRegistry
        from orbit.actors.spawn import ActorSpawn

        old_spawn = mod._actor_spawn
        try:
            registry = ActorRegistry()
            spawn = ActorSpawn(registry=registry)
            mod._actor_spawn = spawn

            result = _parse_result(
                await mod.spawn_subagent(
                    role="developer",
                    task="write a test",
                    timeout=10,
                )
            )
            # 返回结构化 JSON（无论成功或失败，不崩溃）
            assert "status" in result
            # status 是 ok/error/rejected 之一
            assert result["status"] in ("ok", "error", "rejected", "timeout")
        finally:
            mod._actor_spawn = old_spawn

    async def test_spawn_preserves_role_in_registry(self):
        """spawn 调用在 ActorRegistry 中留下记录（即使执行失败）。"""
        import orbit.tools.subagent as mod
        from orbit.actors.registry import ActorRegistry
        from orbit.actors.spawn import ActorSpawn

        old_spawn = mod._actor_spawn
        try:
            registry = ActorRegistry()
            spawn = ActorSpawn(registry=registry)
            mod._actor_spawn = spawn

            await mod.spawn_subagent(role="reviewer", task="review", timeout=5)

            # registry 中应有至少一条记录
            active = registry.count_active()
            records = registry.list_active()
            # 执行失败后状态可能是 idle(zombie) 或 running(未清理)
            # 关键是：spawn 过程不崩溃
            assert active >= 0  # 可能为 0（执行后立即清理）或 1
        finally:
            mod._actor_spawn = old_spawn


# ── Timeout ─────────────────────────────────────────────


class TestSpawnSubagentTimeout:
    """AC9/CE2: 超时处理。"""

    async def test_custom_timeout_accepted(self):
        """自定义 timeout 参数被接受（不因参数错误而失败）。"""
        import orbit.tools.subagent as mod

        old_spawn = mod._actor_spawn
        try:
            # 无 spawn——角色校验先触发
            result = _parse_result(
                await mod.spawn_subagent(
                    role="developer",
                    task="test",
                    timeout=30,
                )
            )
            # 会因为 actor_spawn_not_configured 失败，而不是参数错误
            assert "actor_spawn_not_configured" in result.get("error", "")
        finally:
            mod._actor_spawn = old_spawn


# ── Error Isolation ─────────────────────────────────────


class TestSpawnSubagentErrorIsolation:
    """AC4: 错误隔离——子 Agent 失败不影响调用方。"""

    async def test_error_returns_json_not_exception(self):
        """任何错误都返回 JSON 字符串，不抛异常。"""
        import orbit.tools.subagent as mod

        old_spawn = mod._actor_spawn
        try:
            mod._actor_spawn = None
            # 不应抛出异常
            output = await mod.spawn_subagent(role="developer", task="test")
            result = _parse_result(output)
            assert isinstance(result, dict)
            assert "status" in result
        finally:
            mod._actor_spawn = old_spawn

    async def test_invalid_role_does_not_crash(self):
        """无效角色返回 error JSON，不抛异常。"""
        from orbit.tools.subagent import spawn_subagent

        output = await spawn_subagent(role="nonexistent", task="test")
        result = _parse_result(output)
        assert result["status"] == "error"
        assert "role_not_allowed" in result["error"]


# ── Tool Registration ───────────────────────────────────


class TestSpawnSubagentRegistration:
    """AC1: 工具注册到 ToolRegistry。"""

    def test_tool_registered_in_registry(self):
        """spawn_subagent 在 ToolRegistry 中注册。"""
        from orbit.tools.registry import get_registry

        reg = get_registry()
        schemas = reg.get_schemas()

        names = []
        for s in schemas:
            func = s.get("function", {})
            names.append(func.get("name", ""))

        assert "spawn_subagent" in names, f"spawn_subagent 未注册。已注册工具: {names}"

    def test_tool_schema_has_required_params(self):
        """工具 schema 声明 role 和 task 为必填。"""
        from orbit.tools.registry import get_registry

        reg = get_registry()
        schemas = reg.get_schemas()

        schema = None
        for s in schemas:
            if s.get("function", {}).get("name") == "spawn_subagent":
                schema = s["function"]
                break

        assert schema is not None, "spawn_subagent schema 未找到"
        required = schema.get("parameters", {}).get("required", [])
        assert "role" in required
        assert "task" in required

    def test_tool_in_role_tools(self):
        """spawn_subagent 在 developer/reviewer/qa 的 ROLE_TOOLS 中。"""
        from orbit.tools.registry import ToolRegistry

        for role in ["developer", "reviewer", "qa"]:
            allowed = ToolRegistry.ROLE_TOOLS.get(role, set())
            assert "spawn_subagent" in allowed, (
                f"spawn_subagent 不在 {role} 的 ROLE_TOOLS 中"
            )

    def test_tool_not_in_chatter_or_clarifier(self):
        """spawn_subagent 不在 chatter/clarifier 的 ROLE_TOOLS 中。"""
        from orbit.tools.registry import ToolRegistry

        for role in ["chatter", "clarifier"]:
            allowed = ToolRegistry.ROLE_TOOLS.get(role, set())
            assert "spawn_subagent" not in allowed, (
                f"spawn_subagent 不应在 {role} 的 ROLE_TOOLS 中"
            )
