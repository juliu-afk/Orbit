"""/dream 数据模型 (Phase 2 AC10)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class DreamStage(StrEnum):
    GATHER = "gather"
    MERGE_1 = "merge_1"
    MERGE_2 = "merge_2"
    DEDUP = "dedup"
    VERIFY = "verify"


class DreamStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    REJECTED = "rejected"


class DreamConfig(BaseModel):
    """dream 管线配置."""

    max_output_lines: int = Field(200, gt=0)
    max_output_bytes: int = Field(10_240, gt=0)  # 10KB
    auto_trigger_days: int = Field(7, gt=0)
    merge_temperature: float = Field(0.3, ge=0.0, le=2.0)
    verify_temperature: float = Field(0.1, ge=0.0, le=2.0)


class DreamResult(BaseModel):
    status: DreamStatus = DreamStatus.IDLE
    output_path: str = ""
    lines: int = 0
    bytes: int = 0
    errors: list[str] = Field(default_factory=list)
    verification_message: str = ""
