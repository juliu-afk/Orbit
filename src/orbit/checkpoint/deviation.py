"""偏离日志记录器 (P0)——Fable 5 方法论落地。

WHY 独立模块: Agent 执行过程中偏离原计划的决策需要被结构化记录，
而非散落在日志/注释里。偏离日志是"实现中"发现未知项的唯一记录机制。

设计:
  - DeviationEntry: Pydantic 模型，包含偏离的完整上下文
  - DeviationLogger: 在 Agent 循环中调用，内存缓存，任务终止时 flush
  - 只记 major/critical: 命名调整/import 路径等机械性调整不算偏离
  - 人类可读: render_markdown() 生成 implementation-notes.md

用法:
    from orbit.checkpoint.deviation import DeviationLogger, DeviationEntry, DeviationSeverity

    logger = DeviationLogger(task_id="task_1", plan_md=original_plan)
    logger.record(
        planned="用 SQLAlchemy ORM 查询",
        actual="改用 raw SQL",
        reason="ORM 的 joinedload 在 10k+ 行时 OOM",
        alternatives=["分批查询+ORM", "raw SQL+手动映射"],
        severity=DeviationSeverity.MAJOR,
        file_refs=["src/orbit/graph/query.py"],
    )
    await logger.flush_to_checkpoint(checkpoint_manager)
    notes_md = logger.render_markdown()
"""

from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from orbit.checkpoint.manager import CheckpointManager

import structlog

logger = structlog.get_logger("orbit.checkpoint.deviation")


class DeviationSeverity(StrEnum):
    """偏离严重程度。

    MAJOR: 改变架构/数据模型/API 签名——但不影响安全
    CRITICAL: 改变安全策略/回滚路径/熔断阈值
    minor 级别不记录（命名调整、import 路径等机械性调整不算偏离）
    """

    MAJOR = "major"
    CRITICAL = "critical"


class DeviationEntry(BaseModel):
    """单条偏离记录。

    WHY Pydantic: 需要序列化存入 checkpoint + 跨模块传递。
    """

    id: str = Field(
        default_factory=lambda: hashlib.sha256(
            f"{time.time()}".encode()
        ).hexdigest()[:12],
        description="唯一 ID（SHA256 前 12 位）",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 时间戳",
    )
    planned: str = Field(..., min_length=1, description="原计划做什么")
    actual: str = Field(..., min_length=1, description="实际做了什么")
    reason: str = Field(..., min_length=1, description="为什么偏离——面向审计人员")
    alternatives: list[str] = Field(
        default_factory=list, description="考虑的替代方案（至少 1 个）"
    )
    severity: DeviationSeverity = Field(
        default=DeviationSeverity.MAJOR, description="严重程度"
    )
    file_refs: list[str] = Field(
        default_factory=list, description="涉及的文件路径（项目相对路径）"
    )
    agent_id: str = Field(default="", description="记录此偏离的 Agent ID")
    task_id: str = Field(default="", description="所属任务 ID")

    def to_markdown_section(self) -> str:
        """渲染为 Markdown 段落——用于 implementation-notes.md。"""
        alt_text = "、".join(self.alternatives) if self.alternatives else "无"
        files = "、".join(f"`{f}`" for f in self.file_refs) if self.file_refs else "未指定"
        return (
            f"### 偏离 {self.id}\n\n"
            f"- **时间**: {self.timestamp}\n"
            f"- **严重程度**: {self.severity.value}\n"
            f"- **原计划**: {self.planned}\n"
            f"- **实际执行**: {self.actual}\n"
            f"- **原因**: {self.reason}\n"
            f"- **替代方案**: {alt_text}\n"
            f"- **涉及文件**: {files}\n"
            f"- **记录者**: {self.agent_id or '未知'}\n\n"
        )


# 偏离判定白名单——只有这些领域的变更才算偏离
# WHY 白名单: 不依赖 LLM 判断（零 Token + 零幻觉风险）
DEVIATION_TRIGGERS = [
    # 数据模型变更
    "model", "schema", "field", "column", "table", "migration", "alembic",
    # API 变更
    "endpoint", "route", "api", "response", "request", "status_code",
    # 架构变更
    "architecture", "pattern", "interface", "abstract", "dependency",
    # 安全变更
    "auth", "token", "permission", "sandbox", "isolation", "encrypt",
    # 回滚/熔断变更
    "rollback", "circuit_breaker", "retry", "timeout", "checkpoint",
]


def is_deviation(planned_action: str, actual_action: str, file_paths: list[str] | None = None) -> bool:
    """判断一次决策变更是否构成偏离。

    WHY 白名单 + 规则: 零 Token 成本，毫秒级。命名/import 调整自动过滤。

    Args:
        planned_action: 原计划的动作描述
        actual_action: 实际执行的动作描述
        file_paths: 涉及的文件路径（可选，用于更精确判断）

    Returns:
        True 如果应记录为偏离
    """
    # 没变化不算偏离
    if planned_action.strip() == actual_action.strip():
        return False

    combined = (planned_action + " " + actual_action).lower()
    file_refs_lower = " ".join(file_paths).lower() if file_paths else ""

    # 白名单匹配——关键词命中才算偏离
    for trigger in DEVIATION_TRIGGERS:
        if trigger in combined or trigger in file_refs_lower:
            return True

    return False


class DeviationLogger:
    """偏离日志记录器。

    WHY 独立类: 解耦"何时算偏离"（is_deviation）和"如何记录"（DeviationLogger）。
    CheckpointManager 管存储，DeviationLogger 管决策。

    用法:
        dev_log = DeviationLogger(task_id="task_1", plan_md=spec)
        # Agent 循环中
        if is_deviation(planned, actual):
            dev_log.record(planned=planned, actual=actual, ...)
        # 任务终止时
        await dev_log.flush_to_checkpoint(ckpt_mgr)
        notes = dev_log.render_markdown()
    """

    def __init__(self, task_id: str = "", plan_md: str = "") -> None:
        """初始化偏离日志记录器。

        Args:
            task_id: 所属任务 ID
            plan_md: 原始实现计划（Markdown 文本），用于 render_markdown() 的上下文
        """
        self.task_id = task_id
        self._plan_md = plan_md
        self._entries: list[DeviationEntry] = []
        self._created_at = datetime.now(UTC).isoformat()

    @property
    def entries(self) -> list[DeviationEntry]:
        """返回已记录的所有偏离（只读副本）。"""
        return list(self._entries)

    @property
    def count(self) -> int:
        """已记录的偏离数量。"""
        return len(self._entries)

    def record(
        self,
        planned: str,
        actual: str,
        reason: str,
        alternatives: list[str] | None = None,
        severity: DeviationSeverity = DeviationSeverity.MAJOR,
        file_refs: list[str] | None = None,
        agent_id: str = "",
    ) -> DeviationEntry | None:
        """记录一条偏离。

        WHY 返回 Optional: is_deviation() 预检可能返回 False，
        此时返回 None 避免无意义的内存分配。

        Args:
            planned: 原计划
            actual: 实际执行
            reason: 偏离原因（面向审计人员，必须可理解）
            alternatives: 考虑的替代方案
            severity: 严重程度，默认 MAJOR
            file_refs: 涉及文件路径
            agent_id: 记录者

        Returns:
            创建的 DeviationEntry，或 None（如果不构成偏离）
        """
        if not is_deviation(planned, actual, file_refs):
            return None

        entry = DeviationEntry(
            planned=planned,
            actual=actual,
            reason=reason,
            alternatives=alternatives or [],
            severity=severity,
            file_refs=file_refs or [],
            agent_id=agent_id,
            task_id=self.task_id,
        )
        self._entries.append(entry)

        logger.info(
            "deviation_recorded",
            task_id=self.task_id,
            deviation_id=entry.id,
            severity=severity.value,
            planned=planned[:80],
            actual=actual[:80],
            total_entries=len(self._entries),
        )
        return entry

    async def flush_to_checkpoint(self, ckpt_manager: CheckpointManager) -> None:
        """任务终止时将偏离日志写入 checkpoint。

        调用时机: 任务成功/失败/熔断时。
        写入失败不抛异常（降级: 仅记 Critical 日志）。

        Args:
            ckpt_manager: CheckpointManager 实例
        """
        if not self._entries:
            return

        serialized = [entry.model_dump() for entry in self._entries]
        try:
            # 加载现有 checkpoint，追加偏离日志
            existing = await ckpt_manager.load(self.task_id)
            if existing is not None:
                existing_log = existing.context.get("deviation_log", [])
                existing_log.extend(serialized)
                existing.context["deviation_log"] = existing_log
                await ckpt_manager.save(self.task_id, existing)
            else:
                # 无现有 checkpoint——创建新的最小 checkpoint
                from orbit.checkpoint.manager import CheckpointData

                data = CheckpointData(
                    task_id=self.task_id,
                    state="completed",
                    context={"deviation_log": serialized},
                )
                await ckpt_manager.save(self.task_id, data)

            logger.info(
                "deviation_log_flushed",
                task_id=self.task_id,
                entries=len(serialized),
            )
        except Exception:
            logger.error(
                "deviation_log_flush_failed",
                task_id=self.task_id,
                entries=len(serialized),
                exc_info=True,
            )

    def render_markdown(self) -> str:
        """生成人类可读的 implementation-notes.md。

        Returns:
            Markdown 格式的偏离日志全文
        """
        if not self._entries:
            return (
                f"# 实现笔记 —— {self.task_id}\n\n"
                f"**生成时间**: {self._created_at}\n\n"
                "✅ 严格按计划执行，无偏离。\n"
            )

        severity_count = {"major": 0, "critical": 0}
        for e in self._entries:
            severity_count[e.severity.value] += 1

        lines = [
            f"# 实现笔记 —— {self.task_id}",
            "",
            f"**生成时间**: {self._created_at}",
            f"**偏离总数**: {len(self._entries)}（major: {severity_count['major']}, critical: {severity_count['critical']}）",
            "",
            "---",
            "",
        ]

        if self._plan_md:
            lines.extend([
                "## 原计划",
                "",
                self._plan_md,
                "",
                "---",
                "",
            ])

        lines.append("## 偏离记录")
        lines.append("")

        for entry in self._entries:
            lines.append(entry.to_markdown_section())

        # 汇总
        if severity_count["critical"] > 0:
            lines.append(
                f"⚠️ **注意**: 本任务有 {severity_count['critical']} 条 CRITICAL 偏离，"
                "建议审查后再合并。\n"
            )

        return "\n".join(lines)

    def get_failure_reasons(self) -> list[str]:
        """提取偏离原因列表——供 GEPA evolution 消费。

        Returns:
            ["在 {file_refs} 中，原计划 {planned}，但因 {reason} 改为 {actual}", ...]
        """
        reasons: list[str] = []
        for entry in self._entries:
            files = "、".join(entry.file_refs) if entry.file_refs else "未指定文件"
            reasons.append(
                f"在 {files} 中，原计划「{entry.planned}」，"
                f"但因 {entry.reason} 改为「{entry.actual}」"
            )
        return reasons

    def to_tactical_rules(self) -> list[str]:
        """将偏离原因转为 SCOPE 战术规则——供 ScopeMemory 消费。

        Returns:
            ["DEVIATION_PATTERN: {reason} → 考虑 {alternatives}", ...]
        """
        rules: list[str] = []
        for entry in self._entries:
            alt_text = " 或 ".join(entry.alternatives) if entry.alternatives else "重新评估方案"
            rules.append(
                f"DEVIATION_PATTERN: 遇到「{entry.reason}」时 → 优先考虑 {alt_text}"
            )
        return rules
