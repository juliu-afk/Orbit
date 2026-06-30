"""文件记忆存储 (Phase 2 AC9).

CRUD 操作 MEMORY.md / checkpoint.md / progress.md / notes.md.
YAML frontmatter + markdown body 格式。
双向同步 (file ↔ memory reconcile).

WHY 文件而非 SQLite: Markdown 人可读，符合 MiMo Code 设计。
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

import structlog

from orbit.memory.models import (
    DecisionRecord,
    MemoryConfig,
    MemoryFile,
    MemoryFileType,
    MemorySearchQuery,
    MemorySearchResult,
)

logger = structlog.get_logger("orbit.memory")

# YAML frontmatter 正则——提取两个 `---` 之间的内容
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class MemoryStore:
    """文件记忆存储——CRUD + 搜索.

    Usage:
        store = MemoryStore(project_path="/project/root")
        mem = store.read_file(MemoryFileType.EPISODIC)
        store.append_to_file(MemoryFileType.EPISODIC, "## New Section\\n...")
    """

    def __init__(self, project_path: str = "") -> None:
        self._config = MemoryConfig(project_root=project_path)
        self._resolve_memory_dir()
        # P2-4: 评分缓冲——减少 hit() 高频 IO
        self._score_buffer: dict[str, float] = {}

    # ── 读 ─────────────────────────────────────────────

    def read_file(self, file_type: MemoryFileType) -> MemoryFile:
        """读取一个记忆文件——解析 frontmatter + body."""
        path = self._path_for(file_type)
        mem = MemoryFile(path=str(path), file_type=file_type)

        if not path.exists():
            return mem

        content = path.read_text(encoding="utf-8", errors="replace")
        mem.checksum_sha256 = _sha256(content)
        mem.updated_at = path.stat().st_mtime

        # 解析 frontmatter
        fm_match = _FRONTMATTER_RE.match(content)
        if fm_match:
            mem.body = content[fm_match.end() :]
            mem.frontmatter = _parse_yaml_frontmatter(fm_match.group(1))
        else:
            mem.body = content

        return mem

    def read_for_agent(self, agent_name: str) -> MemoryFile:
        """读取与当前 Agent 相关的记忆——过滤 MEMORY.md 中对应的 Section."""
        mem = self.read_file(MemoryFileType.EPISODIC)
        # 过滤 body 中与 agent_name 相关的 Section
        if agent_name and mem.body:
            sections = re.split(r"\n## ", mem.body)
            relevant = [
                s
                for s in sections
                if agent_name.lower() in s.lower() or "通用" in s or "General" in s
            ]
            if relevant:
                mem.body = "## ".join(relevant)
        return mem

    # ── 写 ─────────────────────────────────────────────

    def write_file(
        self, file_type: MemoryFileType, body: str, frontmatter: dict | None = None
    ) -> None:
        """写入整个记忆文件——带 frontmatter."""
        path = self._path_for(file_type)
        path.parent.mkdir(parents=True, exist_ok=True)

        fm = dict(frontmatter or {})
        fm.setdefault("updated", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

        content = _build_frontmatter(fm) + "\n" + body
        path.write_text(content, encoding="utf-8")
        logger.info("memory_file_written", path=str(path), size=len(content))

    def append_to_file(
        self, file_type: MemoryFileType, entry: str, llm_client: object = None
    ) -> None:
        """追加条目到记忆文件——保留已有内容.

        Phase 3 HyDE: llm_client 参数用于写入时生成假设问答。
        """
        existing = self.read_file(file_type)
        new_body = existing.body.rstrip() + "\n\n" + entry.strip() + "\n"

        # Phase 3: HyDE 预留接口——在大小检查前追加，避免超限
        fm = dict(existing.frontmatter)
        if llm_client:
            hyde = self._generate_hyde_questions(entry, llm_client)
            if hyde:
                new_body += "\n\n## HyDE 假设问答\n" + hyde + "\n"
                fm["has_hyde"] = True

        # 检查大小限制（含 HyDE 内容）
        if len(new_body.encode("utf-8")) > self._config.max_memory_file_size:
            # 截断旧内容（保留 body 前 30%，丢掉 HyDE 和旧尾部）
            split_point = int(len(existing.body) * 0.3)
            truncated = existing.body[split_point:]
            # 重建：归档标记 + 截断旧内容 + 新条目（HyDE 在超限时丢弃）
            new_body = (
                f"[旧记忆已归档——超出 {self._config.max_memory_file_size // 1000}KB 限制]\n\n"
                + truncated.rstrip()
                + "\n\n"
                + entry.strip()
                + "\n"
            )
            fm.pop("has_hyde", None)  # 超限丢弃 HyDE
            # P1-1: 截断后二次检查——若 entry 本身太长，极限截断
            if len(new_body.encode("utf-8")) > self._config.max_memory_file_size:
                new_body = (
                    f"[旧记忆已归档——超出 {self._config.max_memory_file_size // 1000}KB 限制]\n\n"
                    + entry.strip()[: self._config.max_memory_file_size // 2]
                    + "\n"
                )
            logger.warning("memory_file_truncated", path=str(self._path_for(file_type)))

        self.write_file(file_type, new_body, fm)

    def _generate_hyde_questions(self, entry: str, llm_client: object | None) -> str:
        """Phase 3: HyDE 假设问答——预留 async 集成接口。

        P1-2: append_to_file 是同步方法，LLMClient.generate() 返回 coroutine，
        同步调用无法 await。当前返回空字符串，待 async wrapper 实现后再启用。
        """
        return ""  # TODO: async HyDE wrapper (future PR)

    # ── 搜索 ───────────────────────────────────────────

    def search(self, query: MemorySearchQuery) -> list[MemorySearchResult]:
        """在记忆文件中搜索——BM25 排序 (5B.4 升级)."""
        from orbit.memory.fts import rank_by_bm25

        results: list[MemorySearchResult] = []
        pattern = query.query.lower()

        file_types = [query.file_type] if query.file_type else list(MemoryFileType)
        for ft in file_types:
            mem = self.read_file(ft)
            if not mem.body:
                continue
            paragraphs = [p.strip() for p in mem.body.split("\n\n") if p.strip()]
            if not paragraphs:
                continue
            ranked = rank_by_bm25(pattern, [(i, p) for i, p in enumerate(paragraphs)])
            for doc_id, score in ranked:
                if score <= 0:
                    continue
                para = paragraphs[doc_id]
                snippet = para[:200] if len(para) > 200 else para
                results.append(
                    MemorySearchResult(
                        path=mem.path,
                        score=round(score, 4),
                        snippet=snippet,
                        line_number=doc_id + 1,
                    )
                )
        results.sort(key=lambda r: r.score, reverse=True)
        return results[: query.max_results]

    # ── 决策日志（业务层减熵 P1）───────────────────────────

    def save_decision(self, decision: DecisionRecord) -> None:
        """保存设计决策——追加到 decisions.md."""

        entry = (
            f"## {decision.id}\n"
            f"- **选择**: {decision.choice}\n"
            f"- **理由**: {decision.why}\n"
            f"- **约束**: {', '.join(decision.constraints) or '无'}\n"
            f"- **替代方案**: {', '.join(decision.alternatives) or '无'}\n"
            f"- **决策者**: {decision.made_by}\n"
            f"- **时间**: {decision.timestamp}\n"
        )
        self.append_to_file(MemoryFileType.DECISIONS, entry)

    def get_relevant_decisions(
        self, keywords: list[str], max_count: int = 5
    ) -> list[DecisionRecord]:
        """按关键词检索相关设计决策."""
        from orbit.memory.models import DecisionRecord as DR

        mem = self.read_file(MemoryFileType.DECISIONS)
        if not mem.body:
            return []

        results: list[DR] = []

        # 简单 grep 匹配——每个 ## 段检查关键词命中
        sections = mem.body.split("\n## ")
        for section in sections[1:]:  # 跳过第一个空段
            score = sum(1 for kw in keywords if kw.lower() in section.lower())
            if score > 0:
                # P1-2/P1-3: 完整解析 markdown 列表项
                lines = section.strip().split("\n")
                parsed = {}
                for ln in lines:
                    if ln.startswith("- **选择**:"):
                        parsed["choice"] = ln.replace("- **选择**:", "").strip()
                    elif ln.startswith("- **理由**:"):
                        parsed["why"] = ln.replace("- **理由**:", "").strip()
                    elif ln.startswith("- **约束**:"):
                        parsed["constraints"] = ln.replace("- **约束**:", "").strip()
                    elif ln.startswith("- **替代方案**:"):
                        parsed["alternatives"] = ln.replace("- **替代方案**:", "").strip()
                    elif ln.startswith("- **决策者**:"):
                        parsed["made_by"] = ln.replace("- **决策者**:", "").strip()
                    elif ln.startswith("- **时间**:"):
                        parsed["timestamp"] = ln.replace("- **时间**:", "").strip()
                results.append(
                    DR(
                        id=lines[0] if lines else "",
                        choice=parsed.get("choice", ""),
                        why=parsed.get("why", ""),
                        constraints=[
                            c.strip() for c in parsed.get("constraints", "").split(",") if c.strip()
                        ],
                        alternatives=[
                            a.strip()
                            for a in parsed.get("alternatives", "").split(",")
                            if a.strip()
                        ],
                        made_by=parsed.get("made_by", ""),
                        timestamp=parsed.get("timestamp", ""),
                    )
                )

        return results[:max_count]

    # ── Phase 1: 评分 ──────────────────────────────────

    def hit(self, key: str, delta: float = 1.0) -> None:
        """命中记忆条目——增加评分（P2-4: 缓冲批量写入）。"""
        self._score_buffer[key] = self._score_buffer.get(key, 0.0) + delta
        if len(self._score_buffer) >= 10:
            self._flush_scores()
        logger.debug("memory_hit", key=key, delta=delta)

    def _flush_scores(self) -> None:
        """P1/P2-4: 原子 swap 批量写入——防止并发 race."""
        # P1: 原子 swap——先拿走 buffer，再基于快照做 IO
        buffer = self._score_buffer
        self._score_buffer = {}
        if not buffer:
            return
        try:
            mem = self.read_file(MemoryFileType.EPISODIC)
            for key, delta in buffer.items():
                score_key = f"score.{key}"
                current = float(mem.frontmatter.get(score_key, 1.0))
                mem.frontmatter[score_key] = current + delta
            self.write_file(MemoryFileType.EPISODIC, mem.body, mem.frontmatter)
        except Exception as e:
            # P2: write_file 失败不丢数据——回写 buffer
            for key, delta in buffer.items():
                self._score_buffer[key] = self._score_buffer.get(key, 0.0) + delta
            logger.warning("score_flush_failed", error=str(e))

    def decay_scores(self, factor: float = 0.95) -> int:
        """衰减所有条目评分——每天调用一次（/dream 触发）。

        WHY 扁平存储: frontmatter 中每个条目占一行 score.{key}: value。
        Returns:
            衰减影响的条目数。
        """
        mem = self.read_file(MemoryFileType.EPISODIC)
        updated = 0
        keys_to_decay = [k for k in mem.frontmatter if k.startswith("score.")]
        for key in keys_to_decay:
            new_val = max(0.1, float(mem.frontmatter[key]) * factor)
            mem.frontmatter[key] = new_val
            updated += 1

        if updated:
            mem.frontmatter["last_decay"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self.write_file(MemoryFileType.EPISODIC, mem.body, mem.frontmatter)
            logger.info("memory_scores_decayed", count=updated, factor=factor)
        return updated

    # ── 同步 ───────────────────────────────────────────

    def reconcile(self, file_type: MemoryFileType, in_memory_version: MemoryFile) -> bool:
        """双向同步——检测冲突并合并.

        Returns:
            True 如果内存版本与文件版本一致（无需修复）
        """
        disk_version = self.read_file(file_type)
        if disk_version.checksum_sha256 == in_memory_version.checksum_sha256:
            return True  # 一致

        # 冲突：保留磁盘版本，返回 False 让调用方决定
        logger.warning(
            "memory_conflict",
            file_type=file_type.value,
            disk_checksum=disk_version.checksum_sha256[:8],
            mem_checksum=in_memory_version.checksum_sha256[:8],
        )
        return False

    # ── 内部 ───────────────────────────────────────────

    def _path_for(self, file_type: MemoryFileType) -> Path:
        return self._config.memory_dir_path / file_type.value

    @property
    def _config(self) -> MemoryConfig:
        return self.__dict__["_config"]

    @_config.setter
    def _config(self, value: MemoryConfig) -> None:
        self.__dict__["_config"] = value

    def _resolve_memory_dir(self) -> None:
        """解析记忆目录路径."""
        base = Path(self._config.project_root) if self._config.project_root else Path.cwd()
        self._config.memory_dir_path = base / self._config.memory_dir


# ── 辅助 ──────────────────────────────────────────────


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_yaml_frontmatter(fm_text: str) -> dict:
    """极简 YAML 解析——仅支持 key: value 格式.

    P2-6 复审: 保留手写解析器而非 yaml.safe_load——
    手写解析器保证返回值永远是 str 类型，下游代码依赖此契约.
    """
    result: dict = {}
    for line in fm_text.strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def _build_frontmatter(fm: dict) -> str:
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)
