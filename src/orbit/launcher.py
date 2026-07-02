"""PyInstaller 启动入口——启动 uvicorn 服务。"""

from __future__ import annotations

import os
import sys

import orbit.api.routes.files_routes  # noqa: F401
import orbit.api.routes.git_routes  # noqa: F401
import orbit.api.routes.review  # noqa: F401
import orbit.files.service  # noqa: F401
import orbit.lsp.service  # noqa: F401

# Step 9: 强制 PyInstaller 打包新增模块
import orbit.review.models  # noqa: F401
import orbit.review.service  # noqa: F401

# Part A: 项目说明书模块
import orbit.brief  # noqa: F401

# Part B: Ponytail 决策阶梯
import orbit.prompt.ponytail_rules  # noqa: F401
import orbit.review.ponytail  # noqa: F401


def main() -> None:
    # WHY chdir: 双击启动时工作目录不是 exe 所在目录，
    # config.py 相对路径 (data/, configs/) 无法正确解析。
    # PyInstaller 单文件模式：sys.executable 指向原始 exe 路径。
    _exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    os.chdir(_exe_dir)

    # WHY 写日志文件：Windows GUI 子系统无控制台，CREATE_NO_WINDOW 隐藏窗口，
    # 所有错误信息不可见。写入 orbit_startup.log 方便排查启动问题。
    _log_path = os.path.join(_exe_dir, "orbit_startup.log")
    _log_fh = open(_log_path, "w", encoding="utf-8")  # noqa: SIM115
    sys.stdout = _log_fh
    sys.stderr = _log_fh
    print(f"Orbit launcher started, exe_dir={_exe_dir}", flush=True)

    import uvicorn

    from orbit.api.main import app

    host = "0.0.0.0"  # WHY 0.0.0.0: WebView2 用 localhost/IPv6 可能连不上 127.0.0.1
    port = 18888

    print(f"Orbit 启动: http://{host}:{port} (cwd={os.getcwd()})")
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    main()
