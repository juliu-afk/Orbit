"""V15.1 多模态 P3：GUI Agent Tool。

/gui <action> → mss 截图 → P0 视觉模型分析 → PyAutoGUI 操作桌面。

WHY mss 而非 PIL ImageGrab：mss 跨平台，速度快 3-5×。
动作：screenshot / click / type / scroll / move / analyze
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io

import mss
import pyautogui
import structlog
from PIL import Image

from orbit.tools.models import ToolPermission, ToolSchema

logger = structlog.get_logger("orbit.tools.gui")

GUI_SCHEMA = ToolSchema(
    name="gui_agent",
    version="1.0.0",
    description="GUI Agent——截图+分析+操作桌面（点击/输入/滚动）",
    parameters={
        "action": {"type": "string", "description": "screenshot | click | type | scroll | move | analyze"},
        "x": {"type": "integer", "description": "X 坐标（click/move 时必填）"},
        "y": {"type": "integer", "description": "Y 坐标（click/move 时必填）"},
        "text": {"type": "string", "description": "输入文本（type 时必填）"},
        "amount": {"type": "integer", "description": "滚动量（scroll 时必填，正=上，负=下）"},
        "question": {"type": "string", "description": "分析问题（analyze 时必填）"},
    },
    permissions=[ToolPermission.EXECUTE],
    allowed_agents=["qa", "developer"],
    timeout_seconds=60,
    is_async=True,
)

# P2-2 fix: 顶层导入 mss，不再在函数内重复导入


def _capture_screen() -> Image.Image:
    """P2-2 + P2-6: 统一截图函数——mss grab → PIL Image。"""
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            img = sct.grab(monitor)
            return Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
    except Exception as e:
        logger.error("screenshot_failed", error=str(e))
        raise RuntimeError(f"截图失败（可能无显示器环境）: {e}")


async def gui_agent(
    action: str,
    x: int = 0,
    y: int = 0,
    text: str = "",
    amount: int = 0,
    question: str = "",
) -> dict:
    """GUI Agent Tool handler。"""
    pyautogui.FAILSAFE = True

    try:
        if action == "screenshot":
            pil_img = _capture_screen()
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            # P2-3 fix: 返回完整 base64（不截断）
            return {"action": "screenshot", "width": pil_img.width, "height": pil_img.height, "image_base64": b64}

        elif action == "click":
            pyautogui.click(x, y)
            logger.info("gui_click", x=x, y=y)
            return {"action": "click", "x": x, "y": y}

        elif action == "type":
            # P1-2 fix: 中文用剪贴板粘贴——pyautogui.typewrite 不支持 Unicode
            if any(ord(c) > 127 for c in text):
                import pyperclip
                pyperclip.copy(text)
                pyautogui.hotkey('ctrl', 'v')
            else:
                pyautogui.typewrite(text, interval=0.05)
            logger.info("gui_type", text_len=len(text))
            return {"action": "type", "text_len": len(text)}

        elif action == "scroll":
            pyautogui.scroll(amount)
            logger.info("gui_scroll", amount=amount)
            return {"action": "scroll", "amount": amount}

        elif action == "move":
            pyautogui.moveTo(x, y, duration=0.3)
            logger.info("gui_move", x=x, y=y)
            return {"action": "move", "x": x, "y": y}

        elif action == "analyze":
            pil_img = _capture_screen()
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=80)
            b64 = base64.b64encode(buf.getvalue()).decode()

            from orbit.gateway.client import LLMClient
            from orbit.gateway.schemas import LLMRequest

            # P2-1: hashlib 替代 hash()——确定性 task_id
            task_id = f"gui_analyze_{hashlib.md5(question.encode()).hexdigest()[:8]}"

            # P1-3 fix: async with 上下文管理器——释放 httpx 连接池
            async with LLMClient() as client:
                req = LLMRequest(
                    prompt=question or "描述这个屏幕上的内容",
                    content=[{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}],
                    tier=2,
                    max_tokens=2048,
                )
                resp = await client.generate(req, task_id=task_id)
                return {"action": "analyze", "analysis": resp.content, "model": resp.model}

        else:
            raise ValueError(f"不支持的操作: {action}，支持: screenshot/click/type/scroll/move/analyze")

    except Exception as e:
        # P2-6 fix: GUI 操作异常统一捕获
        logger.error("gui_action_failed", action=action, error=str(e))
        return {"action": action, "error": str(e)}


def _register():
    from orbit.tools.registry import get_registry
    get_registry().register(GUI_SCHEMA, gui_agent)

_register()
