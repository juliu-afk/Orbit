"""V15.1 多模态 P3：GUI Agent Tool。

/gui <action> → mss 截图 → P0 视觉模型分析 → PyAutoGUI 操作桌面。

WHY mss 而非 PIL ImageGrab：mss 跨平台，速度快 3-5×。
动作：screenshot / click / type / scroll / move / analyze
"""

from __future__ import annotations

import asyncio
import io

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


async def gui_agent(
    action: str,
    x: int = 0,
    y: int = 0,
    text: str = "",
    amount: int = 0,
    question: str = "",
) -> dict:
    """GUI Agent Tool handler。

    screenshot: 截图，返回 base64 PNG
    click: 点击指定坐标
    type: 在当前位置输入文本
    scroll: 滚轮滚动
    move: 移动鼠标
    analyze: 截图→P0 视觉模型分析→返回结果
    """
    import mss
    import pyautogui

    # 安全：PyAutoGUI fail-safe——鼠标移到左上角立即中止
    pyautogui.FAILSAFE = True

    if action == "screenshot":
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # 主显示器
            img = sct.grab(monitor)
            pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            import base64
            b64 = base64.b64encode(buf.getvalue()).decode()
            return {"action": "screenshot", "width": img.width, "height": img.height, "image_base64": b64[:200] + "..."}

    elif action == "click":
        pyautogui.click(x, y)
        logger.info("gui_click", x=x, y=y)
        return {"action": "click", "x": x, "y": y}

    elif action == "type":
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
        # 截图 → P0 Gateway 多模态分析
        import base64
        import mss as mss_lib
        with mss_lib.mss() as sct:
            monitor = sct.monitors[1]
            img = sct.grab(monitor)
            pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=80)
            b64 = base64.b64encode(buf.getvalue()).decode()

        from orbit.gateway.client import LLMClient
        from orbit.gateway.schemas import LLMRequest

        client = LLMClient()
        req = LLMRequest(
            prompt=question or "描述这个屏幕上的内容",
            content=[{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}],
            tier=2,  # 分析→标准推理
            max_tokens=2048,
        )
        resp = await client.generate(req, task_id=f"gui_analyze_{hash(question) & 0xFFFF:04x}")
        return {"action": "analyze", "analysis": resp.content, "model": resp.model}

    else:
        raise ValueError(f"不支持的操作: {action}，支持: screenshot/click/type/scroll/move/analyze")


def _register():
    from orbit.tools.registry import get_registry
    get_registry().register(GUI_SCHEMA, gui_agent)

_register()
