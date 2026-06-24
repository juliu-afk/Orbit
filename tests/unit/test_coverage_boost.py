"""覆盖率补测——针对历史低覆盖文件。

提升 repo 总体覆盖率到 80% 门禁以上。
覆盖：launcher.py / gateway/client.py / gateway generate_stream / observability probes 关键路径。
"""

from __future__ import annotations

import asyncio

import pytest

from orbit.gateway.client import LLMClient
from orbit.gateway.schemas import LLMRequest


class TestLauncher:
    """launcher.py 入口函数。"""

    def test_main_is_callable(self) -> None:
        """launcher.main 可导入且为函数（不实际执行，避免起 uvicorn）。"""
        from orbit.launcher import main

        assert callable(main)

    def test_launcher_stdout_none_guard(self, monkeypatch) -> None:
        """sys.stdout=None 时不崩源（Windows GUI 子系统）。"""
        import os
        import sys

        from orbit import launcher

        # 模拟 stdout=None，但通过提前 return 避免真正跑 uvicorn
        monkeypatch.setattr(sys, "stdout", None)
        monkeypatch.setattr(sys, "stderr", None)
        # main 会尝试打开 devnull，然后 import uvicorn 跑服务
        # 我们只验证不崩：mock uvicorn 模块
        import types

        fake_uvicorn = types.ModuleType("uvicorn")
        fake_uvicorn.Config = lambda *a, **k: None
        fake_server = types.SimpleNamespace(run=lambda: None)
        fake_uvicorn.Server = lambda *a, **k: fake_server
        monkeypatch.setitem(__import__("sys").modules, "uvicorn", fake_uvicorn)
        launcher.main()  # 不崩即通过

    def test_launcher_normal_stdout(self, monkeypatch) -> None:
        """正常 stdout 环境下走逻辑。"""
        import types

        from orbit import launcher

        fake_uvicorn = types.ModuleType("uvicorn")
        fake_uvicorn.Config = lambda *a, **k: None
        fake_server = types.SimpleNamespace(run=lambda: None)
        fake_uvicorn.Server = lambda *a, **k: fake_server
        monkeypatch.setitem(__import__("sys").modules, "uvicorn", fake_uvicorn)
        launcher.main()


class TestGatewayClientStream:
    """gateway/client.py generate_stream 路径。"""

    @pytest.mark.asyncio
    async def test_generate_stream_no_monitor_no_litellm(self) -> None:
        """generate_stream 无 monitor 时退化（litellm 未装时抛 RuntimeError）。"""
        client = LLMClient()
        req = LLMRequest(prompt="test")
        with pytest.raises(Exception):
            await client.generate_stream(req, "task-1")

    def test_build_usage_zero(self) -> None:
        """_build_usage 零值输入返回零成本。"""
        client = LLMClient()

        class FakeUsage:
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0

        usage = client._build_usage("deepseek/deepseek-chat", FakeUsage())
        assert usage.cost_usd == 0.0
        assert usage.total_tokens == 0

    def test_build_usage_known_model(self) -> None:
        """_build_usage 已知模型计算成本。"""

        class FakeUsage:
            prompt_tokens = 1000
            completion_tokens = 500
            total_tokens = 1500

        client = LLMClient()
        usage = client._build_usage("deepseek/deepseek-chat", FakeUsage())
        assert usage.cost_usd > 0
        assert usage.prompt_tokens == 1000

    def test_build_usage_unknown_model(self) -> None:
        """未知模型成本为 0。"""

        class FakeUsage:
            prompt_tokens = 100
            completion_tokens = 50
            total_tokens = 150

        client = LLMClient()
        usage = client._build_usage("unknown/model", FakeUsage())
        assert usage.cost_usd == 0.0

    def test_get_usage_stats_empty(self) -> None:
        """无调用记录时返回零值。"""
        client = LLMClient()
        stats = client.get_usage_stats("no-task")
        assert stats.total_tokens == 0


class TestProbesBasic:
    """observability/probes.py 关键路径。"""

    def test_probe_functions_registered(self) -> None:
        """8 个探针函数全部注册。"""
        from orbit.observability.probes import _PROBE_FUNCTIONS

        expected = {
            "environment",
            "database",
            "agent",
            "llm_gateway",
            "sandbox",
            "knowledge_engine",
            "code_graph",
            "session_store",
        }
        assert set(_PROBE_FUNCTIONS.keys()) == expected

    def test_probe_environment(self) -> None:
        """environment 探针可执行。"""
        from orbit.observability.probes import _probe_environment

        result = asyncio.run(_probe_environment())
        assert isinstance(result, str)
        assert len(result) > 0

    def test_probe_agent(self) -> None:
        """agent 探针可执行。"""
        from orbit.observability.probes import _probe_agent

        result = asyncio.run(_probe_agent())
        assert isinstance(result, str)

    def test_probe_llm_gateway(self) -> None:
        """llm_gateway 探针可执行。"""
        from orbit.observability.probes import _probe_llm_gateway

        result = asyncio.run(_probe_llm_gateway())
        assert isinstance(result, str)
