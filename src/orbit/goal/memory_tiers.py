"""三层记忆架构——跨 Task 知识传递。

v4 定位: 服务于 MetaOrchestrator 跨独立 Session 的知识管理。

Ledger (永久层): Goal 描述/约束/架构决策——注入每个 SubTaskSession
Beads (会话层): 子任务进度/已完成文件/失败方法——MetaOrchestrator 决策
Execution (执行层): 单 SubTaskSession 的消息历史——可丢弃，独立 128K

对标: Cursor RL 自摘要 + Rovo Dev 三层保护
- Ledger 永不被压缩——架构决策/约束永存
- Beads 跨 Session 持久化——仅在合并时压缩
- Execution 可随时丢弃——每 Task 独立 128K 窗口
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class ThreeTierMemory:
    """三层记忆——不同生命周期分开管理。

    Ledger: 永不过期，永不被压缩
    Beads: 跨 Session 持久化，仅在合并时压缩
    Execution: 单轮次有效，可随时丢弃
    """

    # ── Ledger 层: 架构事实，永不过期 ──
    goal_description: str = ""
    constraints: list[str] = field(default_factory=list)
    architecture_decisions: dict = field(default_factory=dict)
    # {decision_id: {what, why, when}}
    api_contracts: dict = field(default_factory=dict)
    # {endpoint: {method, path, schema}}
    schema_versions: dict = field(default_factory=dict)
    # {table: {version, ddl_hash}}

    # ── Beads 层: 任务进度，跨 Session ──
    sub_tasks: dict = field(default_factory=dict)
    # {task_id: {status, last_evidence, assigned_model}}
    completed_files: set[str] = field(default_factory=set)
    failed_approaches: list[str] = field(default_factory=list)
    # 已尝试但失败的方法——不再重复
    critique_history: list[dict] = field(default_factory=list)
    ensemble_decisions: list[dict] = field(default_factory=list)

    # ── Execution 层: 单轮次，可丢弃 ──
    current_turn_messages: list[dict] = field(default_factory=list)
    tool_outputs: list[str] = field(default_factory=list)
    intermediate_reasoning: str = ""

    # ── Fork/Session 传递 ─────────────────────────────

    def to_task_context(self) -> dict:
        """生成注入每个 SubTaskSession 的上下文。

        仅注入 Ledger 层 + Beads 进度摘要。
        不注入 Execution 层——每个 SubTaskSession 从干净 128K 开始。
        """
        return {
            "goal": self.goal_description,
            "constraints": self.constraints,
            "architecture": self.architecture_decisions,
            "api_contracts": self.api_contracts,
            "progress_so_far": self._build_progress_summary(),
            "failed_approaches": self.failed_approaches[-5:],
        }

    def to_fork_context(self) -> dict:
        """Fork 时传递给子 Session——仅 Ledger + Beads。"""
        return {
            "ledger": {
                "goal": self.goal_description,
                "constraints": self.constraints,
                "architecture": self.architecture_decisions,
                "api_contracts": self.api_contracts,
            },
            "beads": {
                "sub_tasks": self.sub_tasks,
                "completed_files": sorted(self.completed_files)[-50:],
                "failed_approaches": self.failed_approaches[-5:],
                "critique_history": self.critique_history[-5:],
            },
        }

    def to_progress_injection(self) -> str:
        """压缩后注入 Beads 层进度摘要——替代被压缩掉的 Execution 细节。

        WHY: 消息历史被压缩后丢失结构化进度信息，
        此方法从 Beads 层恢复——Beads 不会被压缩。
        """
        lines = ["## 当前进度"]
        for tid, info in self.sub_tasks.items():
            status = info.get("status", "pending") if isinstance(info, dict) else info
            lines.append(f"- [{status}] {tid}")
        if self.completed_files:
            recent = sorted(self.completed_files)[-20:]
            lines.append("\n## 已完成文件")
            for f in recent:
                lines.append(f"- {f}")
        if self.failed_approaches:
            lines.append("\n## 失败方法（勿重复）")
            for f in self.failed_approaches[-5:]:
                lines.append(f"- {f}")
        return "\n".join(lines)

    # ── 更新方法 ──────────────────────────────────────

    def record_decision(self, decision_id: str, what: str, why: str) -> None:
        """记录架构决策——Ledger 层。"""
        self.architecture_decisions[decision_id] = {
            "what": what,
            "why": why,
            "when": datetime.now(UTC).isoformat(),
        }

    def record_failure(self, approach: str) -> None:
        """记录失败方法——Beads 层。最多保留 20 条。"""
        self.failed_approaches.append(approach)
        if len(self.failed_approaches) > 20:
            self.failed_approaches = self.failed_approaches[-20:]

    def record_completion(self, file_path: str) -> None:
        """记录完成的文件——Beads 层。自动去重。"""
        self.completed_files.add(file_path)

    def update_subtask(self, task_id: str, status: str, evidence: str = "") -> None:
        """更新子任务状态——Beads 层。"""
        self.sub_tasks[task_id] = {
            "status": status,
            "last_evidence": evidence,
            "updated_at": datetime.now(UTC).isoformat(),
        }

    # ── 内部 ──────────────────────────────────────────

    def _build_progress_summary(self) -> dict[str, str]:
        """构建进度摘要——纯状态映射。"""
        return {
            tid: (info.get("status", "pending") if isinstance(info, dict) else info)
            for tid, info in self.sub_tasks.items()
        }
