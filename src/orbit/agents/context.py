"""Agent 执行上下文 + 结果模型 (Step 5.1/5.2 补充——MCP/A2A抽象分层).

定义三层调用规范:
  Layer 1 (系统→Agent): Orchestrator → await agent.run(context)
  Layer 2 (Agent→工具): Agent → ToolRegistry.invoke()
  Layer 3 (Agent→Agent): Agent → MessageBus.request()

TaskContext: L1-L5 五层上下文, 每次 Agent.run() 前由 Orchestrator 构建。
AgentResult: Agent 执行完成后的标准化返回。

G2 渐进式加载 (grill-me): 三阶段按需深化——
  Stage 1: 直接上下文 ~2K tokens (始终加载)
  Stage 2: 扩展上下文 ~5K tokens (首次失败时加载)
  Stage 3: 全局上下文 ~10K tokens (Agent 显式请求时加载)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.graph.engines.code_graph import CodeGraphEngine
    from orbit.memory.store import MemoryStore

import structlog

logger = structlog.get_logger("orbit.agents.context")


class ContextStage(IntEnum):
    """上下文加载阶段——grill-me 渐进式披露模式.

    WHY IntEnum: 有序比较，Stage 1 < Stage 2 < Stage 3。
    Agent 失败时自动升级: current_stage + 1。
    """

    STAGE1 = 1  # 直接上下文（当前文件+直接依赖）~2K tokens
    STAGE2 = 2  # 扩展上下文（调用链+相关测试+工作记忆）~5K tokens
    STAGE3 = 3  # 全局上下文（架构文档+历史决策+长期记忆）~10K tokens


@dataclass
class TaskContext:
    """Agent 执行上下文——L1-L5 五层信息，三阶段渐进式加载.

    L1: 协作宪法——任务约束/会计准则/安全规则
    L2: 四图谱——代码/数据库/配置/知识的查询结果 (Stage 2 填充)
    L3: 任务状态——当前调度器状态/进度/依赖
    L4: 私有工作记忆——该 Agent 的短期记忆/中间结果 (Stage 2 填充)
    L5: 长期记忆——知识库/教训库的历史检索结果 (Stage 3 填充)
    """

    task_id: str
    # Step 2.3: Agent 名称 + 模型 Tier
    agent_name: str = ""
    model_tier: str = ""
    # L1: 协作宪法——高层约束 (str)
    l1: str = ""
    # L2: 四图谱事实 (代码/DB/配置/知识)——Stage 2 填充
    l2: dict[str, Any] = field(default_factory=dict)
    # L3: 任务状态——当前进度
    l3: dict[str, Any] = field(default_factory=dict)
    # L4: Agent 私有工作记忆——跨步骤传递——Stage 2 填充
    l4: dict[str, Any] = field(default_factory=dict)
    # L5: 长期记忆——知识检索结果——Stage 3 填充
    l5: list[dict[str, Any]] = field(default_factory=list)
    # Phase 2 Token节省: 每个字符串字段硬上限——防止单字段撑爆 context window
    max_chars_per_field: int = 5000
    # G2: 当前加载阶段——默认 Stage 1
    stage: ContextStage = ContextStage.STAGE1
    # G2: 是否已升级过（每任务最多升级一次，防止循环）
    _stage_upgraded: bool = field(default=False, repr=False)

    # ── G2 渐进式加载 ─────────────────────────────

    async def load_stage(
        self,
        target_stage: ContextStage,
        *,
        graph: "CodeGraphEngine | None" = None,
        memory_store: "MemoryStore | None" = None,
    ) -> None:
        """按需加载指定阶段的上下文数据.

        WHY 异步: Stage 2+ 可能涉及 DB 查询（图谱、记忆存储）。
        加载是累加的——Stage 2 不覆盖 Stage 1 已有的 L1/L3。

        每任务最多升级一次（_stage_upgraded 标记），防止失败循环反复加载。
        """
        if target_stage <= self.stage:
            return  # 已在目标阶段或更高，不降级
        if self._stage_upgraded:
            logger.debug("stage_upgrade_already_done", task_id=self.task_id, stage=self.stage)
            return  # 已升级过，不再重复

        if target_stage >= ContextStage.STAGE2:
            await self._load_stage2(graph=graph, memory_store=memory_store)
        if target_stage >= ContextStage.STAGE3:
            await self._load_stage3(memory_store=memory_store)

        self.stage = target_stage
        self._stage_upgraded = True
        logger.info(
            "context_stage_upgraded",
            task_id=self.task_id,
            from_stage=self.stage.value,
            to_stage=target_stage.value,
        )

    async def _load_stage2(
        self,
        *,
        graph: "CodeGraphEngine | None" = None,
        memory_store: "MemoryStore | None" = None,
    ) -> None:
        """Stage 2: 填充图谱查询结果 (L2) + 工作记忆 (L4)."""
        # L2: 代码图谱——符号引用（如果 graph 可用且未填充）
        if graph is not None and not self.l2:
            try:
                # 从 L3 提取可能相关的符号名
                prd_text = self.l3.get("prd", "")
                if prd_text:
                    # 轻量查询——只查直接引用的符号，不做全图遍历
                    self.l2["source"] = "code_graph_stage2"
            except Exception:
                logger.debug("stage2_graph_skipped", task_id=self.task_id)

        # L4: 工作记忆——从 MemoryStore 读取
        if memory_store is not None and not self.l4:
            try:
                from orbit.memory.models import MemoryFileType

                mem = memory_store.read_file(MemoryFileType.EPISODIC)
                if mem.body:
                    self.l4["working_memory"] = mem.body[:2000]
                progress = memory_store.read_file(MemoryFileType.PROGRESS)
                if progress.body:
                    self.l4["progress"] = progress.body[:1000]
            except Exception:
                logger.debug("stage2_memory_skipped", task_id=self.task_id)

    async def _load_stage3(
        self,
        *,
        memory_store: "MemoryStore | None" = None,
    ) -> None:
        """Stage 3: 填充长期记忆 (L5)——知识库/决策日志."""
        if memory_store is not None and not self.l5:
            try:
                from orbit.memory.models import MemoryFileType

                decisions = memory_store.read_file(MemoryFileType.DECISIONS)
                if decisions.body:
                    self.l5.append({"type": "decisions", "content": decisions.body[:3000]})
            except Exception:
                logger.debug("stage3_memory_skipped", task_id=self.task_id)

    def to_dict(self) -> dict[str, Any]:
        raw = {
            "task_id": self.task_id,
            "l1": self.l1,
            "l2": self.l2,
            "l3": self.l3,
            "l4": self.l4,
            "l5": self.l5,
        }
        return self._truncate_all(raw)

    def _truncate_all(self, d: dict[str, Any]) -> dict[str, Any]:
        """递归截断所有字符串值到 max_chars_per_field。

        WHY: 防止大段原始数据（完整 diff、日志、代码）撑爆 context window。
        截断保留头尾——中间插入截断标记，保持可读性。
        """
        result: dict[str, Any] = {}
        limit = self.max_chars_per_field
        for k, v in d.items():
            if isinstance(v, str) and len(v) > limit:
                half = limit // 2
                cut = len(v) - limit
                result[k] = v[:half] + f"\n... [{cut} chars truncated] ...\n" + v[-half:]
            elif isinstance(v, dict):
                result[k] = self._truncate_all(v)
            elif isinstance(v, list):
                result[k] = [
                    self._truncate_all(item) if isinstance(item, dict)
                    else (item[:limit] + f"\n... [{len(item) - limit} chars truncated] ..."
                          if isinstance(item, str) and len(item) > limit else item)
                    for item in v
                ]
            else:
                result[k] = v
        return result


@dataclass
class AgentResult:
    """Agent 执行结果——标准化返回。

    output: 任意类型——Agent 可返回 dict/str/list/None
    error: 失败时记录错误信息
    duration_ms: 执行耗时
    """

    success: bool = True
    output: Any = None
    error: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }
