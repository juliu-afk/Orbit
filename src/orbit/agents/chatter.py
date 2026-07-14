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
    r"\.(?:py|tsx?|jsx?|vue|html?|css|scss|less|md|json|ya?ml|toml|cfg|ini|"
    r"txt|log|sql|sh|bash|ps1|rs|go|java|c|cpp|h|hpp|env\.[a-z]+|"
    r"git[a-z]*|docker[a-z]*)$",
    _re.IGNORECASE,
)

# 多媒体文件扩展名
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".svg"}
_DOC_EXTS = {".pdf", ".docx", ".xlsx", ".xls", ".pptx", ".csv"}
_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".webm", ".mkv", ".flv", ".wmv"}

# 视频 URL 模式——常见视频平台 + 直链视频文件
# P2-1 (PR#297): 覆盖主流平台 + 直链 .mp4/.mov/.webm/.mkv
_VIDEO_URL_RE = _re.compile(
    r"https?://(?:www\.)?(?:"
    r"youtube\.com/watch\?v=|youtu\.be/|"  # YouTube
    r"bilibili\.com/video/|"  # B站
    r"vimeo\.com/|"  # Vimeo
    r"dailymotion\.com/video/|"  # Dailymotion
    r"twitch\.tv/videos/|"  # Twitch
    r"tiktok\.com/@[\w.\-]+/video/|"  # TikTok
    r"(?:x\.com|twitter\.com)/\w+/status/"  # X/Twitter 视频帖
    r")[\w\-]+",
    _re.IGNORECASE,
)

# 直链视频文件 URL（.mp4/.mov/.webm/.mkv 等）
_VIDEO_FILE_URL_RE = _re.compile(
    r"https?://\S+\.(?:mp4|mov|webm|mkv|flv|avi|wmv)(?:\?\S*)?(?:#\S*)?",
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
    cleaned = _re.sub(r"[#:]\d+(?:-\d+)?$", "", raw)
    cleaned = _re.sub(r"#L\d+(?:-L?\d+)?$", "", cleaned)
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    # URL / 纯数字 不算路径
    if cleaned.startswith(("http://", "https://")):
        return None
    if cleaned.isdigit():
        return None
    return cleaned


def _looks_like_code_file(s: str) -> bool:
    """判断字符串是否像代码文件路径——有分隔符 + 已知扩展名。"""
    return bool(_CODE_EXT_RE.search(s)) and ("/" in s or "\\" in s)


def _looks_like_directory(s: str) -> bool:
    """判断字符串是否像目录路径——有分隔符，且不像代码文件。"""
    has_sep = "/" in s or "\\" in s
    if not has_sep:
        return False
    # 有代码扩展名 → 是文件路径，不是目录
    if _CODE_EXT_RE.search(s):
        return False
    # 纯数字/URL 不算
    if s.isdigit() or s.startswith(("http://", "https://")):
        return False
    return True


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
    for m in _re.finditer(r"`([^`]+)`", text):
        raw = m.group(1).strip()
        clean = _clean_path(raw)
        if clean and clean not in seen:
            # 反引号内：有代码扩展名 或 有路径分隔符+扩展名
            if _CODE_EXT_RE.search(clean):
                found.append((raw, clean))
                seen.add(clean)

    # 层2: 裸路径——仅在无反引号匹配时启用，降低误匹配
    if not found:
        bare_re = r"(?:^|[\s(])" r"((?:\w+[/\\])+[\w./\\-]+\.\w{1,10})" r"(?:[\s,;:!?)]|$)"
        for m in _re.finditer(bare_re, text):
            raw = m.group(1).strip()
            clean = _clean_path(raw)
            if clean and clean not in seen and _looks_like_code_file(clean):
                found.append((raw, clean))
                seen.add(clean)

    return found


def _extract_directory_refs(text: str) -> list[str]:
    """从用户消息中提取目录路径引用。

    检测三层:
    1. 反引号包裹——如 `D:\\Code-Insight-Financial`
    2. 引号包裹——如 "D:\\Code-Insight-Financial" 或 'D:\\Code-Insight-Financial'
    3. 裸路径——如 D:\\Project\\src（仅在前两层无匹配时启用）

    WHY: 用户引用项目目录时，应自动探索目录结构 + 读取关键文件。
    大部分用户习惯用双引号而非反引号括路径。
    """
    found: list[str] = []
    seen: set[str] = set()

    # 层1: 反引号包裹
    for m in _re.finditer(r"`([^`]+)`", text):
        raw = m.group(1).strip()
        clean = _clean_path(raw)
        if clean and clean not in seen and _looks_like_directory(clean):
            found.append(clean)
            seen.add(clean)

    # 层1.5: 双引号/单引号包裹——用户习惯用 "D:\..." 而非 `D:\...`
    if not found:
        for m in _re.finditer(r'"([^"]+)"', text):
            raw = m.group(1).strip()
            clean = _clean_path(raw)
            if clean and clean not in seen and _looks_like_directory(clean):
                found.append(clean)
                seen.add(clean)
        for m in _re.finditer(r"'([^']+)'", text):
            raw = m.group(1).strip()
            clean = _clean_path(raw)
            if clean and clean not in seen and _looks_like_directory(clean):
                found.append(clean)
                seen.add(clean)

    # 层2: 裸路径——Windows 盘符或 Unix 绝对/相对路径
    if not found:
        # 匹配 Windows 绝对路径 D:\... 或 UNC \\...
        # 或 Unix 绝对路径 /home/... 或相对路径 src/.../...
        bare_dir_re = (
            r"(?:^|[\s(])"
            r"((?:[A-Za-z]:[/\\]|/|\.{1,2}[/\\])"
            r"(?:[\w./\\-]+[/\\])+[\w./\\-]*)"
            r"(?:[\s,;:!?)]|$)"
        )
        for m in _re.finditer(bare_dir_re, text):
            raw = m.group(1).strip()
            clean = _clean_path(raw)
            if clean and clean not in seen and _looks_like_directory(clean):
                # 排除像代码文件的（已由 _extract_file_paths 处理）
                found.append(clean)
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
    for m in _re.finditer(r"`([^`]+)`", text):
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
        r"(?:^|[\s(])((?:\w+[/\\])*[\w./\\-]+\.\w{2,5})(?:[\s,;:!?)]|$)",
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


# _build_history_block + 常量已提取到 orbit.agents.context_util——全 Agent 统一使用
from orbit.agents.context_util import _build_history_block

CHATTER_SYSTEM_PROMPT = """你是 Orbit 的通用对话助手（ChatterAgent）。你是用户接触 Orbit 的第一个 Agent。

## 你的定位
你是友好、博学、乐于助人的对话伙伴。你不是"需求工程师"或"技术架构师"——
你是一个 AI Agent，你是 Orbit 多智能体系统的一员。你的底层 LLM 由 LiteLLM 网关统一调度。

## 核心能力
- 回答任何问题：技术、生活、学术、闲聊——没有话题限制
- 讨论编程/软件开发（但不过度工程化——保持自然对话）
- 诚实：不知道就说不知道，不编造
- **读取文件**：用户可以用反引号引用文件路径（如 `src/main.py`），系统会自动读取文件内容并提供给你
- **探索目录**：用户引用目录路径（如 `D:\\Code-Insight-Financial`）时，系统会自动列出目录结构并读取关键文件（CLAUDE.md/README 等），以 "📁 目录探索结果" 形式提供给你——你可以基于这些内容分析项目进度、未完成项等
- **OCR 图片**：用户引用图片文件（如 `photo.jpg`）时，系统会自动 OCR 提取文字内容（以 "🔍 OCR 识别结果" 开头）
- **解析文档**：用户引用 PDF/Word/Excel 等文档时，系统会自动解析为 Markdown（以 "📄 文档解析结果" 开头）
- **视频分析**：检测到视频 URL/文件时，提示用户使用 `/watch` 命令（以 "🎬 检测到视频引用" 开头）。如果消息中附带了以上任何内容，直接基于这些内容回答用户的问题

## 意图识别规则
当用户表达以下意图时，标记 intent="programming"：
1. 明确的编程任务请求（"写一个..."、"帮我实现..."、"修复这个 bug..."）
2. 软件开发项目规划（"我想做一个..."、"设计一个系统..."）
3. 代码审查/调试请求

普通聊天、问答、讨论（不含具体编程任务）标记 intent="chat"。

## Skill 匹配规则
当用户表达的意图恰好对应某个已知技能时，标记 intent="skill"：
- 代码审查/检查/CR → skill_name="compose:review"，confidence=0.85
- 技术方案/架构设计 → skill_name="compose:plan"，confidence=0.85
- 写测试/单元测试 → skill_name="compose:tdd"，confidence=0.85
- 调试/修 bug/fix → skill_name="compose:debug"，confidence=0.80
- 验证/自查/check → skill_name="compose:verify"，confidence=0.75

当用户需求需要**多步完成**时，标记 intent="chain"：
- "设计并实现" → skills=["compose:plan", "compose:implement"]
- "完整开发" → skills=["compose:plan", "compose:implement", "compose:review"]
- "从设计到验证" → skills=["compose:plan", "compose:implement", "compose:verify"]

confidence 取值：如果意图非常明确（如"审查代码"）→ 0.8-0.95；模糊但有匹配（如"帮我检查一下代码质量"）→ 0.4-0.7；不匹配 → 返回 intent="chat" 或 "programming"。

## 输出格式
必须返回严格 JSON：
{"reply": "你的回复内容", "intent": "chat|skill|chain|programming", "skill_name": "...", "confidence": 0.0, "skills": ["...","..."], "reason": "简短说明判定理由"}
当 intent="programming" 时，reply 中简要确认用户需求，并告知将转交 Clarifier 做需求澄清。
当 intent="skill" 时，skill_name 必填，confidence 必填。
当 intent="chain" 时，skills 列表必填。

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
                result["ocr_results"].append(
                    {
                        "path": path,
                        "text": ocr_result.get("text", ""),
                        "cost_usd": ocr_result.get("cost_usd", 0),
                    }
                )
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
                result["parse_results"].append(
                    {
                        "path": path,
                        "text": parse_result.get("text", ""),
                        "file_type": parse_result.get("file_type", ""),
                    }
                )
                logger.info("chatter_parse_done", path=path)
            except FileNotFoundError:
                logger.info("chatter_media_not_found", path=path, type="doc")
            except Exception as e:
                logger.warning("chatter_parse_error", path=path, error=str(e))

        # 视频 → 提示使用 /watch（不自动处理——下载+抽帧太重）
        for ref in media["videos"]:
            result["video_hints"].append(ref)

        return result

    async def _explore_directory(self, dir_path: str) -> dict[str, Any] | None:
        """探索目录——列出结构 + 读取关键文件。

        WHY: 用户引用项目目录时（如 `D:\\Code-Insight-Financial`），
        自动列目录 + 读 CLAUDE.md/README 等关键文件，注入 LLM 上下文。
        避免 LLM 回复"我没权限访问本地文件"。

        Returns: {"path": str, "structure": str, "key_files": [{path, content}]} 或 None
        """
        import os as _os

        resolved = _os.path.abspath(_os.path.expanduser(dir_path))
        if not _os.path.isdir(resolved):
            logger.info("chatter_dir_not_found", path=resolved)
            return None

        # 列出顶层目录结构（限制 50 项，防大目录撑爆 prompt）
        try:
            entries = sorted(_os.listdir(resolved))
        except PermissionError:
            logger.info("chatter_dir_permission_denied", path=resolved)
            return None

        n_total = len(entries)
        entries = entries[:50]
        dirs = [e for e in entries if _os.path.isdir(_os.path.join(resolved, e))]
        files_list = [e for e in entries if _os.path.isfile(_os.path.join(resolved, e))]
        trunc = f"（仅显示前 50 项，共 {n_total} 项）" if n_total > 50 else ""

        lines = [f"📁 目录 `{resolved}`（{n_total} 项）{trunc}", ""]
        if dirs:
            lines.append("**子目录：**")
            for d in dirs:
                lines.append(f"  - 📁 {d}/")
            lines.append("")
        if files_list:
            lines.append("**文件：**")
            for f in files_list:
                lines.append(f"  - 📄 {f}")
            lines.append("")

        structure = "\n".join(lines)

        # 读取关键文件——CLAUDE.md / README.md / pyproject.toml 等
        # WHY: 直接用 Path.read_text() 而非 _fs_read_file，
        # 因为用户引用的目录可能在 Orbit 工作区外（如 D:\Code-Insight-Financial），
        # filesystem 工具受 workspace 边界保护，会拒绝跨区读取。
        # 目录探索是只读操作，不需要沙箱限制。
        from pathlib import Path as _Path

        KEY_FILES = [
            "CLAUDE.md",
            "README.md",
            "AGENTS.md",
            "pyproject.toml",
            "package.json",
            "Makefile",
            "Cargo.toml",
            "docker-compose.yml",
            "docker-compose.yaml",
        ]
        key_file_results: list[dict[str, str]] = []
        for kf in KEY_FILES:
            kf_path = _os.path.join(resolved, kf)
            if not _os.path.isfile(kf_path):
                continue
            try:
                content = _Path(kf_path).read_text(encoding="utf-8", errors="replace")
                if content:
                    # 截断超大文件到 4000 字符——防撑爆 prompt
                    if len(content) > 4000:
                        content = content[:4000] + f"\n\n...（已截断，原文件 {len(content)} 字符）"
                    key_file_results.append({"path": kf_path, "content": content})
                    logger.info("chatter_dir_keyfile_read", path=kf_path, chars=len(content))
            except Exception as e:
                logger.warning("chatter_dir_keyfile_error", path=kf_path, error=str(e))

        # 如果有 docs/ 目录，列出内容
        docs_path = _os.path.join(resolved, "docs")
        docs_listing = ""
        if _os.path.isdir(docs_path):
            try:
                docs_entries = sorted(_os.listdir(docs_path))[:30]
                docs_listing = "\n".join(f"  - {e}" for e in docs_entries)
            except PermissionError:
                pass

        result: dict[str, Any] = {
            "path": resolved,
            "structure": structure,
            "key_files": key_file_results,
        }
        if docs_listing:
            result["docs_listing"] = f"📁 `{resolved}/docs/` 内容：\n{docs_listing}"

        logger.info(
            "chatter_dir_explored",
            path=resolved,
            entries=n_total,
            key_files=len(key_file_results),
        )
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

        # ── 对话历史注入（token 预算驱动） ──
        # WHY: ChatterAgent 无状态——每次 execute() 只看到当前消息。
        # 必须把 SessionRegistry 积累的历史注入 prompt，否则 LLM 每轮像失忆。
        # 业界标准：按 token 预算而非条数截断，超限时摘要而非丢弃。
        # chat.py:_handle_chat 已把 history 放进 context，此处注入。
        history = input_data.context.get("history", []) or []
        history_block = ""
        if history:
            history_block = _build_history_block(history)
            if history_block:
                logger.debug(
                    "chatter_history_injected",
                    messages=min(len(history), 200),
                )

        # ── 文件路径检测 + 自动读取（代码+多媒体+目录） ──
        # WHY: 用户引用文件/目录路径时自动读取内容注入 LLM 上下文。
        # 代码→read_file, 图片→OCR, 文档→file_parser, 视频→提示/watch,
        # 目录→listdir+关键文件读取
        enriched_prompt = history_block + input_data.task
        files = await self._read_referenced_files(input_data.task)
        media = await self._process_media_files(input_data.task)
        # 目录探索——用户引用项目目录时自动列结构+读关键文件
        dir_refs = _extract_directory_refs(input_data.task)
        dir_explorations = []
        for dr in dir_refs:
            explored = await self._explore_directory(dr)
            if explored:
                dir_explorations.append(explored)

        has_files = bool(files)
        has_media = bool(media["ocr_results"] or media["parse_results"] or media["video_hints"])
        has_dirs = bool(dir_explorations)

        if has_files or has_media or has_dirs:
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

            if dir_explorations:
                parts.append("📁 目录探索结果：")
                parts.append("")
                for de in dir_explorations:
                    parts.append(de["structure"])
                    if de.get("docs_listing"):
                        parts.append(de["docs_listing"])
                        parts.append("")
                    for kf in de.get("key_files", []):
                        parts.append(f"### 📄 `{kf['path']}`")
                        parts.append(kf["content"])
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
                dirs=len(dir_explorations),
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
