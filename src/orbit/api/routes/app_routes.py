"""App window control API."""
from __future__ import annotations
import ctypes, os, subprocess, sys
from fastapi import APIRouter

router = APIRouter(prefix="/app", tags=["app"])
SW_MINIMIZE, SW_MAXIMIZE = 6, 3

def _get_parent_hwnd() -> int | None:
    try:
        r = subprocess.run(
            ["powershell","-NoProfile","-Command",
             f"(Get-Process -Id {os.getppid()}).MainWindowHandle"],
            capture_output=True,text=True,timeout=5,
            creationflags=0x08000000)
        h = r.stdout.strip()
        return int(h) if h and h != "0" else None
    except Exception:
        return None

@router.post("/minimize")
async def minimize():
    h = _get_parent_hwnd()
    if h: ctypes.windll.user32.ShowWindow(h, SW_MINIMIZE)
    return {"code":0,"data":None,"message":"ok" if h else "window not found"}

@router.post("/maximize")
async def maximize():
    h = _get_parent_hwnd()
    if h: ctypes.windll.user32.ShowWindow(h, SW_MAXIMIZE)
    return {"code":0,"data":None,"message":"ok" if h else "window not found"}

@router.post("/quit")
async def quit_app():
    subprocess.run(["taskkill","/F","/PID",str(os.getppid())],
                   capture_output=True,creationflags=0x08000000)
    return {"code":0,"data":None,"message":"ok"}
