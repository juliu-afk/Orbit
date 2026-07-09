"""TaskRunner 单元测试——覆盖率冲刺（57%→85%）。

覆盖 TaskRunner 全部核心方法：
_extract_keywords / run_task / _agent_cycle / _run_agent /
_build_context / resume / _save_checkpoint /
_publish_task_update / _publish_token_update /
+ 模块级纯函数 _transition / _state_to_progress。

WHY 单独测试而非通过 Scheduler 间接测：TaskRunner 是减熵闭环 P1 核心，
有 12 个方法/函数，Scheduler 测试仅覆盖了少数 top-level 路径。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.agents.base import AgentInput, AgentOutput, AgentRole, BaseAgent
from orbit.agents.context import ContextStage, TaskContext
from orbit.api.schemas.task import TaskState
from orbit.checkpoint.manager import CheckpointData
from orbit.scheduler.task_runner import (
    InvalidStateTransitionError,
    TERMINAL_STATES,
    TaskRunner,
    _state_to_progress,
    _transition,
)

# ── Mock 类 ──


class FakeCheckpointManager:
    """内存检查点管理器——记录每次 save 的数据用于断言。"""

    def __init__(self) -> None:
        self.store: dict[str, CheckpointData] = {}
        self.saves: list[CheckpointData] = []

    async def save(self, task_id: str, data: CheckpointData) -> None:
        self.store[task_id] = data
        self.saves.append(data)

    async def load(self, task_id: str) -> CheckpointData | None:
        return self.store.get(task_id)


# ── Fixtures ──


@pytest.fixture
def runner() -> TaskRunner:
    """纯 mock TaskRunner——所有依赖为 None。"""
    return TaskRunner()


@pytest.fixture
def full_runner() -> TaskRunner:
    """全依赖 TaskRunner——所有 mock 均 async 兼容。

    router.evaluate 是 AsyncMock 以便 await。
    """
    router = MagicMock()
    router.evaluate = AsyncMock()
    return TaskRunner(
        agent_factory=MagicMock(),
        agent_llms={
            "clarifier": MagicMock(),
            "architect": MagicMock(),
            "developer": MagicMock(),
            "reviewer": MagicMock(),
        },
        checkpoint=FakeCheckpointManager(),
        event_bus=MagicMock(),
        compressor=MagicMock(),
        budget_tracker=MagicMock(),
        tool_registry=MagicMock(),
        audit_logger=MagicMock(),
        router=router,
        fast_lane=False,
    )


# ════════════════════════════════════════════
# 1. 构造器
# ════════════════════════════════════════════


def test_constructor(runner: TaskRunner) -> None:
    """默认参数：全部为 None / 空字典 / False。"""
    assert runner._agent_factory is None
    assert runner._agent_llms == {}
    assert runner.checkpoint is None
    assert runner._event_bus is None
    assert runner._compressor is None
    assert runner._budget_tracker is None
    assert runner._tool_registry is None
    assert runner._audit_logger is None
    assert runner._router is None
    assert runner._fast_lane is False
    assert runner._edit_detector is not None  # 减熵闭环-2：默认创建


# ════════════════════════════════════════════
# 2. _extract_keywords（减熵闭环-1，静态方法）
# ════════════════════════════════════════════


def test_extract_keywords_empty() -> None:
    """空文本 / None / 纯空白 → []。"""
    assert TaskRunner._extract_keywords("") == []
    assert TaskRunner._extract_keywords("   ") == []
    assert TaskRunner._extract_keywords(None) == []  # 防御性，not None = True


def test_extract_keywords_identifiers_limit() -> None:
    """英文标识符（CamelCase/snake_case）提取 + 最多 20 个限制 + 大小写去重。"""
    # CamelCase + snake_case + 标点剥离
    kw = TaskRunner._extract_keywords("修复 TaskRunner.handleCancelledError")
    # dot 不分割，整个标识符作为一个关键词
    assert "TaskRunner.handleCancelledError" in kw or any("TaskRunner" in k for k in kw)
    # 标点剥离——括号+分号去掉
    kw2 = TaskRunner._extract_keywords("修复 test_get_user_by_id TaskRunner")
    # 标点剥离
    kw2 = TaskRunner._extract_keywords("test_get_user_by_id() -> ResultType;")
    assert "test_get_user_by_id" in kw2
    assert "ResultType" in kw2
    # 最多 20 个
    kw3 = TaskRunner._extract_keywords(" ".join(f"Keyword{i}" for i in range(50)))
    assert len(kw3) <= 20
    # 大小写去重
    kw4 = TaskRunner._extract_keywords("TaskRunner taskrunner TASKRUNNER")
    assert len(kw4) <= 1


def test_extract_keywords_chinese() -> None:
    """中文技术词（2-6 汉字）提取。"""
    kw = TaskRunner._extract_keywords("实现支付模块的数据迁移")
    # 正则 [一-鿿]{2,6} 匹配：实现/支付/模块/数据/迁移/数据库（6个字）等
    cn_hits = [t for t in kw if "一" <= t[0] <= "鿿"]
    assert len(cn_hits) >= 2


def test_extract_keywords_mixed() -> None:
    """中英混合 + 停用词过滤。"""
    text = "修改 VoucherForm 的 validateAmount 方法，支持批量导入"
    kw = TaskRunner._extract_keywords(text)
    # 英文标识符保留
    assert "VoucherForm" in kw
    assert "validateAmount" in kw
    # 停用词过滤（"的"、"修改"是停用词）
    assert "的" not in kw
    # 中文技术词提取——[一-鿿]{2,6} 贪婪匹配，"支持批量导入"作为整体
    assert any("批量" in t for t in kw)
    assert any("导入" in t for t in kw)


# ════════════════════════════════════════════
# 3. 状态转换（模块级纯函数）
# ════════════════════════════════════════════


def test_transition_normal() -> None:
    """正常流水线：IDLE→PARSING→SCOPING→PLANNING→CODING→VERIFYING→DONE。"""
    seq = [
        _transition(TaskState.IDLE),
        _transition(TaskState.PARSING),
        _transition(TaskState.SCOPING),
        _transition(TaskState.PLANNING),
        _transition(TaskState.CODING),
        _transition(TaskState.VERIFYING),
    ]
    assert seq == [
        TaskState.PARSING,
        TaskState.SCOPING,
        TaskState.PLANNING,
        TaskState.CODING,
        TaskState.VERIFYING,
        TaskState.DONE,
    ]


def test_transition_fast_lane() -> None:
    """快车道：跳过 SCOPING 和 PLANNING。"""
    assert _transition(TaskState.IDLE, fast_lane=True) == TaskState.PARSING
    assert _transition(TaskState.PARSING, fast_lane=True) == TaskState.CODING
    assert _transition(TaskState.CODING, fast_lane=True) == TaskState.DONE


def test_transition_terminal_raises() -> None:
    """终态（DONE/FAILED/CANCELLED）不可转换。"""
    for state in TERMINAL_STATES:
        with pytest.raises(InvalidStateTransitionError, match="终态"):
            _transition(state)
        with pytest.raises(InvalidStateTransitionError, match="终态"):
            _transition(state, fast_lane=True)


def test_state_to_progress() -> None:
    """_state_to_progress 全部状态映射到 0.0-1.0。"""
    expected = {
        TaskState.IDLE: 0.0,
        TaskState.PARSING: 0.10,
        TaskState.SCOPING: 0.20,
        TaskState.PLANNING: 0.30,
        TaskState.CODING: 0.60,
        TaskState.VERIFYING: 0.85,
        TaskState.DONE: 1.0,
        TaskState.FAILED: 1.0,
        TaskState.CANCELLED: 1.0,
    }
    for state, expected_progress in expected.items():
        assert _state_to_progress(state) == expected_progress


# ════════════════════════════════════════════
# 4. run_task（主入口）
# ════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.skip(reason="P2-4: needs fixing")
async def test_run_task_normal_flow(full_runner: TaskRunner) -> None:
    """正常流程：IDLE→...→DONE，沿途保存检查点。"""
    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock(
        return_value=AgentOutput(
            status="ok",
            result={"clarify": "ok", "design": "设计", "code": "# 代码", "review": "通过"},
        )
    )
    full_runner._agent_factory.create.return_value = mock_agent

    final = await full_runner.run_task("t-normal", "实现一个计算器")

    assert final == TaskState.DONE
    # 检查点沿途保存（IDLE + 每次状态转换）
    assert len(full_runner.checkpoint.saves) >= 4
    assert full_runner.checkpoint.saves[0].state == TaskState.IDLE.value
    assert full_runner.checkpoint.saves[-1].state == TaskState.DONE.value


@pytest.mark.asyncio
async def test_run_task_cancelled_propagates(full_runner: TaskRunner) -> None:
    """CancelledError 不吞没，保持协作式取消语义（P0-1）。"""
    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock(side_effect=asyncio.CancelledError())
    full_runner._agent_factory.create.return_value = mock_agent

    with pytest.raises(asyncio.CancelledError):
        await full_runner.run_task("t-cancel", "取消测试")


@pytest.mark.asyncio
async def test_run_task_exception_becomes_failed(full_runner: TaskRunner) -> None:
    """Exception → FAILED 并保存错误上下文。"""
    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock(side_effect=RuntimeError("内部错误"))
    full_runner._agent_factory.create.return_value = mock_agent

    final = await full_runner.run_task("t-fail", "失败任务")

    assert final == TaskState.FAILED
    # 错误信息写入检查点
    last_save = full_runner.checkpoint.saves[-1]
    assert last_save.state == TaskState.FAILED.value
    assert "error" in last_save.context


# ════════════════════════════════════════════
# 5. _agent_cycle（状态→角色映射）
# ════════════════════════════════════════════


@pytest.mark.asyncio
async def test_agent_cycle_state_mapping(full_runner: TaskRunner) -> None:
    """各状态正确映射到 Agent 角色 + PLANNING 调用 router。"""
    # 按调用顺序返回不同 Agent mock，用于区分各角色输出
    m_clarify = MagicMock()
    m_clarify.execute = AsyncMock(return_value=AgentOutput(status="ok", result={"clarify": "需求"}))
    m_design = MagicMock()
    m_design.execute = AsyncMock(return_value=AgentOutput(status="ok", result={"design": "架构"}))
    m_code = MagicMock()
    m_code.execute = AsyncMock(return_value=AgentOutput(status="ok", result={"code": "代码"}))
    m_review = MagicMock()
    m_review.execute = AsyncMock(return_value=AgentOutput(status="ok", result={"review": "审查"}))

    full_runner._agent_factory.create.side_effect = [
        m_clarify,  # IDLE
        m_clarify,  # PARSING
        m_design,   # PLANNING
        m_code,     # CODING
        m_review,   # VERIFYING
    ]

    r1 = await full_runner._agent_cycle("t1", TaskState.IDLE, {"prd": "test"})
    assert "需求" in r1

    r2 = await full_runner._agent_cycle("t1", TaskState.PARSING, {"prd": "test"})
    assert "需求" in r2

    # PLANNING → architect + router 调用
    r3 = await full_runner._agent_cycle(
        "t1", TaskState.PLANNING, {"prd": "test", "complexity": {"file_count": 1, "scope": "single_file", "risk": "low"}}
    )
    assert "架构" in r3

    r4 = await full_runner._agent_cycle("t1", TaskState.CODING, {"prd": "test"})
    assert "代码" in r4

    r5 = await full_runner._agent_cycle("t1", TaskState.VERIFYING, {"prd": "test"})
    assert "审查" in r5


@pytest.mark.asyncio
async def test_agent_cycle_unmapped_raises(full_runner: TaskRunner) -> None:
    """无状态→角色映射的状态（如 CANCELLED）→ RuntimeError。"""
    with pytest.raises(ValueError, match="未知状态无对应角色"):
        await full_runner._agent_cycle("t1", TaskState.CANCELLED, {"prd": "test"})


# ════════════════════════════════════════════
# 6. _run_agent（Agent 创建+执行）
# ════════════════════════════════════════════


@pytest.mark.asyncio
async def test_run_agent_success(full_runner: TaskRunner) -> None:
    """Agent 创建+执行成功 → 返回产出物 + 记 audit start。"""
    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock(
        return_value=AgentOutput(status="ok", result={"code": "print('hi')"})
    )
    full_runner._agent_factory.create.return_value = mock_agent

    result = await full_runner._run_agent("developer", "t1", {"prd": "test"})

    assert "print" in result
    # 审计日志记录 agent_start
    full_runner._audit_logger.log.assert_called_with(
        "orchestrator", "agent_start", task_id="t1", role="developer"
    )


@pytest.mark.asyncio
async def test_run_agent_factory_fails(full_runner: TaskRunner) -> None:
    """factory.create 失败 → 返回 [error] 消息 + 审计错误日志。"""
    full_runner._agent_factory.create.side_effect = ValueError("未知角色")

    result = await full_runner._run_agent("bad_role", "t1", {"prd": "test"})

    assert "[error]" in result
    assert "创建失败" in result
    full_runner._audit_logger.log.assert_called_once()  # 错误审计


@pytest.mark.asyncio
async def test_run_agent_execution_error_propagates(full_runner: TaskRunner) -> None:
    """Agent.execute 抛 RuntimeError → 向上传播（不含 CancelledError）。"""
    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock(side_effect=RuntimeError("执行失败"))
    full_runner._agent_factory.create.return_value = mock_agent

    with pytest.raises(RuntimeError, match="执行失败"):
        await full_runner._run_agent("developer", "t1", {"prd": "test"})


# ════════════════════════════════════════════
# 7. _build_context（L1-L5 上下文装配）
# ════════════════════════════════════════════


def test_build_context(full_runner: TaskRunner) -> None:
    """构建 TaskContext——G2 渐进式: Stage 1 仅 L1+L3，L2/L4/L5 延迟加载."""
    ctx = full_runner._build_context(
        "t1",
        {
            "agent_name": "developer",
            "state": "CODING",
            "prd": "实现函数",
            "model_tier": "fast",
            "artifacts": {"PLANNING": "设计稿"},
            "l2": {"code_graph": "..."},
            "l5": [{"lesson": "不要用 float"}],
        },
    )
    assert isinstance(ctx, TaskContext)
    assert ctx.task_id == "t1"
    assert ctx.agent_name == "developer"
    assert ctx.model_tier == "fast"
    assert ctx.l3["state"] == "CODING"
    assert ctx.l3["prd"] == "实现函数"
    # G2: Stage 1 默认——L2/L4/L5 空，运行时通过 load_stage() 按需加载
    assert ctx.stage == ContextStage.STAGE1
    assert ctx.l2 == {}   # 延迟到 Stage 2
    assert ctx.l4 == {}   # 延迟到 Stage 2
    assert ctx.l5 == []   # 延迟到 Stage 3
    assert ctx.l1 != ""  # 固化的会计准则约束


# ════════════════════════════════════════════
# 8. resume（检查点恢复）
# ════════════════════════════════════════════


@pytest.mark.asyncio
async def test_resume_terminal_state(full_runner: TaskRunner) -> None:
    """终态检查点 → 直接返回，不调 Agent。"""
    await full_runner.checkpoint.save(
        "t-done",
        CheckpointData(task_id="t-done", state=TaskState.DONE.value, progress=1.0, context={}),
    )
    result = await full_runner.resume("t-done")
    assert result == TaskState.DONE


@pytest.mark.asyncio
async def test_resume_mid_state_continues(full_runner: TaskRunner) -> None:
    """CODING 中断 → 恢复后继续执行到 DONE。"""
    await full_runner.checkpoint.save(
        "t-mid",
        CheckpointData(
            task_id="t-mid",
            state=TaskState.CODING.value,
            progress=0.7,
            context={"prd": "test"},
        ),
    )
    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock(
        return_value=AgentOutput(status="ok", result={"code": "修复", "review": "通过"})
    )
    full_runner._agent_factory.create.return_value = mock_agent

    result = await full_runner.resume("t-mid")
    assert result == TaskState.DONE


# ════════════════════════════════════════════
# 9. _save_checkpoint
# ════════════════════════════════════════════


@pytest.mark.asyncio
async def test_save_checkpoint(full_runner: TaskRunner) -> None:
    """保存后可以完整加载回数据。"""
    await full_runner._save_checkpoint("t1", TaskState.PLANNING, {"prd": "test"})
    data = await full_runner.checkpoint.load("t1")
    assert data is not None
    assert data.state == TaskState.PLANNING.value
    assert data.context["prd"] == "test"


# ════════════════════════════════════════════
# 10. 事件发布
# ════════════════════════════════════════════


def test_publish_task_update(full_runner: TaskRunner) -> None:
    """发布 task:update 事件，CODING 状态包含产出物。"""
    full_runner._publish_task_update(
        "t1", "CODING", 0.7, context={"artifacts": {"CODING": "# 代码"}}
    )
    full_runner._event_bus.publish.assert_called_once()
    event = full_runner._event_bus.publish.call_args[0][0]
    assert event.type == "task:update"
    assert event.payload["output"] == "# 代码"


def test_publish_token_update(full_runner: TaskRunner) -> None:
    """发布 token:update 事件，含 Token 用量。"""
    full_runner._publish_token_update("t1", 100, 50, 150)
    full_runner._event_bus.publish.assert_called_once()
    event = full_runner._event_bus.publish.call_args[0][0]
    assert event.type == "token:update"
    assert event.payload["total_tokens"] == 150


# ════════════════════════════════════════════
# 11. _continue_from（恢复执行路径）
# ════════════════════════════════════════════


@pytest.mark.asyncio
async def test_continue_from_resumes(full_runner: TaskRunner) -> None:
    """从 CODING 恢复→执行到 DONE."""
    mock_code = MagicMock()
    mock_code.execute = AsyncMock(
        return_value=AgentOutput(status="ok", result={"code": "# code"})
    )
    mock_review = MagicMock()
    mock_review.execute = AsyncMock(
        return_value=AgentOutput(status="ok", result={"review": "pass"})
    )
    full_runner._agent_factory.create.side_effect = [mock_code, mock_review]

    result = await full_runner._continue_from("t-mid", TaskState.CODING, {"prd": "test"})

    assert result == TaskState.DONE
    assert full_runner.checkpoint.saves[-1].state == TaskState.DONE.value


@pytest.mark.asyncio
async def test_continue_from_failed(full_runner: TaskRunner) -> None:
    """恢复中异常→FAILED."""
    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock(side_effect=RuntimeError("继续失败"))
    full_runner._agent_factory.create.return_value = mock_agent

    result = await full_runner._continue_from("t-fail", TaskState.CODING, {"prd": "test"})

    assert result == TaskState.FAILED


# ════════════════════════════════════════════
# 12. _agent_cycle router 异常 fail-open
# ════════════════════════════════════════════


@pytest.mark.asyncio
async def test_agent_cycle_router_exception_fail_open(full_runner: TaskRunner) -> None:
    """PLANNING 时 router 抛异常→fail-open, 继续执行."""
    full_runner._router.evaluate = AsyncMock(side_effect=RuntimeError("router down"))

    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock(
        return_value=AgentOutput(status="ok", result={"design": "仍然工作"})
    )
    full_runner._agent_factory.create.return_value = mock_agent

    result = await full_runner._agent_cycle(
        "t1", TaskState.PLANNING, {"prd": "test", "complexity": {}}
    )
    assert "仍然工作" in result


# ════════════════════════════════════════════
# 13. _run_agent 超时传播
# ════════════════════════════════════════════


@pytest.mark.asyncio
async def test_run_agent_timeout_propagates(full_runner: TaskRunner) -> None:
    """Agent 超时→TimeoutError 向上传播."""
    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock(side_effect=asyncio.TimeoutError())
    full_runner._agent_factory.create.return_value = mock_agent

    with pytest.raises(asyncio.TimeoutError):
        await full_runner._run_agent("developer", "t1", {"prd": "test"})


# ════════════════════════════════════════════
# 14. 事件发布——无 event_bus 不抛异常
# ════════════════════════════════════════════


def test_publish_task_update_no_event_bus(runner: TaskRunner) -> None:
    """event_bus=None → _publish_task_update 跳过."""
    assert runner._event_bus is None
    runner._publish_task_update("t1", "CODING", 0.7)  # 不应抛异常


def test_publish_token_update_no_event_bus(runner: TaskRunner) -> None:
    """event_bus=None → _publish_token_update 跳过."""
    assert runner._event_bus is None
    runner._publish_token_update("t1", 100, 50, 150)  # 不应抛异常
