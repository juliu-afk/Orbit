"""测试相关 REST API 端点。

端点:
- POST /api/v1/tests/run — 触发测试执行
- GET  /api/v1/tests/results/{task_id} — 获取测试结果
- GET  /api/v1/tests/coverage?module= — 获取覆盖率
- POST /api/v1/tests/ab-compare — 触发 AB 策略对比（Phase 3）
- GET  /api/v1/tests/history?module=&days=7 — 历史趋势
- WS   /ws/tests/{task_id} — 实时测试进度（Phase 2）

WHY 独立路由文件: API 层薄封装——参数校验 + 调 orchestrator + 响应格式化。
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tests", tags=["tests"])


# ── Pydantic 模型 ────────────────────────────────────────────────


class TestRunRequest(BaseModel):
    code: str = Field(..., min_length=1, description="被测代码内容")
    module: str = Field(default="", description="所属模块名")
    goal_id: str = Field(default="", description="关联的 Goal ID")
    prd_text: str = Field(default="", description="PRD 文本（提取测试意图用）")


class TestRunResponse(BaseModel):
    task_id: str
    status: str


class ABCompareRequest(BaseModel):
    code: str = Field(..., min_length=1)
    strategies: list[str] = Field(default_factory=lambda: ["intention_driven", "path_sensitive"])


class CoverageFile(BaseModel):
    path: str
    pct: float
    missing_lines: list[int] = []


class CoverageResponse(BaseModel):
    files: list[CoverageFile]
    avg_pct: float


# ── 全局 orchestrator 引用（由 main.py 启动时注入） ───────────────

_orchestrator = None


def get_orchestrator():
    """获取全局 orchestrator 实例。"""
    global _orchestrator
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="测试服务未初始化")
    return _orchestrator


def set_orchestrator(orchestrator):
    """注入 orchestrator 实例——由 main.py 启动时调用。"""
    global _orchestrator
    _orchestrator = orchestrator


# ── 端点 ─────────────────────────────────────────────────────────


@router.post("/run", response_model=TestRunResponse)
async def run_tests(req: TestRunRequest):
    """触发测试执行。返回 task_id 供后续查询。"""
    orch = get_orchestrator()
    try:
        result = await orch.run(
            code=req.code,
            module=req.module,
            goal_id=req.goal_id,
            prd_text=req.prd_text,
        )
        return TestRunResponse(
            task_id=result.get("task_id", ""),
            status=result.get("verdict", "running"),
        )
    except Exception as e:
        logger.exception("测试执行失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results/{task_id}")
async def get_test_results(task_id: str):
    """获取测试结果——返回前端可消费的摘要卡片 JSON。"""
    # Phase 1: 结果存内存，后续 Phase 2 持久化
    raise HTTPException(status_code=404, detail="结果已过期或不存在——Phase 2 持久化后可用")


@router.get("/coverage", response_model=CoverageResponse)
async def get_coverage(module: str = Query(default="", description="模块名过滤")):
    """获取覆盖率报告。"""
    # Phase 1: 读 coverage.json 文件
    import json
    from pathlib import Path

    cov_path = Path("coverage.json")
    if not cov_path.exists():
        return CoverageResponse(files=[], avg_pct=0.0)

    try:
        data = json.loads(cov_path.read_text(encoding="utf-8"))
        files_data = data.get("files", {}) if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return CoverageResponse(files=[], avg_pct=0.0)

    files: list[CoverageFile] = []
    total_pct = 0.0
    for path, info in files_data.items():
        if module and module not in path:
            continue
        pct = info.get("summary", {}).get("percent_covered", 0.0)
        missing = info.get("missing_lines", [])
        files.append(CoverageFile(path=path, pct=pct, missing_lines=missing))
        total_pct += pct

    avg = round(total_pct / len(files), 1) if files else 0.0
    return CoverageResponse(files=files, avg_pct=avg)


@router.post("/ab-compare")
async def trigger_ab_compare(req: ABCompareRequest):
    """触发 AB 策略对比——Phase 3 实现。"""
    raise HTTPException(status_code=501, detail="AB 对比 Phase 3 实现")


@router.get("/history")
async def get_test_history(
    module: str = Query(default=""),
    days: int = Query(default=7, ge=1, le=90),
):
    """获取模块测试历史趋势——Phase 2 实现。"""
    raise HTTPException(status_code=501, detail="历史趋势 Phase 2 实现")
