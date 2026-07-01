"""SSE 流式端点单元测试——token 清理 + Pydantic 模型校验。"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from orbit.stream.cancellation import CancellationToken


class TestTokenCleanup:
    """_cleanup_expired_tokens 纯逻辑测试。"""

    def test_cleanup_expired_removes_old_tokens(self):
        """超过 TTL 的 token→被清理。"""
        from orbit.stream.sse import _TOKENS, _TOKEN_TTL_SECONDS, _cleanup_expired_tokens

        _TOKENS.clear()
        # 添加一个过期 token（300+ 秒前）
        old_time = time.time() - _TOKEN_TTL_SECONDS - 10
        _TOKENS["task-old"] = (CancellationToken(), old_time)
        # 添加一个有效 token
        _TOKENS["task-new"] = (CancellationToken(), time.time())

        cleaned = _cleanup_expired_tokens()
        assert cleaned == 1
        assert "task-old" not in _TOKENS
        assert "task-new" in _TOKENS

    def test_cleanup_no_expired(self):
        """没有过期 token→返回 0。"""
        from orbit.stream.sse import _TOKENS, _cleanup_expired_tokens

        _TOKENS.clear()
        _TOKENS["task-1"] = (CancellationToken(), time.time())

        cleaned = _cleanup_expired_tokens()
        assert cleaned == 0
        assert "task-1" in _TOKENS

    def test_cleanup_empty_dict(self):
        """空 token 表→返回 0。"""
        from orbit.stream.sse import _TOKENS, _cleanup_expired_tokens

        _TOKENS.clear()
        assert _cleanup_expired_tokens() == 0


class TestSSEModels:
    """AgentRunRequest / AgentCancelRequest Pydantic 校验。"""

    def test_agent_run_request_valid(self):
        from orbit.stream.sse import AgentRunRequest

        req = AgentRunRequest(task="实现登录", role="developer")
        assert req.task == "实现登录"
        assert req.role == "developer"
        assert req.context == {}

    def test_agent_run_request_empty_task_rejected(self):
        from orbit.stream.sse import AgentRunRequest

        with pytest.raises(Exception):
            AgentRunRequest(task="", role="developer")

    def test_agent_cancel_request_valid(self):
        from orbit.stream.sse import AgentCancelRequest

        req = AgentCancelRequest(task_id="task-001")
        assert req.task_id == "task-001"

    def test_agent_cancel_request_empty_rejected(self):
        from orbit.stream.sse import AgentCancelRequest

        with pytest.raises(Exception):
            AgentCancelRequest(task_id="")
