"""App window control API."""
from __future__ import annotations
import ctypes, os, subprocess
from fastapi import APIRouter

router = APIRouter(prefix="/app", tags=["app"])
SW_MINIMIZE, SW_MAXIMIZE = 6, 3

def _hwnd() -> int | None:
    """查找 Orbit 主窗口句柄——先按标题, 再枚举匹配 PID。"""
    # 方法1: FindWindowW 按窗口标题查找
    h = ctypes.windll.user32.FindWindowW(None, "Orbit")
    if h and ctypes.windll.user32.IsWindowVisible(h):
        return h
    # 方法2: 枚举窗口匹配父进程 PID
    ppid = os.getppid()
    result = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    def callback(hwnd, _):
        pid = ctypes.c_uint32()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == ppid and ctypes.windll.user32.IsWindowVisible(hwnd):
            result.append(hwnd)
            return False
        return True
    ctypes.windll.user32.EnumWindows(WNDENUMPROC(callback), 0)
    return result[0] if result else None

@router.post("/minimize")
async def minimize():
    h = _hwnd()
    if h: ctypes.windll.user32.ShowWindow(h, SW_MINIMIZE)
    return {"code":0,"data":None,"message":"ok" if h else "no hwnd"}

@router.post("/maximize")
async def maximize():
    h = _hwnd()
    if h: ctypes.windll.user32.ShowWindow(h, SW_MAXIMIZE)
    return {"code":0,"data":None,"message":"ok" if h else "no hwnd"}

@router.post("/quit")
async def quit_app():
    # 按进程名杀——PPID 在 Windows 上不可靠
    subprocess.run(["taskkill","/F","/IM","Orbit.exe"],capture_output=True)
    subprocess.run(["taskkill","/F","/IM","orbit-backend.exe"],capture_output=True)
    return {"code":0,"data":None,"message":"ok"}
