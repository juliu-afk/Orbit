"""测试 TaskQualityScorer——三维度评分纯函数."""

from __future__ import annotations

import pytest

from orbit.modes.scorer import TaskQualityScorer


# ════════════════════════════════════════════
# 维度 1: 用户反馈
# ════════════════════════════════════════════


def test_user_satisfaction_empty_history() -> None:
    """空聊天记录 → 默认 0.5."""
    result = TaskQualityScorer.score_user_satisfaction(None)
    assert result.score == 0.5
    assert result.detail["reason"] == "无聊天记录，默认中性"


def test_user_satisfaction_positive() -> None:
    """全正面反馈 → >0.5."""
    history = [
        {"role": "user", "content": "好的，就这样"},
        {"role": "user", "content": "对，没问题"},
        {"role": "user", "content": "确认"},
    ]
    result = TaskQualityScorer.score_user_satisfaction(history)
    assert result.score > 0.5
    assert result.detail["positive_msgs"] == 3


def test_user_satisfaction_negative() -> None:
    """有负面反馈 → <0.5."""
    history = [
        {"role": "user", "content": "不对，不是这个"},
        {"role": "user", "content": "重来"},
    ]
    result = TaskQualityScorer.score_user_satisfaction(history)
    assert result.score < 0.5
    assert result.detail["negative_msgs"] == 2


def test_user_satisfaction_abandoned() -> None:
    """用户放弃 → 0."""
    history = [
        {"role": "user", "content": "算了，不做了"},
    ]
    result = TaskQualityScorer.score_user_satisfaction(history)
    assert result.score == 0.0
    assert result.detail["abandoned"] is True


def test_user_satisfaction_ignores_assistant() -> None:
    """只统计 user 角色消息."""
    history = [
        {"role": "assistant", "content": "不对不对——这是 AI 说的"},
        {"role": "user", "content": "好的"},
    ]
    result = TaskQualityScorer.score_user_satisfaction(history)
    assert result.detail["positive_msgs"] == 1


# ════════════════════════════════════════════
# 维度 2: 会话质量
# ════════════════════════════════════════════


def test_session_quality_no_clarifier() -> None:
    """非 PARSING 任务 → 0.5."""
    result = TaskQualityScorer.score_session_quality(None)
    assert result.score == 0.5


def test_session_quality_no_prd() -> None:
    """PRD 未产出 → 0.2."""
    result = TaskQualityScorer.score_session_quality(
        {"clarification_status": "clarifying", "structured_prd": None}
    )
    assert result.score == 0.2


def test_session_quality_ready_with_full_prd() -> None:
    """ready + 完整 PRD → 高分."""
    result = TaskQualityScorer.score_session_quality({
        "clarification_status": "ready",
        "validation_passed": True,
        "structured_prd": {
            "goal": "实现多币种折算功能，支持实时汇率转换和汇兑损益计算",
            "scope": "改动 exchange_rate.py 和 general_ledger.py，新增折算接口，不做前端汇率面板",
            "acceptance_criteria": [
                "输入 USD 金额返回 CNY 等值",
                "汇率变更后自动重算",
                "generate journal entry with correct debit/credit",
            ],
        },
    })
    assert result.score >= 0.7  # ready + validation + 完整 PRD


def test_session_quality_empty_prd_fields() -> None:
    """空 goal/scope/ac → 低分."""
    result = TaskQualityScorer.score_session_quality({
        "clarification_status": "clarifying",
        "structured_prd": {
            "goal": "",
            "scope": "",
            "acceptance_criteria": [],
        },
    })
    assert result.score < 0.3


# ════════════════════════════════════════════
# 维度 3: 交付结果
# ════════════════════════════════════════════


def test_delivery_done_with_review() -> None:
    """DONE + 审查通过 + 无回归 → ~1.0."""
    result = TaskQualityScorer.score_delivery("DONE", review_passed=True, has_regression=False)
    assert abs(result.score - 1.0) < 0.001  # 浮点: 0.4+0.3+0.2+0.1


def test_delivery_failed() -> None:
    """FAILED → 低分."""
    result = TaskQualityScorer.score_delivery("FAILED")
    assert result.score < 0.4


def test_delivery_with_regression() -> None:
    """DONE 但有回归 bug → 扣分."""
    result_no = TaskQualityScorer.score_delivery("DONE", review_passed=True, has_regression=False)
    result_yes = TaskQualityScorer.score_delivery("DONE", review_passed=True, has_regression=True)
    assert result_yes.score < result_no.score


# ════════════════════════════════════════════
# 综合评分
# ════════════════════════════════════════════


def test_score_integration() -> None:
    """综合评分: 三个维度加权."""
    quality = TaskQualityScorer.score(
        task_id="t1",
        chat_history=[{"role": "user", "content": "好的，确认"}],
        clarifier_result={
            "clarification_status": "ready",
            "structured_prd": {
                "goal": "实现多币种折算",
                "scope": "改动汇率模块和总账模块",
                "acceptance_criteria": ["返回折算金额", "汇率重算"],
            },
        },
        task_state="DONE",
        review_passed=True,
    )
    assert 0 <= quality.total <= 1
    assert quality.task_id == "t1"
    assert "dim1" in quality.detail
    assert "dim2" in quality.detail
    assert "dim3" in quality.detail
