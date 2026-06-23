"""PyInstaller 启动入口——直接 import 后启动 uvicorn。

WHY 不用 "orbit.api.main:app" 字符串：
PyInstaller 的模块查找机制与 uvicorn importer 不兼容，
直接 import app 对象是最可靠的方式。
"""
from __future__ import annotations

import sys
import threading
import webbrowser


def main() -> None:
    import uvicorn
    from orbit.api.main import app

    host = "127.0.0.1"
    port = 18888

    # 自动打开浏览器（仅 exe 构建）
    def open_browser() -> None:
        import time

        time.sleep(1.5)
        webbrowser.open(f"http://{host}:{port}")

    if getattr(sys, "frozen", False):
        threading.Thread(target=open_browser, daemon=True).start()

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    main()
