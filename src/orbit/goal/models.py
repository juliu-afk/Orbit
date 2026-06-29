"""Goal 模式数据模型。

WHY 独立 models 文件: 避免循环导入——process_guard/subtask_session/
meta_orchestrator 各自引用 GoalSession，集中定义。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class GoalSession(BaseModel):
    """Goal 会话——持久化到 goal_sessions 表。

    一个 Goal = 一个用户设定的目标，可能包含多个子任务。
    每个子任务独立 Session + 独立 128K 上下文。
    """

    id: str = Field(default_factory=lambda: uuid4().hex, description="UUID4")
    description: str = Field(..., min_length=1, description="目标描述")
    constraints: list[str] = Field(default_factory=list, description="约束条件")
    verification_commands: list[str] = Field(
        default_factory=list, description="验证命令 (pytest/lint/tsc)"
    )
    sub_tasks: dict[str, str] = Field(
        default_factory=dict, description="{task_id: pending|running|done|failed|retry}"
    )
    spec: dict | None = Field(None, description="TaskDAG 序列化")
    react_count: int = Field(0, ge=0, description="当前 react 计数")
    max_react: int = Field(12, ge=1, description="硬上限")
    status: str = Field("active", description="active|done|failed|cancelled|paused")
    # D5: 预算控制
    total_token_budget: int = Field(0, description="Goal 总 Token 配额，0=无限制")
    token_consumed: int = Field(0, description="Goal 已消耗 Token")
    max_runtime_seconds: int = Field(0, description="最大运行时间（秒），0=无限制")
    max_parallel_tasks: int = Field(5, description="最大并行子任务数")
    started_at: str = Field("", description="Goal 启动时间 ISO")
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
    # D3: 进度信息
    task_merge_shas: dict[str, str] = Field(
        default_factory=dict, description="{task_id: merge_commit_sha}"
    )
    # D10a/D10b/D10c: 品质记录
    critique_history: list[dict] = Field(default_factory=list)
    ensemble_results: list[dict] = Field(default_factory=list)
    alignment_checks: list[dict] = Field(default_factory=list)
    consecutive_failures: int = Field(0, description="连续子任务失败计数")
    consecutive_misalignments: int = Field(0, description="连续不对齐计数")
    # D7: 预估算
    estimated_tokens_range: dict | None = Field(None)
    estimated_time_range: dict | None = Field(None)
    # D12: 三层记忆
    three_tier_memory: dict = Field(default_factory=dict)


class IntakeDecision(BaseModel):
    """Intake Router 判定结果。"""

    needs_clarify: bool = Field(True, description="是否需要需求澄清")
    needs_decompose: bool = Field(True, description="是否需要任务拆解")
    reason_clarify: str = Field("", description="澄清判定理由")
    reason_decompose: str = Field("", description="拆解判定理由")
    clarity_score: float = Field(0.0, ge=0.0, le=1.0)
    decomposition_score: float = Field(0.0, ge=0.0, le=1.0)
    is_batch: bool = Field(False, description="是否为复数文档")
    confidence: float = Field(0.5, ge=0.0, le=1.0)


class DepEdge(BaseModel):
    """依赖边——DependencyAnalyzer 产出。"""

    from_id: str = Field(..., description="被依赖的 Goal ID")
    to_id: str = Field(..., description="依赖方 Goal ID")
    type: str = Field("explicit", description="explicit|file_conflict|implicit")
    source: str = Field("", description="判定来源")
    confidence: float = Field(1.0, ge=0.0, le=1.0)


class DependencyConflict(BaseModel):
    """依赖冲突。"""

    type: str = Field(..., description="cycle|file_conflict|self_ref")
    goals: list[str] = Field(default_factory=list)
    suggestion: str = Field("")


class SubTaskResult(BaseModel):
    """单个子任务执行结果。"""

    task_id: str = ""
    status: str = "pending"  # ok|error|critique_loop|timeout
    pr_id: str = ""
    branch: str = ""
    merge_sha: str = ""
    tokens_used: int = 0
    critique_approved: bool = False
    verification_passed: bool = False
    error: str = ""


class GoalResult(BaseModel):
    """Goal 执行结果。"""

    status: str = "pending"  # done|failed|cancelled|paused
    reason: str = ""
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_tokens: int = 0
    total_time_seconds: float = 0.0
    report_path: str = ""


class GoalBatchReport(BaseModel):
    """批量 Goal 执行报告。"""

    total_goals: int = 0
    completed: int = 0
    failed: int = 0
    total_tokens: int = 0
    total_time_seconds: float = 0.0
    results: list[GoalResult] = Field(default_factory=list)
    report_path: str = ""
