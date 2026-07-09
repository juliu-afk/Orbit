# 阶段2-技术方案-多模态P1-Tool层

> 基线：阶段1 PRD（4 条验收标准）· P0 Gateway 已实现
> 本次覆盖 SC1-SC4，无偏离
> 日期：2026-07-10

---

## 1. PRD 对照

| PRD | 实现 | 文件 |
|-----|------|------|
| SC1 watch_video | download_video() + extract_frames() + analyze() → LLMClient | video_tools.py |
| SC2 ocr_document | ocr_image() / ocr_pdf() → DeepSeek-OCR 2 API | ocr_tools.py |
| SC3 video_capture | ScreenshotHook → ffmpeg dedup → trajectory store | observability/video_capture.py |
| SC4 SKILL watch.md | 技能模板——参数/场景/帧策略 | compose/skills/watch.md |

## 2. 架构

```
Agent 调用 Tool
    │
    ├─ /watch <url>
    │   ├─ download_video(url) → /tmp/orbit_video_xxx.mp4 (yt-dlp subprocess)
    │   ├─ extract_frames(path) → [/tmp/frame_001.jpg, ...] (ffmpeg subprocess)
    │   ├─ extract_captions(path) → str | None (yt-dlp --write-subs)
    │   └─ LLMClient.generate(content=[frames+text]) → analysis result
    │
    ├─ /ocr <file>
    │   └─ DeepSeek-OCR 2 POST → markdown text
    │
    └─ [auto] audit screenshot
        ├─ ScreenshotHook.on_decision() → mss grab
        └─ dedup + store → trajectory DB
```

## 3. 数据模型

```python
# video_tools.py
@dataclass
class VideoInfo:
    path: str           # 本地路径
    duration_sec: float
    has_captions: bool
    captions_text: str | None
    frame_paths: list[str]  # 抽取的帧路径

@dataclass 
class FrameBudget:
    """帧预算——控制 token 消耗"""
    max_frames: int
    fps: float
    width: int = 512

    @classmethod
    def auto(cls, duration_sec: float) -> "FrameBudget":
        if duration_sec <= 30:   return cls(30, 1.0)
        if duration_sec <= 180:  return cls(60, 0.5)
        if duration_sec <= 600:  return cls(100, 0.2)
        return cls(100, 0.1)  # >10min 封顶
```

## 4. Tool 注册

```python
# tools/__init__.py 新增
ToolSchema(
    name="watch_video",
    version="1.0.0",
    description="下载并分析视频——提取关键帧+字幕，用多模态模型理解内容",
    parameters={
        "url": {"type": "string", "description": "视频 URL 或本地路径"},
        "question": {"type": "string", "description": "要分析的问题（可选，默认=总结）"},
        "start": {"type": "string", "description": "起始时间（可选，如 1:30）"},
        "end": {"type": "string", "description": "结束时间（可选，如 2:45）"},
    },
    permissions=[ToolPermission.READ],
    allowed_agents=["qa", "developer", "clarifier"],
    timeout_seconds=120,  # 下载+抽帧可能慢
)

ToolSchema(
    name="ocr_document",
    version="1.0.0",
    description="OCR 图片/PDF——提取文字和表格",
    parameters={
        "file_path": {"type": "string", "description": "图片或 PDF 路径"},
    },
    permissions=[ToolPermission.READ],
    allowed_agents=["qa", "developer", "clarifier", "architect"],
    timeout_seconds=60,
)
```

## 5. ffmpeg 帧抽取命令

```bash
# 关键帧模式：场景变化检测
ffmpeg -i input.mp4 -vf "select=gt(scene\,0.3),scale=512:-1" \
  -vsync vfr -q:v 2 /tmp/frames/frame_%04d.jpg

# 均匀采样模式：按 fps
ffmpeg -i input.mp4 -vf "fps=0.5,scale=512:-1" \
  -q:v 2 /tmp/frames/frame_%04d.jpg
```

## 6. 帧去重算法（审计截图）

```python
# 16x16 灰度缩略图 + MAD (Mean Absolute Difference)
# WHY 16x16：足够检测重复，极低 CPU 开销
def is_duplicate(img1: Image, img2: Image, threshold=2.0) -> bool:
    thumb1 = img1.resize((16,16)).convert("L")
    thumb2 = img2.resize((16,16)).convert("L")
    pixels1 = list(thumb1.getdata())
    pixels2 = list(thumb2.getdata())
    mad = sum(abs(a-b) for a,b in zip(pixels1, pixels2)) / 256
    return mad < threshold
```

## 7. 文件改动

| 文件 | 操作 | 预估行 |
|------|------|--------|
| `src/orbit/tools/video_tools.py` | **新建** | ~200 |
| `src/orbit/tools/ocr_tools.py` | **新建** | ~80 |
| `src/orbit/tools/__init__.py` | 修改 | +20 |
| `src/orbit/observability/video_capture.py` | **新建** | ~120 |
| `src/orbit/compose/skills/watch.md` | **新建** | ~50 |
| `tests/unit/test_video_tools.py` | **新建** | ~100 |
| `tests/unit/test_ocr_tools.py` | **新建** | ~60 |
| **合计** | 5 新 + 1 改 | ~630 |
