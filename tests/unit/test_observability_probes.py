"""StartupProbeEngine + 探针函数单元测试。"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from orbit.observability.probes import (
    StartupProbeEngine,
    _check_docker_running,
    _docker_is_installed,
    _probe_agent,
    _probe_code_graph,
    _probe_environment,
    _probe_knowledge_engine,
    _probe_llm_gateway,
    _repair_environment,
)


def test_init():
    e = StartupProbeEngine()
    assert e is not None


# ── 纯探针函数 ──

@pytest.mark.asyncio
async def test_probe_environment_config():
    """环境和配置检查通过。"""
    result = await _probe_environment()
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_probe_agent_available():
    """Agent 工厂可导入。"""
    result = await _probe_agent()
    assert "Agent工厂" in result


@pytest.mark.asyncio
async def test_probe_llm_gateway_available():
    """LLM 网关模块可导入。"""
    result = await _probe_llm_gateway()
    assert "LLM网关" in result


@pytest.mark.asyncio
async def test_probe_knowledge_engine_available():
    """知识引擎模块可导入。"""
    result = await _probe_knowledge_engine()
    assert "知识引擎" in result


@pytest.mark.asyncio
async def test_probe_code_graph_available():
    """代码图谱模块可导入。"""
    result = await _probe_code_graph()
    assert "代码图谱" in result


# ── 自愈函数 ──

@pytest.mark.asyncio
async def test_repair_environment():
    """环境自愈返回默认配置。"""
    result = await _repair_environment()
    assert "默认环境配置" in result


# ── Docker 纯函数 ──

def test_docker_is_installed():
    """_docker_is_installed 不抛异常，返回 bool。"""
    result = _docker_is_installed()
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_check_docker_not_running_no_docker_binary():
    """Docker 未安装 → 返回 False。"""
    with patch("shutil.which", return_value=None):
        result = await _check_docker_running()
        assert result is False


@pytest.mark.asyncio
async def test_check_docker_running_ok():
    """Docker version 成功 → True。"""
    with patch("shutil.which", return_value="/fake/docker"):
        with patch("subprocess.run", return_value=Mock(returncode=0)):
            result = await _check_docker_running()
            assert result is True


# ── 导入失败场景 ──

@pytest.mark.asyncio
async def test_probe_agent_import_error():
    """Agent 导入失败 → RuntimeError。"""
    with patch.dict("sys.modules", {"orbit.agents.factory": None}):
        with pytest.raises(RuntimeError, match="Agent工厂"):
            await _probe_agent()


@pytest.mark.asyncio
async def test_probe_knowledge_engine_import_error():
    """知识引擎导入失败 → RuntimeError。"""
    with patch.dict("sys.modules", {"orbit.knowledge.engine": None}):
        with pytest.raises(RuntimeError, match="知识引擎"):
            await _probe_knowledge_engine()


# ── StartupProbeEngine ──

@pytest.mark.asyncio
async def test_engine_start_and_results():
    """完整探针运行 → results() 返回字典。"""
    engine = StartupProbeEngine()
    await engine.start()
    results = engine.results()
    assert isinstance(results, dict)
    assert "status" in results
    assert len(results) > 0


def test_engine_reset():
    """reset → 清空结果。"""
    engine = StartupProbeEngine()
    engine.reset()
    results = engine.results()
    assert isinstance(results, dict)
    assert results["status"] == "pending"
