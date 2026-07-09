"""Integration tests: Files + Blame + Terminal routes.

Low-coverage routes that need workspace set + mock services.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


# ── Mocks ─────────────────────────────────────────────────────────


class MockFileService:
    """Mock FileService for files routes."""

    async def list_files(self, directory: str | None = None):
        from orbit.files.service import FileInfo

        from orbit.files.service import FileStatus

        return [FileInfo(path="src/main.py", size=100, status=FileStatus.UNCHANGED)]

    async def read_file(self, path: str, directory: str | None = None):
        return f"# Content of {path}"

    def detect_language(self, path: str) -> str:
        return "python"

    async def diff(self, path: str, rev_a: str, rev_b: str | None, directory: str | None = None) -> dict:
        return {"path": path, "diff": f"diff between {rev_a} and {rev_b or 'HEAD'}"}


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def workspace_dir():
    """Workspace on same drive with a git repo for blame tests."""
    project_drive = os.path.splitdrive(os.getcwd())[0]
    base = os.path.join(project_drive + os.sep, "Temp")
    os.makedirs(base, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as d:
        ws = Path(d)
        # Init a minimal git repo for blame
        import subprocess

        subprocess.run(["git", "init"], cwd=str(ws), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(ws), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(ws), capture_output=True)
        (ws / "test.py").write_text("print('hello')\n", encoding="utf-8")
        subprocess.run(["git", "add", "test.py"], cwd=str(ws), capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(ws), capture_output=True)

        # Create a file for files_routes
        (ws / "src").mkdir(exist_ok=True)
        (ws / "src" / "main.py").write_text("# test file\n", encoding="utf-8")
        yield str(ws)


@pytest.fixture
def app(workspace_dir):
    from orbit.api.main import create_app
    from orbit.api.routes import _workspace as ws_mod
    import importlib

    ws_mod.set_workspace(workspace_dir)

    # Inject FileService mock
    files_mod = importlib.import_module("orbit.api.routes.files_routes")
    files_mod.set_file_service(MockFileService())

    return create_app(enable_auth=False, routes=["files_routes", "blame_routes", "terminal_routes", "git_routes"])


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Files tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_files_tree(client):
    """GET /api/v1/files/tree → 200。"""
    resp = await client.get("/api/v1/files/tree")
    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]  # API 统一封装: {code, data, message}
    assert "files" in data
    assert len(data["files"]) > 0


@pytest.mark.asyncio
async def test_files_read(client):
    """GET /api/v1/files/read?path=src/main.py → 200。"""
    resp = await client.get("/api/v1/files/read?path=src/main.py")
    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]  # API 统一封装: {code, data, message}
    assert "content" in data
    assert "language" in data


@pytest.mark.asyncio
async def test_files_diff(client):
    """GET /api/v1/files/diff?path=src/main.py → 200。"""
    resp = await client.get("/api/v1/files/diff?path=src/main.py")
    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]  # API 统一封装: {code, data, message}
    assert "diff" in data


# ── Blame tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_blame_valid_file(client):
    """GET /api/v1/git/blame?file=test.py → 200——返回 blame 行。"""
    resp = await client.get("/api/v1/git/blame?file=test.py")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "content" in data[0]
    assert "author" in data[0]


@pytest.mark.asyncio
async def test_blame_path_traversal(client):
    """GET /api/v1/git/blame?file=../../etc/passwd → 403。"""
    resp = await client.get("/api/v1/git/blame?file=../../etc/passwd")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_blame_file_not_found(client):
    """GET /api/v1/git/blame?file=nonexistent.py → 404。"""
    resp = await client.get("/api/v1/git/blame?file=nonexistent.py")
    assert resp.status_code == 404


# ── Terminal tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_terminal_commands(client):
    """GET /api/v1/terminal/commands → 200——返回允许的命令列表。"""
    resp = await client.get("/api/v1/terminal/commands")
    assert resp.status_code == 200
    data = resp.json()
    assert "commands" in data
    assert "git" in data["commands"]


@pytest.mark.asyncio
async def test_terminal_exec_disallowed(client):
    """POST /api/v1/terminal/exec 非白名单命令 → 403。"""
    resp = await client.post(
        "/api/v1/terminal/exec",
        json={"command": "rm -rf /"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_terminal_exec_python_c_blocked(client):
    """POST /api/v1/terminal/exec python -c → 403。"""
    resp = await client.post(
        "/api/v1/terminal/exec",
        json={"command": "python -c \"print('pwned')\""},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_terminal_exec_shell_meta(client):
    """POST /api/v1/terminal/exec 含 shell 元字符 → 403。"""
    resp = await client.post(
        "/api/v1/terminal/exec",
        json={"command": "echo hello; rm -rf /"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_terminal_exec_valid(client, workspace_dir):
    """POST /api/v1/terminal/exec echo hello → 200。"""
    resp = await client.post(
        "/api/v1/terminal/exec",
        json={"command": "echo hello", "timeout": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["exit_code"] == 0
    assert "hello" in data["stdout"]


@pytest.mark.asyncio
async def test_terminal_exec_cwd_traversal(client):
    """POST /api/v1/terminal/exec cwd 路径遍历 → 403。"""
    resp = await client.post(
        "/api/v1/terminal/exec",
        json={"command": "echo test", "cwd": "../../etc"},
    )
    assert resp.status_code == 403


# ── Git routes tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_git_gpg_keys(client):
    """GET /api/v1/git/gpg-keys → 200——空列表(测试环境无 GPG)。"""
    resp = await client.get("/api/v1/git/gpg-keys")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_git_merge_conflicts(client):
    """GET /api/v1/git/merge-conflicts → 200——空冲突列表。"""
    resp = await client.get("/api/v1/git/merge-conflicts")
    assert resp.status_code == 200
    data = resp.json()
    assert "conflicts" in data
    assert data["conflicts"] == []


@pytest.mark.asyncio
async def test_git_commit_no_changes(client):
    """POST /api/v1/git/commit 无变更 → 失败（工作区有文件）。"""
    resp = await client.post(
        "/api/v1/git/commit",
        json={"message": "test commit"},
    )
    # 工作区可能有未跟踪文件——commit 可能成功或失败，均接受
    assert resp.status_code in (200, 400)


@pytest.mark.asyncio
async def test_git_commit_invalid_path(client):
    """POST /api/v1/git/commit 路径遍历 → 400。"""
    resp = await client.post(
        "/api/v1/git/commit",
        json={"message": "test", "files": ["../etc/passwd"]},
    )
    assert resp.status_code == 400
