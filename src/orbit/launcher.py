"""PyInstaller 启动入口——启动 uvicorn + 自动打开浏览器。
"""

from __future__ import annotations

import os
import sys
import threading
import webbrowser


def _open_browser(url: str, delay: float = 1.5) -> None:
    """延迟打开浏览器——等 uvicorn 先绑定端口。"""
    import time
    time.sleep(delay)
    webbrowser.open(url)


def main() -> None:
    # Windows GUI 子系统无控制台，sys.stdout/stderr 为 None，
    # uvicorn 日志初始化 .isatty() 调用会崩
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    import uvicorn
    from orbit.api.main import app

    host = "127.0.0.1"
    port = 18888

    url = f"http://{host}:{port}"
    threading.Thread(target=_open_browser, args=(url,), daemon=True).start()

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    main()
