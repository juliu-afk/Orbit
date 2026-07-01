"""ChatChain——WebSocket Chat → ClarifierAgent → Task creation 构建器。

模拟用户通过驾驶舱聊天界面与 Orbit 交互的完整流程：
连接→对话→需求澄清→确认→创建任务。

使用示例:
    chain = ChatChain()
    result = await chain.dialog(messages).confirm_task_creation().run()
    chain.assert_task_created()
"""

from __future__ import annotations

from typing import Any

from tests.lib.factories.agent import create_agent_output


class ChatChain:
    """WebSocket Chat → ClarifierAgent → Task creation 构建器。"""

    def __init__(self, mocks: dict[str, Any] | None = None) -> None:
        mocks = mocks or {}
        self._messages: list[dict[str, str]] = []
        self._task_id: str | None = None
        self._task_description: str = ""

        # 运行结果
        self.dialog_history: list[dict[str, str]] = []
        self.clarification_asked: bool = False
        self.task_created: bool = False
        self.created_task_id: str = ""

    # ── 链式配置 ──────────────────────────────────────────

    def dialog(self, messages: list[dict[str, str]]) -> "ChatChain":
        """设置对话消息列表。

        每轮对话格式: {"role": "user"|"assistant", "content": "..."}

        Args:
            messages: 对话消息列表
        """
        self._messages = messages
        self.dialog_history = list(messages)
        return self

    def confirm_task_creation(self, task_id: str | None = None) -> "ChatChain":
        """确认创建任务。

        Args:
            task_id: 任务 ID（None→自动生成）
        """
        self._task_id = task_id or "chat-task-001"
        self._task_description = self._messages[-1]["content"] if self._messages else "unknown task"
        return self

    # ── 执行 ──────────────────────────────────────────────

    async def run(self) -> dict[str, Any]:
        """模拟 WebSocket 对话流程。

        Returns:
            {status, task_created, task_id, clarification_asked, rounds}
        """
        if not self._messages:
            raise ValueError("must call dialog() before run()")

        # 模拟需求澄清检测
        user_msgs = [m for m in self._messages if m.get("role") == "user"]
        if len(user_msgs) >= 2:
            self.clarification_asked = True

        # 模拟 ClarifierAgent 输出
        if self._task_id:
            self.task_created = True
            self.created_task_id = self._task_id
        elif len(user_msgs) >= 1 and len(user_msgs[-1].get("content", "")) > 20:
            # 足够详细→自动创建任务
            self.task_created = True
            self.created_task_id = "chat-auto-001"

        return {
            "status": "ok",
            "task_created": self.task_created,
            "task_id": self.created_task_id,
            "clarification_asked": self.clarification_asked,
            "rounds": len(self._messages),
            "task_description": self._task_description or (user_msgs[-1]["content"] if user_msgs else ""),
        }

    # ── 断言 ──────────────────────────────────────────────

    def assert_task_created(self) -> None:
        """断言任务已创建。"""
        assert self.task_created, "任务未创建"
        assert self.created_task_id, "任务 ID 为空"

    def assert_clarification_asked(self) -> None:
        """断言触发了需求澄清。"""
        assert self.clarification_asked, "未触发需求澄清"

    def reset(self) -> None:
        self._messages.clear()
        self._task_id = None
        self._task_description = ""
        self.dialog_history.clear()
        self.clarification_asked = False
        self.task_created = False
        self.created_task_id = ""
