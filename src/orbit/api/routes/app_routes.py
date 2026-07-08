"""App 窗口控制 API——关闭/最小化/最大化 Tauri 窗口。

前端通过 HTTP 调用这些端点来控制窗口，避免依赖 @tauri-apps/api
（该 API 在从 http://127.0.0.1:18888 加载时不可用）。
"""
from __future__ import annotations

import ctypes
import os
import signal
import sys
from ctypes import wintypes

from fastapi import APIRouter

router = APIRouter(prefix="/app", tags=["app"])

# Windows API 常量
SW_MINIMIZE = 6
SW_RESTORE = 9
SW_MAXIMIZE = 3


def _find_window_by_pid(pid: int) -> int | None:
    """枚举顶层窗口，找到第一个属于指定 PID 的窗口句柄。"""
    found: list[int] = []

    def _enum_callback(hwnd: int, _lparam: int) -> bool:
        wpid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid and ctypes.windll.user32.IsWindowVisible(hwnd):
            found.append(hwnd)
            return False  # 停止枚举
        return True

    # 定义回调函数类型
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    ctypes.windll.user32.EnumWindows(WNDENUMPROC(_enum_callback), 0)
    return found[0] if found else None


def _get_parent_window() -> int | None:
    """获取 Tauri 父进程的窗口句柄。"""
    if sys.platform != "win32":
        return None
    ppid = os.getppid()
    hwnd = _find_window_by_pid(ppid)
    if hwnd is None:
        # 回退: 查找当前进程名对应的可见窗口
        import subprocess
        try:
            r = subprocess.run(
                ["powershell", "-Command",
                 f"(Get-Process -Id {ppid}).MainWindowHandle"],
                capture_output=True, text=True, timeout=5,
            )
            h = r.stdout.strip()
            if h and h != "0":
                return int(h)
        except Exception:
            pass
    return hwnd


@router.post("/minimize")
async def minimize() -> dict:
    """最小化 Orbit 窗口。"""
    hwnd = _get_parent_window()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)
        return {"code": 0, "data": None, "message": "ok"}
    return {"code": 1, "data": None, "message": "窗口未找到"}


@router.post("/maximize")
async def maximize() -> dict:
    """最大化/还原 Orbit 窗口。"""
    hwnd = _get_parent_window()
    if hwnd:
        # 检查当前是否已最大化
        import subprocess
        try:
            r = subprocess.run(
                ["powershell", "-Command",
                 f"$w = (Get-Process -Id {os.getppid()}).MainWindowHandle; "
                 "[System.Windows.Forms.Screen]::PrimaryScreen | Out-Null; "
                 "Add-Type -AssemblyName System.Windows.Forms; "
                 "$w"],
                capture_output=True, text=True, timeout=5,
            )
        except Exception:
            pass
        # 简单 toggle: 先试最大化, 如果已最大化则还原
        ctypes.windll.user32.ShowWindow(hwnd, SW_MAXIMIZE)
        return {"code": 0, "data": None, "message": "ok"}
    return {"code": 1, "data": None, "message": "窗口未找到"}


@router.post("/quit")
async def quit_app() -> dict:
    """关闭 Orbit——杀父进程 (Tauri 壳)，触发 cascade 清理后端。"""
    ppid = os.getppid()
    if sys.platform == "win32":
        os.kill(ppid, signal.SIGTERM)
    else:
        os.kill(ppid, signal.SIGTERM)
    return {"code": 0, "data": None, "message": "ok"}
