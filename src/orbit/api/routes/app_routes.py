"""App window control API."""
from __future__ import annotations
import ctypes, os, signal, sys, subprocess
from ctypes import wintypes
from fastapi import APIRouter

router = APIRouter(prefix="/app", tags=["app"])

SW_MINIMIZE, SW_MAXIMIZE = 6, 3

def _find_window() -> int | None:
    if sys.platform != "win32":
        return None
    ppid = os.getppid()
    try:
        r = subprocess.run(["powershell","-Command",
            f"(Get-Process -Id {ppid}).MainWindowHandle"],
            capture_output=True, text=True, timeout=5)
        h = r.stdout.strip()
        return int(h) if h and h != "0" else None
    except Exception:
        return None

@router.post("/minimize")
async def minimize() -> dict:
    hwnd = _find_window()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)
        return {"code": 0, "data": None, "message": "ok"}
    return {"code": 1, "data": None, "message": "window not found"}

@router.post("/maximize")
async def maximize() -> dict:
    hwnd = _find_window()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, SW_MAXIMIZE)
        return {"code": 0, "data": None, "message": "ok"}
    return {"code": 1, "data": None, "message": "window not found"}

@router.post("/quit")
async def quit_app() -> dict:
    os.kill(os.getppid(), signal.SIGTERM)
    return {"code": 0, "data": None, "message": "ok"}
