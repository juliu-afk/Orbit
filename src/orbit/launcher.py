"""PyInstaller/Tauri 启动入口——直接 import 后启动 uvicorn。
Tauri 主进程 spawn 此脚本后，加载 http://127.0.0.1:18888 到 WebView。
"""
from __future__ import annotations

import os
import sys


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

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    main()
