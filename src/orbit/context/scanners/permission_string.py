"""权限字符串扫描器——正则扫 Python 文件 → 比对注册表.

复用 Token 节省报告 Phase 1 的 scan_permissions.py 模式。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from orbit.context.scanners.base import BaseScanner

# 匹配 require_permission("xxx") 或 has_permission("xxx") 调用
_PERMISSION_PATTERN = re.compile(
    r'(?:require|has|check)_permission\s*\(\s*["\']([^"\']+)["\']'
)


class PermissionStringScanner(BaseScanner):
    """正则扫描 Python 文件 → 提取权限字符串 + 比对注册表。

    输出: {
        "permissions_found": [{"file": "...", "line": 42, "permission": "admin:write"}, ...],
        "unregistered": [...],   # 使用了但未在注册表中
        "total": 5,
        "note": "no rbac registry found" | ""
    }
    """

    name = "permission_string"

    def scan(self, project_path: str, **kwargs: Any) -> dict[str, Any]:
        result: dict[str, Any] = {
            "permissions_found": [],
            "unregistered": [],
            "total": 0,
        }

        root = Path(project_path)

        # 收集所有已知权限（从可能的 RBAC 注册表）
        known = self._collect_known_permissions(root)

        # 扫描 Python 文件
        try:
            src_dir = root / "src"
            if not src_dir.exists():
                src_dir = root  # 回退到项目根

            for py_file in src_dir.rglob("*.py"):
                # 跳过 __pycache__ 和 venv
                if "__pycache__" in str(py_file) or ".venv" in str(py_file):
                    continue
                try:
                    content = py_file.read_text(encoding="utf-8", errors="replace")
                    for lineno, line in enumerate(content.splitlines(), 1):
                        # 跳过注释行
                        stripped = line.strip()
                        if stripped.startswith("#"):
                            continue
                        matches = _PERMISSION_PATTERN.findall(line)
                        for perm in matches:
                            rel_path = str(py_file.relative_to(root)).replace("\\", "/")
                            entry = {"file": rel_path, "line": lineno, "permission": perm}
                            result["permissions_found"].append(entry)
                            # 检查是否已注册
                            if known and perm not in known:
                                result["unregistered"].append(entry)
                except (UnicodeDecodeError, OSError):
                    continue

            result["total"] = len(result["permissions_found"])
            if not known:
                result["note"] = "no rbac registry found"
            return result
        except Exception as e:
            return {**result, "error": str(e)}

    @staticmethod
    def _collect_known_permissions(root: Path) -> set[str]:
        """从 RBAC/权限注册表中收集已知权限字符串。

        查找常见模式：Permission 枚举 / PERMISSIONS dict / rbac.py。
        """
        known: set[str] = set()
        candidates = list(root.rglob("rbac.py")) + list(root.rglob("permissions.py"))
        for f in candidates[:3]:  # 最多 3 个文件
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                # 提取赋值/枚举中的字符串
                strings = re.findall(r'"([^"]+)"', content)
                known.update(s for s in strings if ":" in s)  # 权限通常含冒号
            except (UnicodeDecodeError, OSError):
                pass
        return known
