"""安全常量——敏感文件模式、危险命令等。

P1-6: 统一 guard.py + permission.py + validators.py 中分散的敏感文件列表。
单一定义，三处引用，避免新增模式时遗漏。
"""

from __future__ import annotations

# 敏感文件名 glob 模式——WorkspaceGuard.ALWAYS_DENY_PATTERNS 使用
SENSITIVE_FILE_GLOB: list[str] = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "credentials",
    "secrets",
    "id_rsa",
    "id_ed25519",
]

# 敏感文件名精确集合——PermissionEngine._is_global_deny 使用
SENSITIVE_FILE_NAMES: frozenset[str] = frozenset({
    ".env",
    ".pem",
    ".key",
    "credentials",
    "secrets",
})
