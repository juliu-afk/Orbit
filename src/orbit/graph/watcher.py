"""后台文件监视器——检测文件变更 → 自动增量索引。

WHY watchdog 而非 git hooks：文件变更即时反馈，不依赖手动 commit。
设计文档 §10.1 原本规划 Git post-commit 钩子——watchdog 作为更即时的替代方案。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

if TYPE_CHECKING:
    from orbit.graph.engines.code_graph import CodeGraphEngine

logger = structlog.get_logger("orbit.graph.watcher")

# Phase 3: 支持的语言扩展名
_WATCHED_EXTS = frozenset({".py", ".ts", ".tsx", ".sql"})


class GraphFileHandler(FileSystemEventHandler):
    """文件变更 → 调 CodeGraph incremental_update。"""

    def __init__(self, code_graph: "CodeGraphEngine") -> None:
        super().__init__()
        self._cg = code_graph

    def on_modified(self, event) -> None:
        if event.is_directory:
            return
        src = getattr(event, "src_path", "")
        if not src or Path(src).suffix not in _WATCHED_EXTS:
            return
        logger.info("watcher_file_changed", path=src)
        try:
            asyncio.run(self._cg.incremental_update(src))
        except Exception as e:
            logger.warning("watcher_update_failed", path=src, error=str(e))

    def on_created(self, event) -> None:
        self.on_modified(event)


class GraphWatcher:
    """后台 watchdog 线程——项目目录文件监听。

    用法::

        watcher = GraphWatcher(code_graph, "/path/to/project")
        watcher.start()
        # ... agent 工作 ...
        watcher.stop()
    """

    def __init__(self, code_graph: "CodeGraphEngine", watch_dir: str) -> None:
        self._cg = code_graph
        self._watch_dir = watch_dir
        self._observer: Observer | None = None

    def start(self) -> None:
        """启动后台监视线程。"""
        handler = GraphFileHandler(self._cg)
        self._observer = Observer()
        self._observer.schedule(handler, self._watch_dir, recursive=True)
        self._observer.start()
        logger.info("watcher_started", directory=self._watch_dir)

    def stop(self) -> None:
        """停止监视。"""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            logger.info("watcher_stopped")
