"""历史代码图谱快照管理（PR10）。

在指定 git commit 上构建代码图谱——用**独立临时 SQLite db + 一次性 CodeGraphEngine**
在 git worktree 里建图，零影响生产 graph.db。带内存缓存避免重复构建。

WHY 独立引擎：build_index 会 clear_all 重建单一 graph.db，直接在生产库建历史图会覆盖当前图。
WHY git worktree：checkout 历史版本到临时目录，不扰乱运行中的工作树。
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import tempfile
import uuid
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from orbit.graph.engines.code_graph import CodeGraphEngine
from orbit.graph.models.nodes import Base as GraphBase

logger = structlog.get_logger("orbit.graph.snapshot")


class SnapshotManager:
    """按 git commit 构建/缓存历史代码图谱快照。"""

    def __init__(self, workspace: str):
        self._workspace = workspace
        # 缓存：commit_hash → {nodes, edges}。重启即丢（内存缓存，MVP 足够）。
        self._cache: dict[str, dict] = {}

    async def _git(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", self._workspace, *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        if proc.returncode != 0:
            raise RuntimeError(err.decode("utf-8", errors="replace")[:200])
        return out.decode("utf-8", errors="replace")

    async def list_commits(self, limit: int = 50) -> list[dict]:
        """返回最近 limit 个 commit 元数据（时间轴用）。无 git 仓库返回空。"""
        try:
            # %H|%s|%an|%cI —— hash|标题|作者|ISO日期，用 \x1f 分隔避免消息含 |
            fmt = "%H%x1f%s%x1f%an%x1f%cI"
            out = await self._git("log", f"-{limit}", f"--pretty=format:{fmt}")
        except (RuntimeError, TimeoutError, FileNotFoundError):
            return []
        commits = []
        for line in out.splitlines():
            parts = line.split("\x1f")
            if len(parts) == 4:
                commits.append({"hash": parts[0], "message": parts[1], "author": parts[2], "date": parts[3]})
        return commits

    async def build_at_commit(self, commit: str) -> dict:
        """在指定 commit 构建图谱，返回 {nodes, edges}。带缓存。

        隔离：git worktree 检出历史版本 → 临时 db + 一次性引擎建图 → 读取 → 清理。
        生产 graph.db 完全不受影响。
        """
        if commit in self._cache:
            return self._cache[commit]

        tmp_root = Path(tempfile.gettempdir()) / f"orbit_snap_{uuid.uuid4().hex[:8]}"
        wt_path = tmp_root / "wt"
        db_path = tmp_root / "snap.db"
        tmp_root.mkdir(parents=True, exist_ok=True)
        engine = None
        try:
            # 1. 检出历史版本到临时 worktree（detached，不建分支）
            await self._git("worktree", "add", "--detach", str(wt_path), commit)
            # 2. 独立临时 db + 引擎建图（零影响生产库）
            engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
            async with engine.begin() as conn:
                await conn.run_sync(GraphBase.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            snap_graph = CodeGraphEngine(factory)
            await snap_graph.build_index(str(wt_path))
            nodes = await snap_graph.get_all_nodes()
            edges = await snap_graph.get_all_edges()
            result = {"nodes": nodes, "edges": edges}
            self._cache[commit] = result
            return result
        finally:
            if engine is not None:
                await engine.dispose()
            # 清理 worktree + 临时目录
            with contextlib.suppress(RuntimeError, TimeoutError):
                await self._git("worktree", "remove", "--force", str(wt_path))
            shutil.rmtree(tmp_root, ignore_errors=True)
