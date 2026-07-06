"""微信消息路由——意图分类 + 命令处理。

WHY 用纯规则匹配而非 LLM 分类：消息格式固定（@Orbit 前缀 + 关键词），
规则匹配确定性 100%，无幻觉风险，延迟 <1ms vs LLM 的 500ms+。
"""

from __future__ import annotations

import re
from collections.abc import Callable

import structlog

from orbit.integration.wechat.models import MessageIntent, WechatMessage

logger = structlog.get_logger("orbit.wechat.router")

# ── 路由表：正则模式 → (category, task_id提取组索引) ──
_ROUTE_TABLE: list[tuple[re.Pattern[str], str, int | None]] = [
    # 格式: (编译后正则, 意图类别, task_id 捕获组索引)
    (re.compile(r"@Orbit\s+(?:启动|开始|新建|start|create)\s+(.+)", re.I), "create_task", None),
    (re.compile(r"@Orbit\s+(?:查|查询|状态|status|query)\s+#?(\d+)", re.I), "query_task", 1),
    (re.compile(r"@Orbit\s+(?:同意|批准|approve|ok)\s+#?(\d+)", re.I), "approve", 1),
    (re.compile(r"@Orbit\s+(?:拒绝|reject|no)\s+#?(\d+)", re.I), "reject", 1),
    (re.compile(r"@Orbit\s+(?:帮助|help)\s*$", re.I), "help", None),
    (re.compile(r"@Orbit\s*(?:状态|status)\s*$", re.I), "status", None),
    # P1: 问答——匹配 "xxx在哪" / "where is" / "找xxx"
    # WHY qa 不含「查」：与 query_task 二义性。查数字→query_task，找描述→qa。
    (re.compile(r"@Orbit\s+(?:找|where\s+is)\s+(.+)", re.I), "qa", None),
]

# ── 帮助文本 ──────────────────────────────────────────
HELP_TEXT = """📋 Orbit 可用命令：

  @Orbit 启动 [描述]   创建新任务
  @Orbit 查 [ID]      查询任务进度
  @Orbit 同意 [ID]    批准合并请求
  @Orbit 拒绝 [ID]    拒绝合并请求
  @Orbit 状态          查看所有进行中任务
  @Orbit 帮助          查看本消息

💡 示例：
  @Orbit 启动 给 keshen 项目加一个导出 PDF 的功能
  @Orbit 查 42
  @Orbit 同意 42"""

UNKNOWN_RESPONSE = "未识别的命令。回复「@Orbit 帮助」查看可用命令。"


# ── 处理器类型 ─────────────────────────────────────────
MessageHandler = Callable[[WechatMessage, MessageIntent], str]


class MessageRouter:
    """微信消息路由——分类入站消息，分发到对应处理器。

    用法:
        router = MessageRouter()
        router.register("create_task", handle_create_task)
        response = await router.route(message)
    """

    def __init__(self) -> None:
        self._handlers: dict[str, MessageHandler] = {}

    def register(self, category: str, handler: MessageHandler) -> None:
        """注册某类意图的处理器。"""
        self._handlers[category] = handler
        logger.info("wechat_handler_registered", category=category)

    def classify(self, message: WechatMessage) -> MessageIntent:
        """对入站消息进行意图分类（纯规则匹配）。"""
        content = message.content.strip()

        for pattern, category, task_id_group in _ROUTE_TABLE:
            match = pattern.match(content)
            if match:
                task_id = None
                # 尝试捕获整数的 task_id
                if task_id_group is not None:
                    try:
                        task_id = int(match.group(task_id_group))
                    except (IndexError, ValueError):
                        pass
                payload = match.group(1) if category in ("create_task", "qa") else ""
                return MessageIntent(
                    category=category,  # type: ignore[arg-type]
                    task_id=task_id,
                    payload=payload,
                )

        return MessageIntent(category="unknown", payload=content)

    async def route(self, message: WechatMessage) -> str:
        """分类并处理消息。返回响应文本。"""
        intent = self.classify(message)
        logger.debug("wechat_message_routed", intent=intent.category)

        handler = self._handlers.get(intent.category)
        if handler:
            try:
                return handler(message, intent)
            except Exception as e:
                logger.error("wechat_handler_error", category=intent.category, error=str(e))
                return f"处理失败：{e}"

        # 未注册处理器的意图——返回通用响应
        if intent.category == "help":
            return HELP_TEXT
        if intent.category == "unknown":
            return UNKNOWN_RESPONSE
        return f"命令 '{intent.category}' 暂不支持。"
