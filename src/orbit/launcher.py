"""PyInstaller 启动入口。"""
from __future__ import annotations
import os, sys
_exe_dir = os.path.dirname(os.path.abspath(sys.executable))
_log = open(os.path.join(_exe_dir, "orbit_startup.log"), "w", encoding="utf-8")
if sys.stdout is None: sys.stdout = _log
if sys.stderr is None: sys.stderr = _log
print("Orbit launcher starting...", flush=True)
try:
    import orbit.api.routes.files_routes, orbit.api.routes.git_routes, orbit.api.routes.review  # noqa
    import orbit.files.service, orbit.lsp.service  # noqa
    import orbit.review.models, orbit.review.service  # noqa
    import orbit.brief  # noqa
    import orbit.prompt.ponytail_rules, orbit.review.ponytail  # noqa
except Exception as e:
    print(f"Import error: {e}", flush=True)
    import traceback; traceback.print_exc(file=_log)
    sys.exit(1)

def main():
    print(f"Orbit main() starting, cwd={os.getcwd()}", flush=True)
    try:
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
