"""共享 workspace 访问器——blame/search/terminal/tests 四个路由文件重复定义。

P2: 抽取为共享模块，消除 4x 重复。
"""

from __future__ import annotations

_workspace_dir: str | None = None


def set_workspace(d: str) -> None:
    global _workspace_dir
    _workspace_dir = d


def _ws() -> str:
    if _workspace_dir is None:
        raise RuntimeError("workspace not set")
    return _workspace_dir
