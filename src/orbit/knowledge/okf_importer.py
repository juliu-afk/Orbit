"""OKF (Open Knowledge Format) v0.1 导入器。

从外部 OKF bundle 导入领域知识 → Orbit KnowledgeEngine。
支持第三方会计准则/行业知识包导入。

WHY 独立模块：导入与导出是不同的数据流——导出是 read→write md，
导入是 read md→write SQLite。共享同一个 OKF 规范但不共享实现路径。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from orbit.knowledge.engine import KnowledgeEngine

logger = structlog.get_logger("orbit.knowledge.okf_import")


class OkfImporter:
    """读取 OKF bundle → 写入 KnowledgeEngine。

    用法::

        importer = OkfImporter(engine)
        count = importer.import_bundle(".orbit/knowledge")
    """

    def __init__(self, engine: KnowledgeEngine | None = None) -> None:
        self._engine = engine or KnowledgeEngine()

    def import_bundle(self, bundle_dir: str) -> int:
        """导入整个 bundle 的知识概念 → KnowledgeEngine SQLite。

        Returns:
            导入的 concept 数量。
        """
        root = Path(bundle_dir)
        if not root.exists():
            logger.warning("okf_import_bundle_missing", path=bundle_dir)
            return 0

        count = 0
        store = self._engine._store
        conn = store._get_conn()

        for md_file in root.rglob("*.md"):
            if md_file.name in ("index.md", "log.md"):
                continue
            try:
                concept = self._parse_concept(md_file)
                if concept is None:
                    continue
                # 插入或忽略——domain+concept 唯一约束防重复
                conn.execute(
                    """INSERT OR IGNORE INTO knowledge_concepts
                       (domain, concept, name_zh, definition, formula, source_uri, source_level)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        concept["domain"],
                        concept["concept"],
                        concept["name_zh"],
                        concept["definition"],
                        concept.get("formula", ""),
                        concept.get("source_uri", ""),
                        concept.get("source_level", 3),
                    ),
                )
                conn.commit()
                count += 1
            except Exception as e:
                logger.warning("okf_import_skip", file=str(md_file), error=str(e))

        logger.info("okf_import_done", bundle_dir=bundle_dir, concepts=count)
        return count

    def _parse_concept(self, filepath: Path) -> dict[str, Any] | None:
        """解析单个 OKF concept .md 文件。

        Returns:
            {domain, concept, name_zh, definition, formula?, source_uri?, source_level?}
            或 None（解析失败）。
        """
        content = filepath.read_text(encoding="utf-8")
        if not content.startswith("---"):
            return None

        # 解析 frontmatter
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None
        fm_text = parts[1].strip()
        body = parts[2].strip()

        frontmatter: dict[str, Any] = {}
        for line in fm_text.split("\n"):
            line = line.strip()
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"')
            frontmatter[key] = value

        if "type" not in frontmatter:
            return None

        # 从 type 推导 domain（type = "Orbit/accounting" → domain = "accounting"）
        okf_type = frontmatter["type"]
        domain = okf_type.split("/")[-1] if "/" in okf_type else okf_type
        # concept = 文件名去 .md
        concept = filepath.stem

        return {
            "domain": domain,
            "concept": concept,
            "name_zh": frontmatter.get("title", concept),
            "definition": body[:1000] if body else frontmatter.get("description", ""),
            "formula": frontmatter.get("x-orbit-formula", ""),
            "source_uri": frontmatter.get("resource", ""),
            "source_level": frontmatter.get("x-orbit-source-level", 3),
        }
