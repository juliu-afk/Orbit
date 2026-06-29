"""Goal 模式——多独立会话编排 + 自主 PR 合入。

核心模块:
- process_guard: 流程强制守卫（对标 MetaGPT SOP）
- subtask_session: 独立 Task 会话（独立 128K 上下文）
- meta_orchestrator: Goal 级编排器
- critique: 批判 Agent（自主 PR 合入门禁）
- ensemble: 多模型并行集成
- verifier: 真实验证执行器
- progress_tracker: 跨 Session 进度跟踪
- intake_router: 输入形态智能判定
- dependency_analyzer: 复数任务依赖关联分析
- memory_tiers: 三层记忆架构
- budget_allocator: 按权重分配 Token 预算
- preflight: 预估算 Agent
- alignment: RefAct 对齐检查
- regression_guard: 回归守卫
- compose_bridge: Goal→Compose 桥接
"""

from orbit.goal.alignment import AlignmentCheck, AlignmentResult
from orbit.goal.budget_allocator import BudgetAllocator
from orbit.goal.compose_bridge import GoalComposeBridge
from orbit.goal.critique import CritiqueAgent, CritiqueResult
from orbit.goal.dependency_analyzer import DependencyAnalyzer
from orbit.goal.ensemble import EnsembleResult, ModelEnsemble
from orbit.goal.intake_router import IntakeRouter
from orbit.goal.memory_tiers import ThreeTierMemory
from orbit.goal.meta_orchestrator import MetaOrchestrator
from orbit.goal.models import GoalSession
from orbit.goal.preflight import PreFlightEstimator, PreFlightResult
from orbit.goal.process_guard import ProcessGuard, ProcessViolationError
from orbit.goal.progress_tracker import ProgressTracker
from orbit.goal.regression_guard import RegressionGuard, RegressionResult
from orbit.goal.subtask_session import SubTaskSession
from orbit.goal.verifier import ExecutorVerifier, VerificationResult

__all__ = [
    "AlignmentCheck",
    "AlignmentResult",
    "BudgetAllocator",
    "CritiqueAgent",
    "CritiqueResult",
    "DependencyAnalyzer",
    "EnsembleResult",
    "ExecutorVerifier",
    "GoalComposeBridge",
    "GoalSession",
    "IntakeRouter",
    "MetaOrchestrator",
    "ModelEnsemble",
    "PreFlightEstimator",
    "PreFlightResult",
    "ProcessGuard",
    "ProcessViolationError",
    "ProgressTracker",
    "RegressionGuard",
    "RegressionResult",
    "SubTaskSession",
    "ThreeTierMemory",
    "VerificationResult",
]
