"""Integration tests: 前后端契约断链修复 (A 批).

覆盖 5 个断链修复：
1. agent_llm 名字归一化——前端 PascalCase(ArchitectAgent) 应解析到规范名
2. files/write——编辑器存盘端点
3. mcp/servers——MCP 服务器列表
4. memory/list——记忆库浏览
5. lsp/diagnostics——诊断 HTTP GET
"""

from __future__ import annotations

import importlib
import os
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


class MockFileService:
    """Mock FileService——记录 write_file 调用。"""

    def __init__(self) -> None:
        self.written: dict[str, str] = {}

    async def write_file(self, path: str, content: str) -> None:
        self.written[path] = content


@pytest.fixture
def workspace_dir():
    project_drive = os.path.splitdrive(os.getcwd())[0]
    base = os.path.join(project_drive + os.sep, "Temp")
    os.makedirs(base, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as d:
        ws = Path(d)
        # 记忆库：放两个 md 文件供 memory/list
        mem = ws / ".orbit" / "memory"
        mem.mkdir(parents=True)
        (mem / "MEMORY.md").write_text("# 记忆索引\n", encoding="utf-8")
        (mem / "notes.md").write_text("笔记内容\n", encoding="utf-8")
        # 超大文件（>100KB）——验证 P2-1 截断
        (mem / "big.md").write_text("x" * 200_000, encoding="utf-8")
        # MCP 配置：空服务器列表
        (ws / "configs").mkdir()
        (ws / "configs" / "mcp_clients.yaml").write_text("servers: []\n", encoding="utf-8")
        yield str(ws)


@pytest.fixture
def app(workspace_dir):
    from orbit.api.main import create_app
    from orbit.lsp.service import DiagnosticService

    importlib.import_module("orbit.api.routes.mcp_routes").set_workspace(workspace_dir)
    importlib.import_module("orbit.api.routes.memory_routes").set_workspace(workspace_dir)
    importlib.import_module("orbit.api.routes.lsp_routes").set_diagnostic_service(DiagnosticService(workspace_dir))
    importlib.import_module("orbit.api.routes.files_routes").set_file_service(MockFileService())

    return create_app(
        enable_auth=False,
        routes=["agent_llm", "files_routes", "mcp_routes", "memory_routes", "lsp_routes"],
    )


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── 1. agent 命名归一化 ───────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "frontend_name",
    ["ArchitectAgent", "DeveloperAgent", "ReviewerAgent", "QAAgent", "ConfigAgent", "ClarifierAgent"],
)
async def test_agent_llm_pascalcase_resolves(client, frontend_name):
    """前端 PascalCase Agent 名不再 404（归一化到 snake_case）。"""
    resp = await client.get(f"/api/v1/agents/{frontend_name}/llm")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_agent_llm_unknown_still_404(client):
    """真正未知的 Agent 仍返回 404。"""
    resp = await client.get("/api/v1/agents/NotARealAgent/llm")
    assert resp.status_code == 404


# ── 2. files/write ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_files_write(client):
    """POST /files/write → 200 且 code=0。"""
    resp = await client.post("/api/v1/files/write", json={"path": "a.txt", "content": "hi"})
    assert resp.status_code == 200
    assert resp.json()["code"] == 0


# ── 3. mcp/servers ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_servers_empty(client):
    """GET /mcp/servers → 200，空配置返回空列表。"""
    resp = await client.get("/api/v1/mcp/servers")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] == []


# ── 4. memory/list ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_memory_list(client):
    """GET /memory/list → 200，返回工作区 .orbit/memory 下的 md 文件。"""
    resp = await client.get("/api/v1/memory/list")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    types = {item["type"] for item in body["data"]}
    assert {"MEMORY", "notes"} <= types


@pytest.mark.asyncio
async def test_memory_list_truncates_oversized(client):
    """P2-1: 超过 100KB 的记忆文件被截断，并标记 truncated=True。"""
    from orbit.api.routes.memory_routes import MAX_MEMORY_SIZE

    resp = await client.get("/api/v1/memory/list")
    big = next(item for item in resp.json()["data"] if item["type"] == "big")
    assert big["truncated"] is True
    assert len(big["text"]) == MAX_MEMORY_SIZE


# ── 5. lsp/diagnostics ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lsp_diagnostics_http(client):
    """GET /lsp/diagnostics → 200，返回 {diagnostics:{}}（无 file 时空结果）。"""
    resp = await client.get("/api/v1/lsp/diagnostics?task_id=t1")
    assert resp.status_code == 200
    assert "diagnostics" in resp.json()
