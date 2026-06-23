"""Step 6.1 WebSocket 模块。

原生 WebSocket（RFC 6455）实现驾驶舱实时推送。
ConnectionManager 管理连接 + 任务订阅，router 定义端点 + 广播协程。
"""

from orbit.ws.manager import ConnectionManager
from orbit.ws.router import router, start_broadcaster

__all__ = [
    "ConnectionManager",
    "router",
    "start_broadcaster",
]
