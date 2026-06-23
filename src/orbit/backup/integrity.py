"""备份完整性校验 (Step 7.4/7.5 PR #1).

SHA256 哈希计算 + 轻量级文件完整性验证。
"""

from __future__ import annotations

import hashlib


def compute_hash(file_path: str) -> str:
    """计算文件 SHA256 哈希值。

    分块读取 (64KB)，避免大文件占满内存。
    """
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):  # 64KB 块
            h.update(chunk)
    return h.hexdigest()


def verify_integrity(file_path: str, expected_hash: str) -> bool:
    """验证文件完整性——对比 SHA256 哈希。

    Returns:
        True 如果哈希匹配，False 否则。
    """
    try:
        actual = compute_hash(file_path)
        return actual == expected_hash
    except FileNotFoundError:
        return False
