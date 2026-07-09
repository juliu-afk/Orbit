"""V15.1 多模态 P1：文档 OCR Tool。

/ocr <file> → DeepSeek-OCR 2 API → Markdown 结构化文本。

WHY DeepSeek-OCR 2：100+ 语言、$0.15/M 均一价、输出 Markdown/LaTeX/JSON。
WHY 不本地跑 OCR：Tesseract/paddleocr 中文准确率远低于 API。
"""

from __future__ import annotations

import base64
from pathlib import Path

import httpx
import structlog

from orbit.core.config import settings
from orbit.tools.models import ToolPermission, ToolSchema

logger = structlog.get_logger("orbit.tools.ocr")

# ── Tool Schema ──

OCR_SCHEMA = ToolSchema(
    name="ocr_document",
    version="1.0.0",
    description="OCR 图片/PDF——提取文字和表格，输出 Markdown",
    parameters={
        "file_path": {"type": "string", "description": "本地图片（jpg/png）或 PDF 路径"},
        "language": {"type": "string", "description": "主要语言（可选，默认 auto=自动检测）"},
    },
    permissions=[ToolPermission.READ],
    allowed_agents=["qa", "developer", "clarifier", "architect"],
    timeout_seconds=60,
    is_async=True,
)

# DeepSeek-OCR 2 API 端点
OCR_API_URL = "https://api.deepseek.com/v1/chat/completions"
OCR_MODEL = "deepseek-ocr-2"

# 支持的文件类型
SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".pdf"}


# ── OCR Handler ──


async def ocr_document(
    file_path: str,
    language: str = "auto",
) -> dict:
    """OCR 文档——发送到 DeepSeek-OCR 2，返回结构化 Markdown。

    Returns:
        {"text": str, "pages": int, "tokens": int, "cost_usd": float}
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError(f"不支持的文件类型: {ext}，支持: {', '.join(SUPPORTED_EXTS)}")

    # 读取 + base64 编码
    with open(file_path, "rb") as f:
        data = base64.b64encode(f.read()).decode()

    mime = _mime_type(ext)
    image_url = f"data:{mime};base64,{data}"

    # 构造 OCR 请求
    prompt = "请提取此文档中的所有文字和表格，输出 Markdown 格式。保留表格结构。"
    if language != "auto":
        prompt = f"主要语言：{language}。{prompt}"

    body = {
        "model": OCR_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": prompt},
            ],
        }],
        "max_tokens": 4096,
    }

    api_key = getattr(settings, "DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置——DeepSeek-OCR 2 需要独立 API Key")

    logger.info("ocr_start", file=file_path[:80], ext=ext)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            OCR_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )

    if resp.status_code != 200:
        err = _extract_error(resp)
        logger.error("ocr_failed", status=resp.status_code, error=err)
        raise RuntimeError(f"OCR 失败 ({resp.status_code}): {err}")

    data = resp.json()
    usage_data = data.get("usage", {})
    content = data["choices"][0]["message"]["content"]

    cost = (usage_data.get("prompt_tokens", 0) + usage_data.get("completion_tokens", 0)) * 0.15 / 1_000_000

    logger.info("ocr_done", tokens=usage_data.get("total_tokens", 0), cost=cost)

    return {
        "text": content,
        "pages": _estimate_pages(data),
        "tokens": usage_data.get("total_tokens", 0),
        "cost_usd": round(cost, 6),
    }


# ── 辅助函数 ──


def _mime_type(ext: str) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".pdf": "application/pdf",
    }.get(ext, "application/octet-stream")


def _extract_error(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("error", {}).get("message", resp.text[:200]))
    except Exception:
        return resp.text[:200]


def _estimate_pages(data: dict) -> int:
    """从 API 响应估算页数（原生不支持时返回 1）"""
    return data.get("pages", 1)


# ── 暴露给 ToolRegistry 的 handler ──
ocr_tool_handler = ocr_document
