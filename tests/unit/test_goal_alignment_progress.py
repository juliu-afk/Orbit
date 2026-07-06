"""Unit tests: AlignmentCheck (26%→) + ProgressTracker (25%→).

Both are pure-logic modules when LLM is mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.goal.alignment import ALIGNMENT_CHECK_PROMPT, AlignmentCheck, AlignmentResult
from orbit.goal.progress_tracker import ProgressTracker


# ── AlignmentResult ───────────────────────────────────────────────


def test_alignment_result_defaults():
    r = AlignmentResult()
    assert r.aligned is True
    assert r.should_pause is False


def test_alignment_result_misaligned():
    r = AlignmentResult(aligned=False, deviation_task="t2", should_pause=True)
    assert r.aligned is False
    assert r.deviation_task == "t2"
    assert r.should_pause is True


# ── AlignmentCheck —— no LLM ─────────────────────────────────────


@pytest.mark.asyncio
async def test_alignment_skip_on_empty_progress():
    """0 个完成 → 跳过检查。"""
    check = AlignmentCheck()
    result = await check.check(MagicMock(), {"t1": "pending", "t2": "in_progress"})
    assert result.aligned is True


@pytest.mark.asyncio
async def test_alignment_skip_not_interval():
    """完成数不是 CHECK_INTERVAL=5 的倍数 → 跳过。"""
    check = AlignmentCheck()
    progress = {f"t{i}": "done" for i in range(3)}  # 3 done, not divisible by 5
    result = await check.check(MagicMock(), progress)
    assert result.aligned is True


@pytest.mark.asyncio
async def test_alignment_mock_mode():
    """无 LLM → mock mode 默认对齐。"""
    check = AlignmentCheck(llm=None)
    progress = {f"t{i}": "done" for i in range(5)}  # exactly 5 done
    result = await check.check(MagicMock(), progress)
    assert result.aligned is True
    assert "mock" in result.message


# ── AlignmentCheck —— with LLM ───────────────────────────────────


@pytest.mark.asyncio
async def test_alignment_llm_aligned():
    """LLM 返回 aligned=True。"""
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock()
    mock_llm.generate.return_value.content = '{"aligned": true}'
    goal = MagicMock()
    goal.description = "实现支付模块"
    goal.constraints = []
    goal.consecutive_misalignments = 0

    check = AlignmentCheck(llm=mock_llm)
    progress = {f"t{i}": "done" for i in range(5)}
    result = await check.check(goal, progress)
    assert result.aligned is True
    assert goal.consecutive_misalignments == 0


@pytest.mark.asyncio
async def test_alignment_llm_not_aligned_first_time():
    """第一次不对齐 → aligned=False, should_pause=False。"""
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock()
    mock_llm.generate.return_value.content = '{"aligned": false, "deviation_task": "t3"}'
    goal = MagicMock()
    goal.description = "重构调度器"
    goal.constraints = []
    goal.consecutive_misalignments = 0

    check = AlignmentCheck(llm=mock_llm)
    progress = {f"t{i}": "done" for i in range(5)}
    result = await check.check(goal, progress)
    assert result.aligned is False
    assert result.should_pause is False
    assert goal.consecutive_misalignments == 1


@pytest.mark.asyncio
async def test_alignment_llm_not_aligned_second_time():
    """连续 2 次不对齐 → should_pause=True。"""
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock()
    mock_llm.generate.return_value.content = '{"aligned": false}'
    goal = MagicMock()
    goal.description = "重构"
    goal.constraints = []
    goal.consecutive_misalignments = 1  # 上次已经不对齐

    check = AlignmentCheck(llm=mock_llm)
    progress = {f"t{i}": "done" for i in range(5)}
    result = await check.check(goal, progress)
    assert result.aligned is False
    assert result.should_pause is True
    assert goal.consecutive_misalignments == 2


@pytest.mark.asyncio
async def test_alignment_llm_exception_fail_open():
    """LLM 异常 → fail-open: aligned=True。"""
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(side_effect=RuntimeError("LLM down"))
    goal = MagicMock()
    goal.description = "test"

    check = AlignmentCheck(llm=mock_llm)
    progress = {f"t{i}": "done" for i in range(5)}
    result = await check.check(goal, progress)
    assert result.aligned is True


# ── ProgressTracker._determine_status ─────────────────────────────


def test_determine_status_ok_all_passed():
    """compose ok + 验证全通过 → done。"""
    s = ProgressTracker._determine_status("t1", {"status": "ok"}, [{"passed": True}])
    assert s == "done"


def test_determine_status_ok_not_passed():
    """compose ok + 验证部分未通过 → in_progress。"""
    s = ProgressTracker._determine_status("t1", {"status": "ok"}, [{"passed": False}])
    assert s == "in_progress"


def test_determine_status_ok_no_verification():
    """compose ok + 无验证结果 → done。"""
    s = ProgressTracker._determine_status("t1", {"status": "ok"}, [])
    assert s == "done"


def test_determine_status_error():
    s = ProgressTracker._determine_status("t1", {"status": "error"}, [])
    assert s == "failed"


def test_determine_status_critique_loop():
    s = ProgressTracker._determine_status("t1", {"status": "critique_loop"}, [])
    assert s == "retry"


def test_determine_status_default():
    s = ProgressTracker._determine_status("t1", {"status": "unknown"}, [])
    assert s == "in_progress"


# ── ProgressTracker.update ───────────────────────────────────────


@pytest.mark.asyncio
async def test_update_with_compose_results():
    from orbit.goal.models import GoalSession

    tracker = ProgressTracker()
    goal = GoalSession(goal_id="g1", description="test")
    result = await tracker.update(
        goal,
        compose_results={
            "tasks": {
                "t1": {"status": "ok"},
                "t2": {"status": "error"},
            }
        },
    )
    assert goal.sub_tasks["t1"] == "done"
    assert goal.sub_tasks["t2"] == "failed"


@pytest.mark.asyncio
async def test_update_done_stays_done():
    """done 状态不倒退。"""
    from orbit.goal.models import GoalSession

    tracker = ProgressTracker()
    goal = GoalSession(goal_id="g1", description="test", sub_tasks={"t1": "done"})
    result = await tracker.update(
        goal,
        compose_results={"tasks": {"t1": {"status": "error"}}},
    )
    assert goal.sub_tasks["t1"] == "done"  # 不倒退


@pytest.mark.asyncio
async def test_update_empty():
    from orbit.goal.models import GoalSession

    tracker = ProgressTracker()
    goal = GoalSession(goal_id="g1", description="test")
    result = await tracker.update(goal)
    assert goal.sub_tasks == {}


# ── ProgressTracker.build_progress_prompt ────────────────────────


def test_build_progress_prompt():
    from orbit.goal.models import GoalSession

    tracker = ProgressTracker()
    goal = GoalSession(
        goal_id="g1", description="test",
        sub_tasks={"t1": "done", "t2": "in_progress", "t3": "pending"},
    )
    prompt = tracker.build_progress_prompt(goal)
    assert "任务进度" in prompt
    assert "done" in prompt
    assert "t1" in prompt
    assert "t2" in prompt


def test_build_checklist():
    from orbit.goal.models import GoalSession

    tracker = ProgressTracker()
    goal = GoalSession(
        goal_id="g1", description="test",
        sub_tasks={"t1": "done", "t2": "pending"},
    )
    cl = tracker.build_checklist(goal)
    assert len(cl) == 2
    assert "[x]" in cl[0]
    assert "[ ]" in cl[1]
