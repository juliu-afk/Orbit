"""测试 ExecutionContext——thread-local 模式 + 会话确认状态。"""

from orbit.core.context import get_context, set_context, reset_context
from orbit.skills.models import ChatMode


class TestExecutionContext:
    def test_default_mode_is_auto(self):
        ctx = get_context()
        assert ctx.chat_mode == ChatMode.AUTO

    def test_set_mode(self):
        set_context(chat_mode=ChatMode.PLAN)
        ctx = get_context()
        assert ctx.chat_mode == ChatMode.PLAN

    def test_set_partial_preserves_other_fields(self):
        set_context(chat_mode=ChatMode.MANUAL, session_id="sess_1")
        set_context(confirmed_tools={"edit_file"})
        ctx = get_context()
        assert ctx.chat_mode == ChatMode.MANUAL  # 保留
        assert ctx.session_id == "sess_1"  # 保留
        assert ctx.confirmed_tools == {"edit_file"}  # 新值

    def test_reset_clears_context(self):
        set_context(chat_mode=ChatMode.PLAN, session_id="test")
        reset_context()
        ctx = get_context()
        assert ctx.chat_mode == ChatMode.AUTO
        assert ctx.session_id == ""
        assert ctx.confirmed_tools == set()
