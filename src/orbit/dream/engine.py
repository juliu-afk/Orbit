"""/dream 引擎——5 阶段 LLM 合并 (Phase 2 AC10).

Stage 1: GATHER — 扫描近期 session + 读取 MEMORY.md
Stage 2: MERGE_1 — LLM 第一遍合并 (temperature=0.3)
Stage 3: MERGE_2 — LLM 第二遍精炼
Stage 4: DEDUP — Jaccard 去重
Stage 5: VERIFY — 检查 <200 lines + <10KB

WHY 5 阶段而非 1 步: 分阶段可中断、可重试、可独立验证。
"""

from __future__ import annotations

import structlog

from orbit.dream.models import DreamConfig, DreamResult, DreamStatus
from orbit.dream.verifier import DreamVerifier
from orbit.memory.models import MemoryFileType
from orbit.memory.store import MemoryStore

logger = structlog.get_logger("orbit.dream")

DREAM_MERGE_PROMPT = """将以下 Agent 记忆条目合并为精简的记忆文档。

规则:
1. 合并重复或相似的主题
2. 保留具体的文件路径、错误信息和决策
3. 移除过时或已被修复的信息
4. 按主题分组（决策/教训/模式/待办）
5. 保持结构化——使用 ## Section 标题

原始记忆:
{memories}

输出合并后的 Markdown 记忆文档:
"""


class DreamEngine:
    """5 阶段 dream 引擎.

    Usage:
        engine = DreamEngine(llm_client, memory_store)
        result = await engine.run()
    """

    def __init__(
        self,
        llm_client: object = None,
        memory_store: MemoryStore | None = None,
        config: DreamConfig | None = None,
    ) -> None:
        self._llm = llm_client
        self._store = memory_store or MemoryStore()
        self._config = config or DreamConfig()
        self._verifier = DreamVerifier(self._config)

    async def run(self) -> DreamResult:
        """执行完整的 5 阶段 dream 循环."""
        logger.info("dream_cycle_start")

        try:
            # Stage 1: GATHER
            memories = self._stage_gather()

            # Stage 2: MERGE_1
            merged_1 = await self._stage_merge(memories, self._config.merge_temperature)

            # Stage 3: MERGE_2
            merged_2 = await self._stage_merge(merged_1, self._config.verify_temperature)

            # Stage 4: DEDUP
            deduped = self._stage_dedup(merged_2)

            # Stage 5: VERIFY
            result = self._stage_verify(deduped)

            # 写入 MEMORY.md
            if result.status == DreamStatus.COMPLETE:
                self._store.write_file(
                    MemoryFileType.EPISODIC,
                    deduped,
                    {
                        "type": "episodic",
                        "updated": "",
                        "dream_cycle": "v1",
                    },
                )
                logger.info("dream_cycle_complete", lines=result.lines, bytes=result.bytes)

        except Exception as e:
            logger.error("dream_cycle_failed", error=str(e))
            return DreamResult(
                status=DreamStatus.FAILED,
                errors=[str(e)],
            )

        return result

    # ── Stages ──────────────────────────────────────────

    def _stage_gather(self) -> str:
        """Stage 1: 收集记忆来源."""
        parts: list[str] = []

        # 读取现有 MEMORY.md
        episodic = self._store.read_file(MemoryFileType.EPISODIC)
        if episodic.body:
            parts.append(f"## 现有记忆 (MEMORY.md)\n{episodic.body}")

        # 读取 progress.md
        progress = self._store.read_file(MemoryFileType.PROGRESS)
        if progress.body:
            parts.append(f"## 任务进度\n{progress.body}")

        # 读取 notes.md
        notes = self._store.read_file(MemoryFileType.NOTES)
        if notes.body:
            parts.append(f"## 笔记\n{notes.body}")

        gathered = "\n\n".join(parts)
        logger.info("dream_gather", chars=len(gathered))
        return gathered

    async def _stage_merge(self, content: str, temperature: float) -> str:
        """Stage 2/3: LLM 合并——调用廉价模型."""
        if not self._llm:
            return content

        try:
            from orbit.gateway.schemas import LLMRequest

            req = LLMRequest(
                prompt=DREAM_MERGE_PROMPT.format(memories=content[:8000]),
                system_prompt="你是一个知识管理助手，将 Agent 记忆合并为精简的结构化文档。",
                temperature=temperature,
                max_tokens=4000,
            )
            resp = await self._llm.generate(req, task_id="dream_merge")
            return resp.content or content
        except Exception as e:
            logger.warning("dream_merge_failed", error=str(e))
            return content

    def _stage_dedup(self, content: str) -> str:
        """Stage 4: Jaccard 去重——移除高度相似的段落."""
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if len(paragraphs) <= 1:
            return content

        keep: list[str] = [paragraphs[0]]
        for para in paragraphs[1:]:
            is_dup = False
            for kept in keep:
                if _jaccard_similarity(para, kept) > 0.8:
                    is_dup = True
                    break
            if not is_dup:
                keep.append(para)

        logger.info("dream_dedup", original=len(paragraphs), kept=len(keep))
        return "\n\n".join(keep)

    def _stage_verify(self, content: str) -> DreamResult:
        """Stage 5: 验证输出."""
        return self._verifier.verify(content, self._store._path_for(MemoryFileType.EPISODIC))


# ── Jaccard Similarity ─────────────────────────────────


def _jaccard_similarity(a: str, b: str) -> float:
    """计算两个文本的 Jaccard 相似度 (unigram)."""
    set_a = set(a.lower().split())
    set_b = set(b.lower().split())
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0
