"""盲区扫描器 (P1)——Fable 5 方法论落地。

WHY: Thariq "blindspot pass"——动手前让 AI 帮你找出你不知道自己不知道的东西。
在任务创建时执行前向扫描，发现三类盲区:
  1. 知识图谱缺失——任务涉及的概念不在知识库中
  2. 代码图谱未覆盖——任务文件路径不在图谱索引范围
  3. 模糊决策点——需要用户确认的架构/配置选择

设计:
  - 只读: 不修改任何图谱数据，仅查询
  - 并行: 知识图谱 + 代码图谱查询同时执行
  - 超时: 5 秒 abort，不阻塞任务创建
  - 规则优先: 启发式提取模糊决策点（零 Token），LLM 增强可选

用法:
    from orbit.metacognition.blindspot import BlindspotScanner, BlindspotReport

    scanner = BlindspotScanner(knowledge_store=ks, code_graph=cg)
    report = await scanner.scan(
        task_description="添加 JWT refresh token 支持",
        task_files=["src/orbit/gateway/auth.py"],
    )
    # 注入 Agent 上下文
    context_block = scanner.merge_into_context(report)
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from orbit.knowledge.store import KnowledgeStore
    from orbit.graph.query import GraphQuery
    from orbit.graph.engines.code_graph import CodeGraphEngine

import structlog

logger = structlog.get_logger("orbit.metacognition.blindspot")

# 扫描超时（秒）
SCAN_TIMEOUT = 5.0

# 模糊决策触发关键词——文件中包含这些词时标记为需要用户确认
# WHY 启发式: 零 Token 成本，覆盖 80% 常见模糊点
FUZZY_DECISION_KEYWORDS = [
    # 配置选择
    "TODO", "FIXME", "HACK", "WORKAROUND",
    # 架构决策
    "tradeoff", "trade-off", "权衡", "取舍",
    # 待确认
    "choose between", "either", "or consider",
    "depends on", "待定", "待确认", "暂定",
    # 环境差异
    "production", "staging", "development only",
    # 安全相关
    "secret", "password", "token", "credential",
]


class BlindspotReport(BaseModel):
    """盲区扫描报告。

    三列表:
      - knowledge_gaps: 知识图谱中缺失的领域概念
      - code_gaps: 代码图谱未覆盖的文件/模块路径
      - fuzzy_decisions: 启发式提取的模糊决策点
    """

    task_id: str = ""
    knowledge_gaps: list[str] = Field(
        default_factory=list,
        description="知识图谱缺失概念——'你可能需要了解 X，但知识库中没有 X 的定义'",
    )
    code_gaps: list[str] = Field(
        default_factory=list,
        description="代码图谱未覆盖的路径——'这些文件不在图谱索引中，Agent 可能理解有偏差'",
    )
    fuzzy_decisions: list[str] = Field(
        default_factory=list,
        description="模糊决策点——'这些地方需要你确认选择'",
    )
    scan_duration_ms: float = Field(
        default=0.0, description="扫描耗时（毫秒）"
    )
    scanned_concepts: int = Field(default=0, description="扫描的知识概念数")
    scanned_files: int = Field(default=0, description="扫描的代码文件数")
    timed_out: bool = Field(
        default=False, description="扫描是否超时终止"
    )
    warnings: list[str] = Field(
        default_factory=list, description="扫描过程中的警告"
    )

    @property
    def is_empty(self) -> bool:
        """扫描是否无任何发现——全空说明暂无盲区。"""
        return not any([self.knowledge_gaps, self.code_gaps, self.fuzzy_decisions])

    @property
    def total_gaps(self) -> int:
        """盲区总数。"""
        return len(self.knowledge_gaps) + len(self.code_gaps) + len(self.fuzzy_decisions)


class BlindspotScanner:
    """前向盲区扫描器。

    WHY 独立类: 与 MonitorAgent 解耦——Monitor 负责执行中监控，
    BlindspotScanner 负责执行前扫描。两者职责不同、时机不同。

    不依赖 LLM——所有检测基于规则/查询/关键词匹配。
    """

    def __init__(
        self,
        knowledge_store: KnowledgeStore | None = None,
        code_graph: CodeGraphEngine | None = None,
        graph_query: GraphQuery | None = None,
    ) -> None:
        """初始化扫描器。

        Args:
            knowledge_store: 知识图谱存储（None 时跳过知识扫描）
            code_graph: 代码图谱引擎（None 时跳过代码扫描）
            graph_query: 图谱查询接口（None 时跳过代码扫描）
        """
        self._kg = knowledge_store
        self._cg = code_graph
        self._gq = graph_query

    async def scan(
        self, task_description: str, task_files: list[str] | None = None,
        task_id: str = "",
    ) -> BlindspotReport:
        """执行盲区扫描。

        三个扫描维度并行执行，5 秒超时 abort。

        Args:
            task_description: 任务描述文本
            task_files: 任务涉及的文件路径列表
            task_id: 任务 ID（用于日志关联）

        Returns:
            BlindspotReport——三列表盲区报告
        """
        _t0 = time.monotonic()
        report = BlindspotReport(task_id=task_id)
        task_files = task_files or []

        logger.info(
            "blindspot_scan_start",
            task_id=task_id,
            desc_len=len(task_description),
            file_count=len(task_files),
        )

        try:
            # 三个维度并行扫描
            kg_task = asyncio.create_task(
                self._scan_knowledge_gaps(task_description, report)
            )
            cg_task = asyncio.create_task(
                self._scan_code_gaps(task_files, report)
            )
            fz_task = asyncio.create_task(
                self._scan_fuzzy_decisions(task_description, task_files, report)
            )

            done, pending = await asyncio.wait(
                [kg_task, cg_task, fz_task],
                timeout=SCAN_TIMEOUT,
            )
            # 取消未完成的
            for task in pending:
                task.cancel()
                report.warnings.append(f"扫描超时: {task.get_name()} 在 {SCAN_TIMEOUT}s 内未完成")

            if pending:
                report.timed_out = True

        except Exception:
            logger.error("blindspot_scan_error", task_id=task_id, exc_info=True)
            report.warnings.append("扫描异常终止，返回部分结果")

        report.scan_duration_ms = (time.monotonic() - _t0) * 1000
        report.scanned_concepts = self._kg.count() if self._kg else 0
        report.scanned_files = len(task_files)

        logger.info(
            "blindspot_scan_done",
            task_id=task_id,
            knowledge_gaps=len(report.knowledge_gaps),
            code_gaps=len(report.code_gaps),
            fuzzy_decisions=len(report.fuzzy_decisions),
            duration_ms=round(report.scan_duration_ms, 1),
            timed_out=report.timed_out,
        )

        return report

    # ── 维度 1: 知识图谱缺失 ──────────────────────────

    async def _scan_knowledge_gaps(
        self, task_description: str, report: BlindspotReport,
    ) -> None:
        """扫描知识图谱——任务描述中的概念是否在知识库中有覆盖。

        WHY 异步: 与代码扫描并行，减少总时间。
        """
        if self._kg is None:
            report.warnings.append("知识图谱未初始化——跳过概念扫描")
            return

        # 从任务描述中提取关键词/概念
        concepts = self._extract_concepts(task_description)
        if not concepts:
            return

        for concept in concepts:
            # 在知识图谱中检索此概念
            found = self._search_knowledge(concept)
            if not found:
                report.knowledge_gaps.append(
                    f"缺少对 '{concept}' 的知识覆盖——"
                    "Agent 可能基于通用知识而非项目特定规范来处理"
                )

    def _search_knowledge(self, concept: str) -> bool:
        """在知识图谱中搜索概念。返回 True=找到。"""
        if self._kg is None:
            return False
        try:
            # 精确匹配 + 域内全量搜索
            result = self._kg.query_exact(domain="accounting", concept=concept.lower())
            if result:
                return True
            # 中文名也试
            result = self._kg.query_exact(domain="accounting", concept=concept)
            return result is not None
        except Exception:
            return False

    @staticmethod
    def _extract_concepts(text: str) -> list[str]:
        """从任务描述中提取关键概念。

        WHY 规则提取: 零 Token 成本。提取英文标识符+中文技术术语。

        Returns:
            概念列表（去重，最多 20 个）
        """
        concepts: list[str] = []

        # 英文标识符: snake_case / camelCase / PascalCase
        english = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b', text)
        concepts.extend(w.lower() for w in english if len(w) > 3)

        # 中文技术术语: 2-8 个汉字组成的词组
        chinese = re.findall(r'[一-鿿]{2,8}', text)
        concepts.extend(chinese)

        # 去重 + 限制数量
        seen: set[str] = set()
        unique: list[str] = []
        for c in concepts:
            if c.lower() not in seen:
                seen.add(c.lower())
                unique.append(c)
        return unique[:20]

    # ── 维度 2: 代码图谱未覆盖 ──────────────────────────

    async def _scan_code_gaps(
        self, task_files: list[str], report: BlindspotReport,
    ) -> None:
        """扫描代码图谱——任务文件是否在图谱索引中。

        WHY 异步: 与知识扫描并行。
        """
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
        """检查文件是否在代码图谱中有对应节点。"""
        if self._cg is None:
            return False
        try:
            # code_graph 的 get_symbol_meta 查找符号名，
            # 检查文件是否有节点是更准确的覆盖判定
            from orbit.graph.engines.code_graph import CodeNode

            node = await self._cg.find_node_by_name(CodeNode, file_path)
            if node is not None:
                return True
            # 也试文件名的最后一段
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
        self, task_description: str, task_files: list[str],
        report: BlindspotReport,
    ) -> None:
        """扫描模糊决策点——任务描述中的 TODO/权衡/待确认标记。

        WHY 纯关键词: 零 Token，毫秒级。不读文件内容（那是 Agent 的事）。
        """
        # 从任务描述中匹配
        desc_lower = task_description.lower()
        for keyword in FUZZY_DECISION_KEYWORDS:
            kw_lower = keyword.lower()
            if kw_lower in desc_lower:
                # 提取关键词周围上下文（前后 40 字符）
                idx = desc_lower.find(kw_lower)
                start = max(0, idx - 40)
                end = min(len(task_description), idx + len(keyword) + 40)
                context = task_description[start:end].replace("\n", " ")
                report.fuzzy_decisions.append(
                    f"检测到模糊决策标记 '{keyword}': "
                    f"上下文: \"...{context.strip()}...\""
                )

        # 跨模块引用检测——任务涉及多个顶级模块时标记为模糊
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
        """将扫描报告转为可注入 Agent 上下文的文本块。

        Returns:
            Markdown 格式的盲区报告块，可直接拼接到 system prompt。
        """
        if report.is_empty:
            return ""

        lines = [
            "## 盲区扫描报告（Fable 5 Blindspot Pass）",
            "",
            f"扫描耗时: {report.scan_duration_ms:.0f}ms | "
            f"概念数: {report.scanned_concepts} | "
            f"文件数: {report.scanned_files}",
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
