"""V15.1 多模态 P1：审计截图管线。

Agent 关键决策点 → 自动截图 → 帧去重 → trajectory DB。

WHY 截图审计：纯文本日志无法证明 Agent 看到了什么。截图+决策并存，审计可回溯。

帧去重算法（WHY 16×16+MAD：低 CPU 开销，足够检测重复）：
  1. 缩放到 16×16 灰度
  2. 与上一帧比较 MAD (Mean Absolute Difference)
  3. MAD < 阈值 2.0 → 视为重复 → 丢弃
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger("orbit.observability.video_capture")

# ── 去重配置 ──
DEDUP_THUMB_SIZE = (16, 16)
DEDUP_MAD_THRESHOLD = 2.0  # 灰度 0-255 范围，2.0=极低敏感度

# ── 截图存储目录（相对于 Orbit data 目录）─
SCREENSHOT_DIR = "screenshots"


@dataclass
class ScreenshotRecord:
    """单张审计截图记录。"""
    filepath: str         # 截图文件路径
    timestamp: float      # Unix 时间戳
    task_id: str          # 关联的 Task ID
    agent_name: str       # 触发截图的 Agent
    decision_type: str    # 决策类型（post_voucher/config_change/generate_code 等）
    description: str      # 决策简述


@dataclass
class VideoCaptureState:
    """截图管线内部状态。"""
    last_thumb: list[int] | None = None  # 上一帧的 16×16 灰度像素
    total_captured: int = 0
    total_deduped: int = 0
    records: list[ScreenshotRecord] = field(default_factory=list)


class ScreenshotCapture:
    """审计截图捕获器。

    用法：
        cap = ScreenshotCapture(data_dir="/data/orbit")
        record = await cap.capture(
            frame,             # PIL Image 或 numpy array（来自 mss）
            task_id="task_1",
            agent_name="qa",
            decision_type="post_voucher",
            description="过账凭证 #123",
        )
        if record:
            print(f"Saved: {record.filepath}")

    WHY mss 而非 PIL ImageGrab：mss 跨平台 (Win/Mac/Linux)，速度更快。
    """

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.screenshot_dir = self.data_dir / SCREENSHOT_DIR
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.state = VideoCaptureState()

    async def capture(
        self,
        frame,  # PIL.Image or similar (有 .resize() 和 .convert() 方法)
        task_id: str,
        agent_name: str,
        decision_type: str,
        description: str = "",
    ) -> ScreenshotRecord | None:
        """捕获一帧——如果与上一帧不同则保存。

        Returns:
            ScreenshotRecord if saved, None if deduped.
        """
        # 1. 帧去重
        try:
            thumb = frame.resize(DEDUP_THUMB_SIZE).convert("L")
            pixels = list(thumb.get_flattened_data())  # Pillow 14+: getdata()→get_flattened_data()
        except Exception as e:
            logger.warning("screenshot_resize_failed", error=str(e))
            return None

        if self.state.last_thumb is not None:
            mad = sum(abs(a - b) for a, b in zip(pixels, self.state.last_thumb)) / 256.0
            if mad < DEDUP_MAD_THRESHOLD:
                self.state.total_deduped += 1
                return None  # 重复帧，丢弃

        # 2. 保存截图
        self.state.last_thumb = pixels
        ts = time.time()
        filename = f"orbit_audit_{task_id}_{agent_name}_{int(ts)}_{self.state.total_captured:04d}.jpg"
        filepath = self.screenshot_dir / filename

        try:
            frame.save(str(filepath), "JPEG", quality=75)
        except Exception as e:
            logger.warning("screenshot_save_failed", path=str(filepath), error=str(e))
            return None

        self.state.total_captured += 1

        record = ScreenshotRecord(
            filepath=str(filepath),
            timestamp=ts,
            task_id=task_id,
            agent_name=agent_name,
            decision_type=decision_type,
            description=description,
        )
        self.state.records.append(record)

        logger.info(
            "screenshot_captured",
            task_id=task_id,
            agent=agent_name,
            decision=decision_type,
            total=self.state.total_captured,
            deduped=self.state.total_deduped,
        )

        return record

    def get_session_records(self, task_id: str | None = None) -> list[ScreenshotRecord]:
        """获取本次 session 的截图记录。"""
        if task_id:
            return [r for r in self.state.records if r.task_id == task_id]
        return list(self.state.records)

    def get_stats(self) -> dict:
        """获取截图统计。"""
        return {
            "total_captured": self.state.total_captured,
            "total_deduped": self.state.total_deduped,
            "dedup_ratio": (
                self.state.total_deduped / max(1, self.state.total_captured + self.state.total_deduped)
            ),
            "dir": str(self.screenshot_dir),
        }


# ── 全局单例（供 Agent 钩子使用） ──
_capture_instance: ScreenshotCapture | None = None


def get_screenshot_capture(data_dir: str = "data") -> ScreenshotCapture:
    """获取全局 ScreenshotCapture 单例。"""
    global _capture_instance
    if _capture_instance is None:
        _capture_instance = ScreenshotCapture(data_dir)
    return _capture_instance
