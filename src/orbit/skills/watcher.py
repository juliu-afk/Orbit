"""SkillWatcher——文件系统 watcher，检测 SKILL.md 变化 → 热更新。

使用 watchdog 库（Orbit 已有依赖）监听 skills/ 目录。
debounce 500ms 防止编辑器连续写触发多次重载。
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from orbit.skills.registry import SkillRegistry

logger = structlog.get_logger("orbit.skills.watcher")

# debounce 间隔（秒）——编辑器保存可能连续写多次
_DEBOUNCE_SECONDS = 0.5


class SkillWatcher:
    """文件系统 watcher——SKILL.md 变化 → SkillRegistry.reload()。

    Usage:
        watcher = SkillWatcher(registry, [skills_dir])
        watcher.start()
        # ... 文件变化时自动 reload ...
        watcher.stop()
    """

    def __init__(
        self,
        registry: SkillRegistry,
        watch_dirs: list[Path],
    ) -> None:
        self._registry = registry
        self._watch_dirs = [d for d in watch_dirs if d.exists()]
        self._observer: object | None = None
        self._running = False
        # debounce: 文件名 → 定时器
        self._debounce_timers: dict[str, threading.Timer] = {}

    def start(self) -> None:
        """启动 watcher。非阻塞——在独立线程中运行。"""
        if self._running:
            return
        if not self._watch_dirs:
            logger.warning("skill_watcher_no_dirs")
            return

        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            logger.warning("watchdog_not_installed——热更新不可用")
            return

        handler = _SkillFileHandler(self._registry, self._on_change)

        self._observer = Observer()
        for d in self._watch_dirs:
            self._observer.schedule(handler, str(d), recursive=False)
            logger.debug("skill_watcher_watching", dir=str(d))

        self._observer.start()
        self._running = True
        logger.info("skill_watcher_started", dirs=[str(d) for d in self._watch_dirs])

    def stop(self) -> None:
        """停止 watcher。"""
        # 取消所有待处理的 debounce 定时器
        for timer in self._debounce_timers.values():
            timer.cancel()
        self._debounce_timers.clear()

        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None
        self._running = False
        logger.info("skill_watcher_stopped")

    def _on_change(self, file_path: str) -> None:
        """文件变化回调——debounce 后触发 reload。

        WHY debounce: 编辑器保存文件时可能触发多次 on_modified 事件，
        用 debounce 确保只在最后一次写入后 reload。
        """
        # 取消之前的定时器
        if file_path in self._debounce_timers:
            self._debounce_timers[file_path].cancel()

        # 设置新的定时器
        timer = threading.Timer(_DEBOUNCE_SECONDS, self._do_reload, args=[file_path])
        self._debounce_timers[file_path] = timer
        timer.start()

    def _do_reload(self, file_path: str) -> None:
        """执行实际的 reload——从 debounce 定时器触发。"""
        # 清理定时器引用
        self._debounce_timers.pop(file_path, None)

        # 提取 Skill 名
        name = _extract_skill_name(file_path)
        try:
            self._registry.reload(name)
        except Exception:
            logger.error("skill_watcher_reload_error", file=file_path, exc_info=True)


class _SkillFileHandler:
    """watchdog 文件事件处理器——把 watchdog 事件转为 _on_change 回调。

    WHY 独立类: watchdog 要求 FileSystemEventHandler 子类。
    """

    def __init__(self, registry: SkillRegistry, callback) -> None:
        from watchdog.events import FileSystemEventHandler
        self._registry = registry
        self._callback = callback

    # 继承 FileSystemEventHandler 的 dispatch 方法
    def __getattr__(self, name):
        """动态继承——避免硬编码 import。"""
        if name in ("dispatch", "on_modified", "on_created"):
            return self._handle
        raise AttributeError(name)

    def _handle(self, event) -> None:
        """处理文件系统事件。"""
        src = getattr(event, "src_path", "")
        if src.endswith(".md"):
            self._callback(src)


def _extract_skill_name(file_path: str) -> str:
    """从 SKILL.md 文件路径提取 Skill 名称。

    e.g. "path/to/skills/review.md" → "review"
         "path/to/skills/compose:plan.md" → "compose:plan"
    """
    p = Path(file_path)
    return p.stem  # 去掉 .md 扩展名
