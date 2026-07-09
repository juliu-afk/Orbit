"""OKF (Open Knowledge Format) v0.1 导出器。

将 Orbit 知识图谱导出为符合 Google OKF v0.1 规范的 Markdown bundle。
输出到 .orbit/knowledge/ 目录——人类可用 Obsidian/VS Code 编辑，
Agent 可通过 okf-mcp 消费，git 可版本化。

规范：https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md

WHY OKF 仅用于知识图谱：代码/DB/配置图谱需要毫秒级结构化查询——
SQLite 是正确选择。OKF 作为知识交换格式，仅应用于外挂领域知识层。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from orbit.knowledge.engine import KnowledgeEngine

logger = structlog.get_logger("orbit.knowledge.okf")


def _slugify(text: str) -> str:
    """中文文本 → 文件名安全 slug。"""
    return text.replace(" ", "-").replace("/", "-").replace("(", "").replace(")", "")


class OkfExporter:
    """将 KnowledgeEngine 中的概念导出为 OKF bundle。

    用法::

        exporter = OkfExporter(engine)
        count = exporter.export("/path/to/.orbit/knowledge")
        exporter.generate_index("/path/to/.orbit/knowledge")
        exporter.generate_log("/path/to/.orbit/knowledge")
    """

    def __init__(self, engine: KnowledgeEngine | None = None) -> None:
        self._engine = engine or KnowledgeEngine()

    def export(self, output_dir: str) -> int:
        """全量导出所有知识概念 → OKF .md 文件。

        Returns:
            导出的 concept 数量。
        """
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        store = self._engine._store
        # 遍历所有 domain 下的所有概念
        domains = self._list_domains()
        count = 0

        for domain in domains:
            domain_dir = root / _slugify(domain)
            domain_dir.mkdir(parents=True, exist_ok=True)
            concepts = store.list_by_domain(domain)
            for c in concepts:
                self._write_concept(domain_dir, domain, c)
                count += 1

        logger.info("okf_export_done", output_dir=str(root), concepts=count)
        return count

    def _write_concept(
        self, domain_dir: Path, domain: str, concept: dict[str, Any]
    ) -> None:
        """写单个概念 → .md 文件（OKF v0.1 格式）。"""
        filename = _slugify(concept["concept"]) + ".md"
        filepath = domain_dir / filename

        # ── Frontmatter（仅 type 必需）─────────────────────
        frontmatter: dict[str, Any] = {
            "type": f"Orbit/{domain}",
            "title": concept.get("name_zh", concept["concept"]),
            "description": concept.get("definition", "")[:200],
            "tags": [domain, concept["concept"]],
            "timestamp": concept.get("created_at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
        }
        if concept.get("source_uri"):
            frontmatter["resource"] = concept["source_uri"]
        if concept.get("source_level"):
            frontmatter["x-orbit-source-level"] = concept["source_level"]

        # ── Body（Markdown）──────────────────────────────────
        body_parts = [f"# {concept.get('name_zh', concept['concept'])}"]
        body_parts.append("")
        body_parts.append(concept.get("definition", ""))
        if concept.get("formula"):
            body_parts.append("")
            body_parts.append("## 公式")
            body_parts.append("")
            body_parts.append(concept["formula"])
        if concept.get("source_uri"):
            body_parts.append("")
            body_parts.append("## Citations")
            body_parts.append("")
            body_parts.append(f"[1] [{concept['source_uri']}]({concept['source_uri']})")

        # ── 组装（手写 YAML frontmatter——避免引入 PyYAML 依赖）────
        fm_lines = []
        for key, value in frontmatter.items():
            if isinstance(value, list):
                items = ", ".join(repr(v) for v in value)
                fm_lines.append(f"{key}: [{items}]")
            elif isinstance(value, str):
                # WHY 不用 yaml.dump: 零新依赖。YAML 多行字符串场景极少，
                # 知识图谱的 frontmatter 值均为单行文本。
                escaped = value.replace("\\", "\\\\").replace('"', '\\"')
                fm_lines.append(f'{key}: "{escaped}"')
            elif isinstance(value, bool):
                fm_lines.append(f"{key}: {'true' if value else 'false'}")
            else:
                fm_lines.append(f"{key}: {value}")
        frontmatter_str = "\n".join(fm_lines)
        content = f"---\n{frontmatter_str}\n---\n\n" + "\n".join(body_parts) + "\n"

        filepath.write_text(content, encoding="utf-8")
        logger.debug("okf_concept_written", path=str(filepath))

    def generate_index(self, output_dir: str) -> None:
        """生成各层 index.md——渐进披露。"""
        root = Path(output_dir)
        domains = self._list_domains()
        store = self._engine._store

        # 根 index.md
        root_lines = ["# Orbit 知识图谱", "", "## 领域"]
        for domain in domains:
            concepts = store.list_by_domain(domain)
            root_lines.append(f"- [{domain}]({_slugify(domain)}/) — {len(concepts)} 个概念")
        (root / "index.md").write_text("\n".join(root_lines) + "\n", encoding="utf-8")

        # 各 domain index.md
        for domain in domains:
            domain_dir = root / _slugify(domain)
            concepts = store.list_by_domain(domain)
            lines = [f"# {domain}", ""]
            for c in concepts:
                name = c.get("name_zh", c["concept"])
                desc = c.get("definition", "")[:120]
                filename = _slugify(c["concept"]) + ".md"
                lines.append(f"- [{name}]({filename}) — {desc}")
            (domain_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

        logger.info("okf_index_generated", output_dir=str(root))

    def generate_log(self, output_dir: str) -> None:
        """生成根 log.md——变更历史。"""
        root = Path(output_dir)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_content = f"""# 知识图谱变更日志

## {today}
* **Export**: Orbit 知识图谱 OKF 导出——{self._engine._store.count()} 个概念
"""
        (root / "log.md").write_text(log_content, encoding="utf-8")
        logger.info("okf_log_generated", output_dir=str(root))

    def _list_domains(self) -> list[str]:
        """从 SQLite 获取所有领域列表。"""
        try:
            conn = self._engine._store._get_conn()
            rows = conn.execute(
                "SELECT DISTINCT domain FROM knowledge_concepts ORDER BY domain"
            ).fetchall()
            return [r[0] for r in rows]
        except Exception:
            return ["accounting"]
