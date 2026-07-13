"""通用对话 Agent（ChatterAgent）——用户首触点。

WHY ChatterAgent: 用户不应每次打开 Orbit 都被 Clarifier 审问需求。
ChatterAgent 无约束、啥都能聊，仅在检测到编程意图时路由到 Clarifier。
其他 Agent (architect/developer/reviewer) 保持原有触发条件不变。

意图路由机制：
- chatter 返回 `output.result` 中包含 `_intent: "chat"|"programming"`
- task_runner._agent_cycle 检查 intent → "programming" 时继续进入 PARSING
- "chat" 时结束任务（DONE）
"""

from __future__ import annotations

import re as _re
from pathlib import Path
from typing import Any

import structlog

from orbit.agents.base import AgentInput, AgentOutput, AgentRole, BaseAgent

logger = structlog.get_logger("orbit.agents.chatter")

# ── 文件路径检测 ──────────────────────────────────────────
# WHY: 用户在聊天中引用文件路径时，自动读取并注入 LLM 上下文。
# 用户不需要手动复制粘贴文件内容——引用路径即可。

# 常见代码文件扩展名
_CODE_EXT_RE = _re.compile(
    r'\.(?:py|tsx?|jsx?|vue|html?|css|scss|less|md|json|ya?ml|toml|cfg|ini|'
    r'txt|log|sql|sh|bash|ps1|rs|go|java|c|cpp|h|hpp|env\.[a-z]+|'
    r'git[a-z]*|docker[a-z]*)$',
    _re.IGNORECASE,
)

# 多媒体文件扩展名
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".svg"}
_DOC_EXTS = {".pdf", ".docx", ".xlsx", ".xls", ".pptx", ".csv"}
_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".webm", ".mkv", ".flv", ".wmv"}

# 视频 URL 模式——常见视频平台 + 直链视频文件
# P2-1 (PR#297): 覆盖主流平台 + 直链 .mp4/.mov/.webm/.mkv
_VIDEO_URL_RE = _re.compile(
    r'https?://(?:www\.)?(?:'
    r'youtube\.com/watch\?v=|youtu\.be/|'          # YouTube
    r'bilibili\.com/video/|'                        # B站
    r'vimeo\.com/|'                                 # Vimeo
    r'dailymotion\.com/video/|'                     # Dailymotion
    r'twitch\.tv/videos/|'                          # Twitch
    r'tiktok\.com/@[\w.\-]+/video/|'                # TikTok
    r'(?:x\.com|twitter\.com)/\w+/status/'          # X/Twitter 视频帖
    r')[\w\-]+',
    _re.IGNORECASE,
)

# 直链视频文件 URL（.mp4/.mov/.webm/.mkv 等）
_VIDEO_FILE_URL_RE = _re.compile(
    r'https?://\S+\.(?:mp4|mov|webm|mkv|flv|avi|wmv)(?:\?\S*)?(?:#\S*)?',
    _re.IGNORECASE,
)


def _is_image_file(s: str) -> bool:
    """判断是否图片文件。"""
    return Path(s).suffix.lower() in _IMAGE_EXTS


def _is_doc_file(s: str) -> bool:
    """判断是否文档文件（PDF/Office）。"""
    return Path(s).suffix.lower() in _DOC_EXTS


def _is_video_file(s: str) -> bool:
    """判断是否视频文件。"""
    return Path(s).suffix.lower() in _VIDEO_EXTS


def _is_media_file(s: str) -> bool:
    """判断是否多媒体文件（图片/文档/视频）。"""
    return _is_image_file(s) or _is_doc_file(s) or _is_video_file(s)


def _clean_path(raw: str) -> str | None:
    """清理路径字符串——去行号后缀、空白、URL 过滤。"""
    # 去行号后缀: :42, :42-51, #L42, #L42-L51
    cleaned = _re.sub(r'[#:]\d+(?:-\d+)?$', '', raw)
    cleaned = _re.sub(r'#L\d+(?:-L?\d+)?$', '', cleaned)
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    # URL / 纯数字 不算路径
    if cleaned.startswith(('http://', 'https://')):
        return None
    if cleaned.isdigit():
        return None
    return cleaned


def _looks_like_code_file(s: str) -> bool:
    """判断字符串是否像代码文件路径——有分隔符 + 已知扩展名。"""
    return bool(_CODE_EXT_RE.search(s)) and ('/' in s or '\\' in s)


def _extract_file_paths(text: str) -> list[tuple[str, str]]:
    """从用户消息中提取文件路径引用。返回 [(原始文本, 清理后路径), ...]。

    检测两层:
    1. 反引号包裹——显式路径引用（如 `src/main.py:42`）
    2. 裸路径——自然语言中带目录分隔符的代码文件路径（仅在无反引号匹配时启用）
    """
    found: list[tuple[str, str]] = []
    seen: set[str] = set()

    # 层1: 反引号包裹——用户明确想引用文件
    # WHY: 反引号内放宽要求——有代码扩展名即可，不强制路径分隔符
    # 用户可能写 `main.py` 而非 `src/main.py`
    for m in _re.finditer(r'`([^`]+)`', text):
        raw = m.group(1).strip()
        clean = _clean_path(raw)
        if clean and clean not in seen:
            # 反引号内：有代码扩展名 或 有路径分隔符+扩展名
            if _CODE_EXT_RE.search(clean):
                found.append((raw, clean))
                seen.add(clean)

    # 层2: 裸路径——仅在无反引号匹配时启用，降低误匹配
    if not found:
        bare_re = (
            r'(?:^|[\s(])'
            r'((?:\w+[/\\])+[\w./\\-]+\.\w{1,10})'
            r'(?:[\s,;:!?)]|$)'
        )
        for m in _re.finditer(bare_re, text):
            raw = m.group(1).strip()
            clean = _clean_path(raw)
            if clean and clean not in seen and _looks_like_code_file(clean):
                found.append((raw, clean))
                seen.add(clean)

    return found


def _extract_media_refs(text: str) -> dict[str, list[str]]:
    """从用户消息中提取多媒体引用。返回 {"images": [...], "docs": [...], "videos": [...]}。

    检测:
    - 反引号包裹的媒体文件路径 `photo.jpg`
    - 裸媒体文件路径
    - 视频 URL（YouTube/B站等）
    """
    result: dict[str, list[str]] = {"images": [], "docs": [], "videos": []}
    seen: set[str] = set()

    # 层1: 反引号包裹
    for m in _re.finditer(r'`([^`]+)`', text):
        raw = m.group(1).strip()
        clean = _clean_path(raw)
        if not clean or clean in seen:
            continue
        if _is_image_file(clean):
            result["images"].append(clean)
            seen.add(clean)
        elif _is_doc_file(clean):
            result["docs"].append(clean)
            seen.add(clean)
        elif _is_video_file(clean):
            result["videos"].append(clean)
            seen.add(clean)

    # 层2: 裸路径
    for m in _re.finditer(
        r'(?:^|[\s(])((?:\w+[/\\])*[\w./\\-]+\.\w{2,5})(?:[\s,;:!?)]|$)',
        text,
    ):
        raw = m.group(1).strip()
        clean = _clean_path(raw)
        if not clean or clean in seen:
            continue
        if _is_image_file(clean):
            result["images"].append(clean)
            seen.add(clean)
        elif _is_doc_file(clean):
            result["docs"].append(clean)
            seen.add(clean)
        elif _is_video_file(clean):
            result["videos"].append(clean)
            seen.add(clean)

    # 层3: 视频平台 URL
    for m in _VIDEO_URL_RE.finditer(text):
        url = m.group(0)
        if url not in seen:
            result["videos"].append(url)
            seen.add(url)

    # 层4: 直链视频文件 URL (.mp4/.mov等)
    for m in _VIDEO_FILE_URL_RE.finditer(text):
        url = m.group(0)
        if url not in seen:
            result["videos"].append(url)
            seen.add(url)

    return result


CHATTER_SYSTEM_PROMPT = """你是 Orbit 的通用对话助手（ChatterAgent）。你是用户接触 Orbit 的第一个 Agent。

## 你的定位
你是友好、博学、乐于助人的对话伙伴。你不是"需求工程师"或"技术架构师"——
你是一个 AI Agent，你是 Orbit 多智能体系统的一员。你的底层 LLM 由 LiteLLM 网关统一调度。

## 核心能力
- 回答任何问题：技术、生活、学术、闲聊——没有话题限制
- 讨论编程/软件开发（但不过度工程化——保持自然对话）
- 诚实：不知道就说不知道，不编造
- **读取文件**：用户可以用反引号引用文件路径（如 `src/main.py`），系统会自动读取文件内容并提供给你
- **OCR 图片**：用户引用图片文件（如 `photo.jpg`）时，系统会自动 OCR 提取文字内容（以 "🔍 OCR 识别结果" 开头）
- **解析文档**：用户引用 PDF/Word/Excel 等文档时，系统会自动解析为 Markdown（以 "📄 文档解析结果" 开头）
- **视频分析**：检测到视频 URL/文件时，提示用户使用 `/watch` 命令（以 "🎬 检测到视频引用" 开头）。如果消息中附带了以上任何内容，直接基于这些内容回答用户的问题

## 意图识别规则
当用户表达以下意图时，标记 intent="programming"：
1. 明确的编程任务请求（"写一个..."、"帮我实现..."、"修复这个 bug..."）
2. 软件开发项目规划（"我想做一个..."、"设计一个系统..."）
3. 代码审查/调试请求

普通聊天、问答、讨论（不含具体编程任务）标记 intent="chat"。

## 输出格式
必须返回严格 JSON：
{"reply": "你的回复内容", "intent": "chat", "reason": "简短说明判定理由"}
当 intent="programming" 时，reply 中简要确认用户需求，并告知将转交 Clarifier 做需求澄清。

## 风格
- 轻松、自然、友好
- 可以用表情符号
- 简短回答优于长篇大论（除非用户要求详细）
- 用户问"你是什么模型"时如实回答——你是 Orbit 系统的一部分，底层 LLM 由配置决定
- 当用户引用了文件而你看到了文件内容时，在回复中提及你已读取该文件
"""


class ChatterAgent(BaseAgent):
    """通用对话 Agent——无约束首触点。

    用法:
        agent = ChatterAgent(llm=llm_client)
        result = await agent.execute(AgentInput(task="今天天气怎么样？"))
    """

    role: AgentRole = AgentRole.CHATTER

    def __init__(self, llm: Any = None, graph: Any = None, sandbox: Any = None) -> None:
        super().__init__(llm=llm, graph=graph, sandbox=sandbox)

    async def _read_referenced_files(self, text: str) -> list[dict[str, str]]:
        """检测用户消息中的文件路径引用，自动读取并返回文件内容。

        WHY: 用户不应每次手动粘贴文件内容。引路径 = 自动读。
        返回 [{path, content}, ...]——空列表表示无文件引用或读取失败。
        """
        from orbit.tools.filesystem import read_file as _fs_read_file

        paths = _extract_file_paths(text)
        if not paths:
            return []

        results: list[dict[str, str]] = []
        for raw, clean in paths:
            try:
                content = await _fs_read_file(clean)
                # read_file 返回带行号的格式化文本；如果文件不存在，以 "文件不存在:" 开头
                if content and not content.startswith("文件不存在"):
                    results.append({"path": clean, "content": content})
                    logger.info("chatter_file_read", path=clean, chars=len(content))
                else:
                    logger.info("chatter_file_not_found", path=clean)
            except Exception as e:
                logger.warning("chatter_file_read_error", path=clean, error=str(e))

        return results

    async def _process_media_files(self, text: str) -> dict[str, Any]:
        """检测多媒体文件引用，自动 OCR/解析，返回结果 + 视频提示。

        WHY: 用户引用图片/文档时自动提取内容，视频则提示用 /watch。
        返回 {"ocr_results": [...], "parse_results": [...], "video_hints": [...]}
        """
        media = _extract_media_refs(text)
        result: dict[str, Any] = {
            "ocr_results": [],
            "parse_results": [],
            "video_hints": [],
        }

        # 图片 → OCR
        for path in media["images"]:
            try:
                from orbit.tools.ocr_tools import ocr_document as _ocr

                ocr_result = await _ocr(path)
                result["ocr_results"].append({
                    "path": path,
                    "text": ocr_result.get("text", ""),
                    "cost_usd": ocr_result.get("cost_usd", 0),
                })
                logger.info("chatter_ocr_done", path=path)
            except FileNotFoundError:
                logger.info("chatter_media_not_found", path=path, type="image")
            except Exception as e:
                logger.warning("chatter_ocr_error", path=path, error=str(e))

        # 文档 → file_parser
        for path in media["docs"]:
            try:
                from orbit.tools.file_parser import file_parser as _parse

                parse_result = await _parse(path)
                result["parse_results"].append({
                    "path": path,
                    "text": parse_result.get("text", ""),
                    "file_type": parse_result.get("file_type", ""),
                })
                logger.info("chatter_parse_done", path=path)
            except FileNotFoundError:
                logger.info("chatter_media_not_found", path=path, type="doc")
            except Exception as e:
                logger.warning("chatter_parse_error", path=path, error=str(e))

        # 视频 → 提示使用 /watch（不自动处理——下载+抽帧太重）
        for ref in media["videos"]:
            result["video_hints"].append(ref)

        return result

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """执行对话——生成回复 + 意图标记。"""
        if not self.llm:
            return AgentOutput(
                status="ok",
                result={
                    "reply": (
                        "你好！我是 Orbit 的对话助手。当前 LLM 未配置，"
                        "请检查环境变量或 CC_SWITCH 设置。"
                    ),
                    "_intent": "chat",
                    "reason": "llm_not_configured",
                },
            )

        import json as _json

        from orbit.gateway.schemas import LLMRequest

        # ── 文件路径检测 + 自动读取（代码+多媒体） ──
        # WHY: 用户引用文件路径时自动读取内容注入 LLM 上下文。
        # 代码→read_file, 图片→OCR, 文档→file_parser, 视频→提示/watch
        enriched_prompt = input_data.task
        files = await self._read_referenced_files(input_data.task)
        media = await self._process_media_files(input_data.task)

        has_files = bool(files)
        has_media = bool(
            media["ocr_results"] or media["parse_results"] or media["video_hints"]
        )

        if has_files or has_media:
            parts = [input_data.task, "", "---"]

            if files:
                parts.append("📂 引用的文件内容：")
                parts.append("")
                for f in files:
                    parts.append(f"### `{f['path']}`")
                    parts.append(f["content"])
                    parts.append("")

            if media["ocr_results"]:
                parts.append("🔍 OCR 识别结果：")
                parts.append("")
                for r in media["ocr_results"]:
                    parts.append(f"### `{r['path']}` (OCR, ${r['cost_usd']:.4f})")
                    parts.append(r["text"])
                    parts.append("")

            if media["parse_results"]:
                parts.append("📄 文档解析结果：")
                parts.append("")
                for r in media["parse_results"]:
                    parts.append(f"### `{r['path']}` ({r['file_type']})")
                    parts.append(r["text"])
                    parts.append("")

            if media["video_hints"]:
                parts.append("🎬 检测到视频引用：")
                for v in media["video_hints"]:
                    parts.append(f"- `{v}`")
                parts.append("")
                parts.append(
                    "视频分析需要下载+抽帧，请用户使用 **/watch** 命令："
                    "`/watch <url或路径> [问题]`"
                )
                parts.append("")

            parts.append("---")
            parts.append("请基于以上内容回答用户的问题。")
            enriched_prompt = "\n".join(parts)
            logger.info(
                "chatter_enriched_prompt",
                files=len(files),
                ocr=len(media["ocr_results"]),
                parsed=len(media["parse_results"]),
                videos=len(media["video_hints"]),
            )

        try:
            req = LLMRequest(
                prompt=enriched_prompt,
                system_prompt=CHATTER_SYSTEM_PROMPT,
                temperature=0.8,
                max_tokens=1024,
                # Inkeep 借鉴 #1: 注入 task_type 用于模型路由
                task_type=input_data.context.get("task_type"),
            )
            resp = await self.llm.generate(req, task_id=input_data.context.get("task_id", ""))
            content = resp.content or ""

            parsed = self._parse_output(content)
            return AgentOutput(
                status="ok",
                result={
                    "reply": parsed.get("reply", content[:500]),
                    "_intent": parsed.get("intent", "chat"),
                    "reason": parsed.get("reason", ""),
                },
            )
        except Exception as e:
            logger.warning("chatter_execution_failed", error=str(e))
            return AgentOutput(
                status="ok",
                result={
                    "reply": "抱歉，我暂时无法处理这个消息。请稍后再试。",
                    "_intent": "chat",
                    "reason": "chatter_execution_failed",
                },
            )

    @staticmethod
    def _parse_output(content: str) -> dict[str, Any]:
        """宽松解析 LLM 返回的 JSON——容错代码块包裹/尾字符/字段缺失。"""
        import json as _json
        import re as _re

        try:
            return _json.loads(content.strip())
        except (_json.JSONDecodeError, ValueError):
            pass

        match = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, _re.DOTALL)
        if match:
            try:
                return _json.loads(match.group(1))
            except (_json.JSONDecodeError, ValueError):
                pass

        brace = _re.search(r"\{.*\}", content, _re.DOTALL)
        if brace:
            try:
                return _json.loads(brace.group(0))
            except (_json.JSONDecodeError, ValueError):
                pass

        return {"reply": content.strip(), "intent": "chat", "reason": "parse_fallback"}
