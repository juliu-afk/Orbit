"""共享图谱产物——zstd 压缩 SQLite 用于团队共享。

WHY zstd: 比 gzip 快 3-5× 压缩、2× 解压，压缩比相当（8-13:1）。
CBM 已验证此方案（.codebase-memory/graph.db.zst）。

用法:
    export_graph_artifact("data/graph.db", ".orbit/graph/graph.db.zst")
    import_graph_artifact(".orbit/graph/graph.db.zst", "data/graph.db")
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from pathlib import Path

import structlog
import zstandard as zstd

logger = structlog.get_logger("orbit.graph.artifact")

_GITATTRS_LINE = ".orbit/graph/graph.db.zst merge=ours\n"


def export_graph_artifact(
    db_path: str,
    output_path: str = ".orbit/graph/graph.db.zst",
    compression_level: int = 9,
) -> bool:
    """压缩图谱 SQLite → zstd 单文件。

    Args:
        db_path: 源 SQLite 数据库路径
        output_path: 输出 .zst 文件路径
        compression_level: zstd 压缩级别（1-22，默认 9）

    Returns:
        True 如果成功。
    """
    src = Path(db_path)
    if not src.exists():
        logger.warning("artifact_source_missing", path=db_path)
        return False

    dst = Path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    try:
        # 1. VACUUM INTO 去碎片（CBM 借鉴——压缩前 compact）
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name
        conn = sqlite3.connect(str(src))
        # P2-3 fix: VACUUM INTO 不支持参数绑定（DDL 限制）——用字符串拼接
        # tmp_path 来自 tempfile.mktemp()——系统生成的安全路径，非用户输入
        conn.execute(f"VACUUM INTO '{tmp_path}'")
        conn.close()

        # 2. zstd 压缩
        cctx = zstd.ZstdCompressor(level=compression_level)
        with open(tmp_path, "rb") as f_in:
            compressed = cctx.compress(f_in.read())

        with open(dst, "wb") as f_out:
            f_out.write(compressed)

        Path(tmp_path).unlink()
        logger.info("artifact_exported", src=str(src), dst=str(dst),
                     size=len(compressed))

        # 3. 写入 gitattributes（防合并冲突）
        _ensure_gitattributes(dst.parent)

        return True
    except Exception as e:
        logger.error("artifact_export_failed", error=str(e))
        return False


def import_graph_artifact(
    artifact_path: str,
    db_path: str,
) -> bool:
    """解压 zstd 产物 → 恢复 SQLite 数据库。

    Args:
        artifact_path: .zst 产物路径
        db_path: 目标 SQLite 数据库路径

    Returns:
        True 如果成功。
    """
    src = Path(artifact_path)
    dst = Path(db_path)

    if not src.exists():
        logger.info("artifact_not_found", path=artifact_path)
        return False

    try:
        dctx = zstd.ZstdDecompressor()
        with open(src, "rb") as f_in:
            decompressed = dctx.decompress(f_in.read())

        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(dst, "wb") as f_out:
            f_out.write(decompressed)

        logger.info("artifact_imported", src=str(src), dst=str(dst),
                     size=len(decompressed))
        return True
    except Exception as e:
        logger.error("artifact_import_failed", error=str(e))
        return False


def _ensure_gitattributes(graph_dir: Path) -> None:
    """确保 .gitattributes 包含 merge=ours 规则——避免二进制产物合并冲突。"""
    repo_root = graph_dir
    while repo_root.parent != repo_root:
        if (repo_root / ".git").exists():
            break
        repo_root = repo_root.parent
    else:
        return

    attr_file = repo_root / ".gitattributes"
    if attr_file.exists():
        content = attr_file.read_text()
        if _GITATTRS_LINE.strip() in content:
            return
    else:
        content = ""

    attr_file.write_text(content + _GITATTRS_LINE)
    logger.info("gitattributes_updated", file=str(attr_file))
