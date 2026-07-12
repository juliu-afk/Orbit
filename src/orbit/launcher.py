"""PyInstaller 启动入口。"""
from __future__ import annotations
import os, sys
_exe_dir = os.path.dirname(os.path.abspath(sys.executable))
_log = open(os.path.join(_exe_dir, "orbit_startup.log"), "w", encoding="utf-8")
if sys.stdout is None: sys.stdout = _log
if sys.stderr is None: sys.stderr = _log
print("Orbit launcher starting...", flush=True)
try:
    # PyInstaller 隐式导入清单——懒加载路由模块需静态 import 才能被 PyInstaller 发现
    import orbit.api.routes.files_routes, orbit.api.routes.git_routes, orbit.api.routes.review  # noqa
    import orbit.api.routes.tasks, orbit.api.routes.knowledge  # noqa
    import orbit.api.routes.compliance, orbit.api.routes.observability  # noqa
    import orbit.api.routes.backup, orbit.api.routes.versioning  # noqa
    import orbit.api.routes.chat, orbit.api.routes.agent_llm  # noqa
    import orbit.api.routes.compose, orbit.api.routes.dream  # noqa
    import orbit.api.routes.goal, orbit.api.routes.loop  # noqa
    import orbit.api.routes.sessions, orbit.api.routes.projects  # noqa
    import orbit.api.routes.schedule  # noqa
    import orbit.api.routes.codegraph_routes, orbit.api.routes.search_routes  # noqa
    import orbit.api.routes.tests_routes, orbit.api.routes.blame_routes  # noqa
    import orbit.api.routes.insights_routes, orbit.api.routes.compliance_routes  # noqa
    import orbit.api.routes.terminal_routes, orbit.api.routes.diagnostics_ws  # noqa
    import orbit.api.routes.config_routes  # noqa
    import orbit.api.routes.wechat_routes  # noqa
    import orbit.api.routes.health  # noqa
    import orbit.files.service, orbit.lsp.service  # noqa
    import orbit.review.models, orbit.review.service  # noqa
    import orbit.brief  # noqa
    import orbit.prompt.ponytail_rules, orbit.review.ponytail  # noqa
    import orbit.integration.wechat  # noqa
except Exception as e:
    print(f"Import error: {e}", flush=True)
    import traceback; traceback.print_exc(file=_log)
    sys.exit(1)

def main():
    print(f"Orbit main() starting, cwd={os.getcwd()}", flush=True)
    try:
        # 阻止 Windows 休眠/屏保——Orbit 长时间跑 Agent 任务期间 PC 不能休眠
        # SetThreadExecutionState 作用于调用线程，uvicorn 存活期间持续生效，进程退出自动恢复
        if sys.platform == "win32":
            import ctypes
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            ES_DISPLAY_REQUIRED = 0x00000002
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            )
            print("Orbit: 已启用休眠阻止", flush=True)

        import uvicorn
        from orbit.api.main import app
        host, port = "0.0.0.0", 18888
        print(f"Orbit: http://{host}:{port}", flush=True)
        uvicorn.run(app, host=host, port=port, log_level="info")
    except Exception as e:
        print(f"Startup error: {e}", flush=True)
        import traceback; traceback.print_exc(file=_log)
        sys.exit(1)

if __name__ == "__main__": main()
