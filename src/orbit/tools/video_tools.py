"""V15.1 多模态 P1：视频理解 Tool。

/watch <url> → yt-dlp 下载 → ffmpeg 抽帧 → 字幕提取 → LLMClient 分析。

帧预算策略（WHY 自适应：控制 token 消耗，短视频密集/长视频稀疏）：
  ≤30s   → 30 帧 @ 1.0fps
  30s-3m → 60 帧 @ 0.5fps
  3m-10m → 100 帧 @ 0.2fps
  >10m   → 100 帧 @ 0.1fps（封顶）

字幕优先策略（WHY 省钱：原生字幕免费，Whisper API 收费）：
  有原生字幕 → 直接使用（免费）
  无字幕     → 提示用户可选 ASR（P1 不做，留给 Agent 决策）
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import structlog

from orbit.tools.models import ToolInvocation, ToolPermission, ToolSchema

logger = structlog.get_logger("orbit.tools.video")

# ── 帧预算 ──


@dataclass
class FrameBudget:
    """自适应帧预算——随视频时长递减 fps，封顶 100 帧。"""
    max_frames: int
    fps: float
    width: int = 512

    @classmethod
    def auto(cls, duration_sec: float) -> "FrameBudget":
        if duration_sec <= 30:
            return cls(30, 1.0)
        if duration_sec <= 180:
            return cls(60, 0.5)
        if duration_sec <= 600:
            return cls(100, 0.2)
        return cls(100, 0.1)


# ── Tool Schema ──

WATCH_VIDEO_SCHEMA = ToolSchema(
    name="watch_video",
    version="1.0.0",
    description="下载并分析视频——yt-dlp 下载 → ffmpeg 抽帧 → 多模态模型理解内容。字幕优先（免费原生字幕），无字幕时提示可选 ASR。",
    parameters={
        "url": {"type": "string", "description": "视频 URL（YouTube/B站等 1800+ 平台）或本地 .mp4/.mov 路径"},
        "question": {"type": "string", "description": "要分析的问题（可选，默认=总结视频内容）"},
        "start": {"type": "string", "description": "起始时间（可选，如 '1:30' 或 '90'）"},
        "end": {"type": "string", "description": "结束时间（可选，如 '2:45' 或 '165'）"},
    },
    permissions=[ToolPermission.READ],
    allowed_agents=["qa", "developer", "clarifier"],
    timeout_seconds=180,  # 下载+抽帧可能慢
    is_async=True,
)


# ── 视频信息 ──


@dataclass
class VideoInfo:
    """视频分析中间产物。"""
    path: str
    duration_sec: float
    has_captions: bool
    captions_text: str | None
    frame_paths: list[str]


# ── 下载 ──


async def download_video(url: str, output_dir: str | None = None) -> str:
    """yt-dlp 下载视频到临时目录。

    WHY subprocess：yt-dlp 是 Python 包但没有可靠的 async API。
    用 --no-playlist 防止播放列表下载。
    """
    # P2-1: SSRF 防护——拒绝内网/localhost URL
    _validate_url(url)

    dest = output_dir or tempfile.mkdtemp(prefix="orbit_video_")
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--merge-output-format", "mp4",
        "--output", f"{dest}/%(title)s.%(ext)s",
        "--no-progress",
        url,
    ]
    logger.info("video_download_start", url=url[:80])
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace")[:500]
        logger.error("video_download_failed", url=url[:80], error=err)
        raise RuntimeError(f"视频下载失败：{err}")

    # 查找下载的文件
    for f in Path(dest).glob("*.mp4"):
        logger.info("video_download_ok", path=str(f))
        return str(f)
    for f in Path(dest).glob("*"):
        if f.suffix.lower() in (".mkv", ".webm", ".mov", ".avi"):
            return str(f)

    raise FileNotFoundError(f"下载完成但未找到视频文件: {dest}")


# ── 字幕提取 ──


async def extract_captions(url: str) -> str | None:
    """从在线视频提取原生字幕——yt-dlp 下载 VTT。

    WHY 字幕优先：原生字幕免费且准确，Whisper API 收费且可能不准。
    P1-2 fix: 参数改为 URL（yt-dlp 不接受本地文件路径）。
    P2-4 fix: 异常不静默——timeout 记录日志，其他异常记录详细信息。
    """
    work_dir = tempfile.mkdtemp(prefix="orbit_subs_")
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--write-subs", "--write-auto-subs",
        "--sub-lang", "zh-Hans,zh,en",
        "--sub-format", "vtt",
        "--output", f"{work_dir}/%(title)s",
        url,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError:
        logger.warning("captions_timeout", url=url[:80])
        return None
    except Exception as e:
        logger.warning("captions_extract_failed", url=url[:80], error=str(e))
        return None

    # 查找 .vtt 文件
    for vtt in Path(work_dir).glob("**/*.vtt"):
        try:
            text = vtt.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        lines = []
        for line in text.split("\n"):
            line = line.strip()
            if not line or "-->" in line or line.startswith(("WEBVTT", "Kind:", "Language:")):
                continue
            if line.isdigit():
                continue
            lines.append(line)
        result = " ".join(lines)
        if result.strip():
            logger.info("captions_extracted", url=url[:80], chars=len(result))
            return result

    return None


async def _extract_local_captions(video_path: str) -> str | None:
    """从本地文件提取嵌入字幕——ffmpeg。

    WHY ffmpeg：本地文件无 URL，yt-dlp 不可用。ffmpeg 可提取嵌入字幕轨。
    """
    work_dir = tempfile.mkdtemp(prefix="orbit_local_subs_")
    output = f"{work_dir}/subs.srt"
    cmd = ["ffmpeg", "-y", "-i", video_path, "-map", "0:s:0", output]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=30)
        if os.path.exists(output):
            text = Path(output).read_text(encoding="utf-8", errors="replace")
            logger.info("local_captions_extracted", path=video_path[:80], chars=len(text))
            return text
    except asyncio.TimeoutError:
        logger.warning("local_captions_timeout", path=video_path[:80])
    except Exception as e:
        logger.warning("local_captions_failed", path=video_path[:80], error=str(e))
    return None


# ── 帧抽取 ──


async def extract_frames(
    video_path: str,
    budget: FrameBudget | None = None,
    start_sec: float | None = None,
    end_sec: float | None = None,
    output_dir: str | None = None,
) -> list[str]:
    """ffmpeg 关键帧抽取。

    WHY ffmpeg 而非 opencv：ffmpeg scene-change detection 比固定 fps 更智能——画面变化快时多抽帧，静止时少抽。

    两种模式：
      有 start/end → 均匀采样（聚焦片段，帧密集）
      无 start/end → 场景变化检测（全片覆盖，智能抽帧）
    """
    if budget is None:
        budget = FrameBudget.auto(600)  # 默认 100 帧

    dest = output_dir or tempfile.mkdtemp(prefix="orbit_frames_")
    os.makedirs(dest, exist_ok=True)

    if start_sec is not None and end_sec is not None:
        # 均匀采样模式——聚焦片段
        duration = end_sec - start_sec
        vf = f"fps={budget.fps},scale={budget.width}:-2"
        seek_args = ["-ss", str(start_sec), "-t", str(duration)]
    else:
        # 场景变化检测模式——全片覆盖
        vf = f"select=gt(scene\\,0.3),scale={budget.width}:-2"
        seek_args = []

    cmd = [
        "ffmpeg", "-y",
        *seek_args,
        "-i", video_path,
        "-vf", vf,
        "-vsync", "vfr",
        "-q:v", "3",
        "-frames:v", str(budget.max_frames),
        f"{dest}/frame_%04d.jpg",
    ]

    logger.info("frame_extract_start", path=video_path, fps=budget.fps, max=budget.max_frames)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

    frames = sorted(Path(dest).glob("frame_*.jpg"))
    logger.info("frame_extract_done", count=len(frames), path=dest)

    if not frames:
        err = stderr.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"帧抽取失败——无输出帧: {err}")

    return [str(f) for f in frames]


# ── 主入口：Tool handler ──


async def watch_video(
    url: str,
    question: str = "请总结这个视频的内容",
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """watch_video Tool handler——下载→抽帧→字幕→分析。

    Returns:
        {"frames": [...], "captions": str|None, "analysis": str}
    """
    work_dir = tempfile.mkdtemp(prefix="orbit_watch_")
    try:
        # 1. 判断本地文件 vs URL
        is_local = os.path.isfile(url)
        if is_local:
            video_path = url
        else:
            video_path = await download_video(url, work_dir)

        # 2. 字幕（免费优先）
        # P1-2 fix: 在线视频用原始 URL 提取字幕，本地文件用 ffmpeg
        if is_local:
            captions = await _extract_local_captions(video_path)
        else:
            captions = await extract_captions(url)  # 传原始 URL，不是本地路径

        # 3. 帧抽取
        start_sec = _parse_time(start) if start else None
        end_sec = _parse_time(end) if end else None
        if start_sec and end_sec:
            budget = FrameBudget.auto(end_sec - start_sec)
        else:
            # 尝试获取时长——ffprobe
            dur = await _get_duration(video_path)
            budget = FrameBudget.auto(dur) if dur else FrameBudget.auto(600)

        frames = await extract_frames(video_path, budget, start_sec, end_sec, work_dir)

        # 4. 组装多模态 content——交给 P0 Gateway
        from orbit.gateway.client import LLMClient
        from orbit.gateway.schemas import LLMRequest

        content: list[dict] = []
        for fp in frames:
            content.append({"type": "image_url", "image_url": {"url": f"file://{fp}"}})
        if captions:
            content.append({"type": "text", "text": f"[字幕]\n{captions[:8000]}"})  # 64K 上下文留空间

        client = LLMClient()
        req = LLMRequest(
            prompt=question,
            content=content,
            # T2: 视频分析默认开启 thinking
            tier=2,
            max_tokens=4096,
        )
        resp = await client.generate(req, task_id=f"watch_{hash(url) & 0xFFFF:04x}")

        return {
            "frames_count": len(frames),
            "captions_available": captions is not None,
            "captions_length": len(captions) if captions else 0,
            "analysis": resp.content,
            "model": resp.model,
            "cost_usd": resp.usage.cost_usd,
        }

    finally:
        # 清理临时文件
        if not is_local and os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)


# ── 辅助函数 ──

# P2-1: SSRF 防护——内网/保留地址黑名单
BLOCKED_URL_PREFIXES = (
    "http://127.", "http://localhost", "http://10.",
    "http://172.16.", "http://172.17.", "http://172.18.",
    "http://172.19.", "http://172.20.", "http://172.21.",
    "http://172.22.", "http://172.23.", "http://172.24.",
    "http://172.25.", "http://172.26.", "http://172.27.",
    "http://172.28.", "http://172.29.", "http://172.30.",
    "http://172.31.", "http://192.168.", "http://169.254.",
    "http://0.", "http://[::1]",
)


def _validate_url(url: str) -> None:
    """检查 URL 是否安全——拒绝内网/保留地址（SSRF 防护）。"""
    url_lower = url.lower().strip()
    for prefix in BLOCKED_URL_PREFIXES:
        if url_lower.startswith(prefix):
            raise ValueError(f"禁止访问内网地址: {url[:80]}")
    if not url_lower.startswith(("http://", "https://")):
        raise ValueError(f"仅支持 HTTP/HTTPS URL: {url[:80]}")


async def _get_duration(video_path: str) -> float | None:
    """ffprobe 获取视频时长（秒）。"""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        return float(stdout.decode().strip())
    except Exception:
        return None


def _parse_time(s: str) -> float:
    """解析时间字符串 -> 秒。
    支持: '90', '1:30', '1:30:00'
    """
    s = s.strip()
    if ":" not in s:
        return float(s)
    parts = s.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])


# ── ToolRegistry 自动发现入口 ──
# AST 扫描 detect: registry.register() 触发自动导入
def _register():
    from orbit.tools.registry import get_registry
    registry = get_registry()
    registry.register(WATCH_VIDEO_SCHEMA, watch_video)

_register()
