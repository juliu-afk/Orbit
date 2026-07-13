"""盲区扫描器 (P1)——Fable 5 方法论落地。

WHY: Thariq "blindspot pass"——动手前让 AI 帮你找出你不知道自己不知道的东西。
在任务创建时执行前向扫描，发现三类盲区:
  1. 知识图谱缺失——任务涉及的概念不在知识库中
  2. 代码图谱未覆盖——任务文件路径不在图谱索引范围
  3. 模糊决策点——需要用户确认的架构/配置选择

设计:
  - 只读: 不修改任何图谱数据，仅查询
  - 并行: 知识图谱 + 代码图谱查询同时执行 (asyncio.gather)
  - 超时: 5 秒 abort，不阻塞任务创建
  - 规则优先: 启发式提取模糊决策点（零 Token），LLM 增强可选

用法:
    from orbit.metacognition.blindspot import BlindspotScanner, BlindspotReport

    scanner = BlindspotScanner(knowledge_store=ks, code_graph=cg)
    report = await scanner.scan(
        task_description="添加 JWT refresh token 支持",
        task_files=["src/orbit/gateway/auth.py"],
    )
    ctx_block = scanner.merge_into_context(report)
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from orbit.knowledge.store import KnowledgeStore
    from orbit.graph.engines.code_graph import CodeGraphEngine

import structlog

logger = structlog.get_logger("orbit.metacognition.blindspot")

SCAN_TIMEOUT = 5.0  # 秒

# 模糊决策触发关键词——文件中包含这些词时标记为需要用户确认
FUZZY_DECISION_KEYWORDS = [
    "TODO", "FIXME", "HACK", "WORKAROUND",
    "tradeoff", "trade-off", "权衡", "取舍",
    "choose between", "either", "or consider",
    "depends on", "待定", "待确认", "暂定",
    "production", "staging", "development only",
    "secret", "password", "token", "credential",
]


class BlindspotReport(BaseModel):
    """盲区扫描报告——三列表。

    knowledge_gaps: 知识图谱缺失概念
    code_gaps: 代码图谱未覆盖的路径
    fuzzy_decisions: 需要用户确认的模糊决策点
    """

    task_id: str = ""
    knowledge_gaps: list[str] = Field(default_factory=list)
    code_gaps: list[str] = Field(default_factory=list)
    fuzzy_decisions: list[str] = Field(default_factory=list)
    scan_duration_ms: float = 0.0
    scanned_concepts: int = 0
    scanned_files: int = 0
    timed_out: bool = False
    warnings: list[str] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not any([self.knowledge_gaps, self.code_gaps, self.fuzzy_decisions])

    @property
    def total_gaps(self) -> int:
        return len(self.knowledge_gaps) + len(self.code_gaps) + len(self.fuzzy_decisions)


class BlindspotScanner:
    """前向盲区扫描器。

    WHY 独立类: 与 MonitorAgent 解耦——Monitor 负责执行中监控，
    BlindspotScanner 负责执行前扫描。
    """

    def __init__(
        self,
        knowledge_store: KnowledgeStore | None = None,
        code_graph: CodeGraphEngine | None = None,
    ) -> None:
        self._kg = knowledge_store
        self._cg = code_graph

    async def scan(
        self, task_description: str, task_files: list[str] | None = None,
        task_id: str = "",
    ) -> BlindspotReport:
        """执行盲区扫描——三个维度并行，5 秒超时。"""
        _t0 = time.monotonic()
        report = BlindspotReport(task_id=task_id)
        task_files = task_files or []

        logger.info("blindspot_scan_start", task_id=task_id,
                     desc_len=len(task_description), file_count=len(task_files))

        try:
            kg_task = asyncio.create_task(self._scan_knowledge_gaps(task_description, report))
            cg_task = asyncio.create_task(self._scan_code_gaps(task_files, report))
            fz_task = asyncio.create_task(self._scan_fuzzy_decisions(task_description, task_files, report))

            done, pending = await asyncio.wait(
                [kg_task, cg_task, fz_task], timeout=SCAN_TIMEOUT,
            )
            for task in pending:
                task.cancel()
                report.warnings.append(f"扫描超时: {task.get_name()}")
            if pending:
                report.timed_out = True
        except Exception:
            logger.error("blindspot_scan_error", task_id=task_id, exc_info=True)
            report.warnings.append("扫描异常终止")

        report.scan_duration_ms = (time.monotonic() - _t0) * 1000
        report.scanned_concepts = self._kg.count() if self._kg else 0
        report.scanned_files = len(task_files)

        logger.info("blindspot_scan_done", task_id=task_id,
                     knowledge_gaps=len(report.knowledge_gaps),
                     code_gaps=len(report.code_gaps),
                     fuzzy_decisions=len(report.fuzzy_decisions),
                     duration_ms=round(report.scan_duration_ms, 1))
        return report

    # ── 维度 1: 知识图谱缺失 ──────────────────────────

    async def _scan_knowledge_gaps(self, task_description: str, report: BlindspotReport) -> None:
        if self._kg is None:
            report.warnings.append("知识图谱未初始化——跳过概念扫描")
            return
        concepts = self._extract_concepts(task_description)
        for concept in concepts:
            if not self._search_knowledge(concept):
                report.knowledge_gaps.append(
                    f"缺少对 '{concept}' 的知识覆盖——"
                    "Agent 可能基于通用知识而非项目特定规范来处理"
                )

    def _search_knowledge(self, concept: str) -> bool:
        """在知识图谱中搜索概念。True=找到。"""
        if self._kg is None:
            return False
        try:
            result = self._kg.query_exact(domain="accounting", concept=concept.lower())
            if result:
                return True
            result = self._kg.query_exact(domain="accounting", concept=concept)
            return result is not None
        except Exception:
            return False

    @staticmethod
    def _extract_concepts(text: str) -> list[str]:
        """从任务描述中提取关键概念——规则驱动，零 Token。"""
        concepts: list[str] = []
        english = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b', text)
        concepts.extend(w.lower() for w in english if len(w) > 3)
        chinese = re.findall(r'[一-鿿]{2,8}', text)
        concepts.extend(chinese)
        seen: set[str] = set()
        unique: list[str] = []
        for c in concepts:
            if c.lower() not in seen:
                seen.add(c.lower())
                unique.append(c)
        return unique[:20]

    # ── 维度 2: 代码图谱未覆盖 ──────────────────────────

    async def _scan_code_gaps(self, task_files: list[str], report: BlindspotReport) -> None:
        if self._cg is None or not task_files:
            if not task_files:
                report.warnings.append("无任务文件列表——跳过代码覆盖扫描")
            else:
                report.warnings.append("代码图谱未初始化——跳过代码覆盖扫描")
            return
        for file_path in task_files:
            covered = await self._check_file_covered(file_path)
            if not covered:
                report.code_gaps.append(
                    f"'{file_path}' 不在代码图谱索引中——"
                    "Agent 可能需要手动探索该文件的依赖关系"
                )

    async def _check_file_covered(self, file_path: str) -> bool:
        if self._cg is None:
            return False
        try:
            from orbit.graph.engines.code_graph import CodeNode
            node = await self._cg.find_node_by_name(CodeNode, file_path)
            if node is not None:
                return True
            filename = file_path.replace("\\", "/").split("/")[-1]
            if filename != file_path:
                node = await self._cg.find_node_by_name(CodeNode, filename)
                return node is not None
            return False
        except Exception:
            logger.debug("code_cover_check_failed", file=file_path, exc_info=True)
            return False

    # ── 维度 3: 模糊决策点 ─────────────────────────────

    async def _scan_fuzzy_decisions(
        self, task_description: str, task_files: list[str], report: BlindspotReport,
    ) -> None:
        desc_lower = task_description.lower()
        for keyword in FUZZY_DECISION_KEYWORDS:
            kw_lower = keyword.lower()
            if kw_lower in desc_lower:
                idx = desc_lower.find(kw_lower)
                start = max(0, idx - 40)
                end = min(len(task_description), idx + len(keyword) + 40)
                context = task_description[start:end].replace("\n", " ")
                report.fuzzy_decisions.append(
                    f"检测到模糊决策标记 '{keyword}': 上下文: \"...{context.strip()}...\""
                )
        # 跨模块检测
        if len(task_files) >= 3:
            modules = set()
            for f in task_files:
                parts = f.replace("\\", "/").split("/")
                if len(parts) >= 2:
                    modules.add(parts[0])
            if len(modules) >= 3:
                report.fuzzy_decisions.append(
                    f"任务跨 {len(modules)} 个模块（{', '.join(sorted(modules))}），"
                    "可能需要确认模块间的接口约定"
                )

    # ── 上下文注入 ─────────────────────────────────────

    def merge_into_context(self, report: BlindspotReport) -> str:
        """将扫描报告转为可注入 Agent 上下文的 Markdown 文本块。"""
        if report.is_empty:
            return ""
        lines = [
            "## 盲区扫描报告（Fable 5 Blindspot Pass）",
            f"扫描耗时: {report.scan_duration_ms:.0f}ms | "
            f"概念数: {report.scanned_concepts} | 文件数: {report.scanned_files}",
            "",
        ]
        if report.knowledge_gaps:
            lines.append("### 知识缺失（Agent 可能不了解以下概念）")
            for gap in report.knowledge_gaps:
                lines.append(f"- ⚠️ {gap}")
            lines.append("")
        if report.code_gaps:
            lines.append("### 代码未覆盖（以下文件不在图谱索引中）")
            for gap in report.code_gaps:
                lines.append(f"- 📁 {gap}")
            lines.append("")
        if report.fuzzy_decisions:
            lines.append("### 需要确认（以下决策点需要你的判断）")
            for fd in report.fuzzy_decisions:
                lines.append(f"- ❓ {fd}")
            lines.append("")
        if report.warnings:
            lines.append("### 扫描警告")
            for w in report.warnings:
                lines.append(f"- ⚡ {w}")
            lines.append("")
        if report.timed_out:
            lines.append("> ⚠️ 扫描超时——以上结果为部分数据，建议手动检查盲区。")
        return "\n".join(lines)
