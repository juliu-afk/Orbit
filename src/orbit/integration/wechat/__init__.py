"""微信集成模块——iLink Bot API 通道适配。

双向对话模型：微信是 Orbit 驾驶舱的伴随通道——
用户可在微信中启动任务/查询进度/审批，Orbit 可推送完成/失败/审批通知。

入口函数：
- start(bindings_db_path: str) → 启动 cc-weixin 子进程 + 事件订阅
- stop() → 停止子进程 + 取消订阅
"""

from orbit.integration.wechat.bind import BindManager
from orbit.integration.wechat.channel import WechatChannel
from orbit.integration.wechat.outbound import OutboundQueue
from orbit.integration.wechat.router import MessageRouter

__all__ = [
    "BindManager",
    "MessageRouter",
    "OutboundQueue",
    "WechatChannel",
]
