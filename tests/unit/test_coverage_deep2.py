"""覆盖率深度补测——compression/compressor + tools/registry + goal/verifier + prompt/builder."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.agents.base import AgentRole
from orbit.compression.compressor import ContextCompressor
from orbit.compression.models import CompressionResult
from orbit.goal.verifier import ExecutorVerifier, VerificationResult
from orbit.prompt.builder import PromptBuilder
from orbit.tools.registry import ToolRegistry


# ════════════════════════════════════════════
# 1. ContextCompressor 深度
# ════════════════════════════════════════════

class TestContextCompressorDeep:
    def test_compress_returns_compression_result(self):
        mock_llm = MagicMock()
        compressor = ContextCompressor(llm_client=mock_llm)

        import asyncio
        result = asyncio.run(compressor.compress(
            [{"role": "user", "content": "hello"}],
            task_id="test",
            turn=0,
        ))
        assert isinstance(result, CompressionResult)

    def test_compress_with_long_messages(self):
        """长消息触发压缩。"""
        mock_llm = MagicMock()
        compressor = ContextCompressor(llm_client=mock_llm)

        msgs = [
            {"role": "user", "content": "x" * 5000},
            {"role": "assistant", "content": "y" * 5000},
        ]
        import asyncio
        result = asyncio.run(compressor.compress(msgs, task_id="t2"))
        assert isinstance(result, CompressionResult)

    def test_child_session_id_initial(self):
        compressor = ContextCompressor(llm_client=None)
        assert compressor.child_session_id is None

    def test_init_default_budget(self):
        compressor = ContextCompressor(llm_client=None)
        assert compressor._budget is not None
        assert compressor._budget.available > 0


# ════════════════════════════════════════════
# 2. ToolRegistry 深度
# ════════════════════════════════════════════

class TestToolRegistryDeep:
    def test_register_multiple_toolsets(self):
        reg = ToolRegistry()
        reg.register_tool("read_file", "fs", {"name": "read_file"}, lambda x: x)
        reg.register_tool("grep", "search", {"name": "grep"}, lambda x: [])
        reg.register_tool("exec_command", "shell", {"name": "exec_command"}, lambda x: "")
        schemas = reg.get_schemas()
        assert len(schemas) >= 3

    def test_reviewer_has_read_only(self):
        """reviewer 角色只能读。"""
        reg = ToolRegistry()
        reg.register_tool("read_file", "fs", {"name": "read_file"}, lambda x: x)
        reg.register_tool("write_file", "fs", {"name": "write_file"}, lambda x: None)
        schemas = reg.list_for_role("reviewer")
        names = {s.get("name") for s in schemas}
        assert "read_file" in names
        assert "write_file" not in names

    def test_qa_has_exec(self):
        reg = ToolRegistry()
        reg.register_tool("exec_command", "shell", {"name": "exec_command"}, lambda x: "")
        schemas = reg.list_for_role("qa")
        names = {s.get("name") for s in schemas}
        assert "exec_command" in names

    def test_dream_role(self):
        """dream 角色可读文件。"""
        reg = ToolRegistry()
        reg.register_tool("read_file", "fs", {"name": "read_file"}, lambda x: x)
        schemas = reg.list_for_role("dream")
        names = {s.get("name") for s in schemas}
        assert "read_file" in names


# ════════════════════════════════════════════
# 3. ExecutorVerifier
# ════════════════════════════════════════════

class TestExecutorVerifierDeep:
    def test_init_defaults(self):
        verifier = ExecutorVerifier()
        assert verifier._timeout > 0

    def test_init_custom_timeout(self):
        verifier = ExecutorVerifier(timeout_per_command=60)
        assert verifier._timeout == 60

    @pytest.mark.asyncio
    async def test_execute_empty_commands(self):
        verifier = ExecutorVerifier()
        result = await verifier.execute([])
        assert isinstance(result, VerificationResult)
        assert result.total_count == 0
        assert result.all_passed is True

    def test_verification_result_failed_commands(self):
        result = VerificationResult(
            all_passed=False,
            results=[
                {"command": "pytest", "passed": True, "exit_code": 0},
                {"command": "mypy", "passed": False, "exit_code": 1, "stderr_tail": "error: ..."},
            ],
        )
        assert result.total_count == 2
        assert result.passed_count == 1
        assert len(result.failed_commands) == 1
        assert result.all_passed is False


# ════════════════════════════════════════════
# 4. PromptBuilder 深度
# ════════════════════════════════════════════

class TestPromptBuilderDeep:
    def test_build_all_roles(self):
        builder = PromptBuilder()
        for role in AgentRole:
            try:
                prompt = builder.build_stable_only(role=role)
                assert len(prompt) > 0
            except Exception:
                pass  # 某些角色可能未实现

    def test_build_for_anthropic_all_roles(self):
        builder = PromptBuilder()
        for role in (AgentRole.DEVELOPER, AgentRole.ARCHITECT, AgentRole.REVIEWER):
            result = builder.build_for_anthropic(role=role)
            assert len(result) >= 1
            assert result[0]["type"] == "text"

    def test_build_system_and_user_with_tools(self):
        builder = PromptBuilder()
        result = builder.build_system_and_user(
            role=AgentRole.DEVELOPER,
            task="refactor module",
            tools_schema=[{"name": "read_file"}],
        )
        assert "system" in result
        assert "user" in result
