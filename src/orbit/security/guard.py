"""WorkspaceGuard——文件操作路径安全守卫。

对标 OpenClaw wrapToolWorkspaceRootGuard:
  Path.resolve() 必须在 project_root 内，否则拒绝。

WHY resolve(): 防止 ../../../etc/passwd 类路径遍历攻击。
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from orbit.security.constants import SENSITIVE_FILE_GLOB  # P1-6: 统一常量


class WorkspaceGuard:
    """工作区路径守卫。

    Usage:
        guard = WorkspaceGuard("/path/to/project")
        guard.validate("/path/to/project/src/file.py")  # OK
        guard.validate("/etc/passwd")                   # raises ValueError
    """

    # P1-6: 统一到 security/constants.py
    ALWAYS_DENY_PATTERNS = SENSITIVE_FILE_GLOB

    def __init__(self, project_root: str | Path | None = None) -> None:
        self._root = Path(project_root).resolve() if project_root else None

    @property
    def root(self) -> Path | None:
        return self._root

    def validate(self, path: str, allow_outside: bool = False) -> Path:
        """验证路径在工作区内。

        Args:
            path: 要验证的文件路径
            allow_outside: True = 允许访问工作区外（仅限 read_file）

        Returns:
            解析后的绝对路径

        Raises:
            ValueError: 路径不安全
        """
        # 1. 路径遍历检测——在 resolve() 前拒绝 ../（P1-2）
        if ".." in Path(path).parts:
            raise ValueError(f"安全拒绝——路径遍历攻击: {path}")

        resolved = Path(path).resolve()

        # 2. 检查全局拒绝模式
        fname = resolved.name
        for pattern in self.ALWAYS_DENY_PATTERNS:
            if fnmatch.fnmatch(fname, pattern):
                raise ValueError(f"安全拒绝——禁止访问敏感文件: {fname}")

        # 3. 工作区边界检查
        if self._root and not allow_outside:
            try:
                resolved.relative_to(self._root)
            except ValueError as err:
                raise ValueError(f"安全拒绝——路径在工作区外: {path} (root={self._root})") from err

        return resolved
