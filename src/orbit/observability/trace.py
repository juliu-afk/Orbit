"""TraceSpan——任务执行链路追踪（Inkeep 借鉴 #4）。

WHY: Inkeep 的 Visual Builder 直接展示 Agent 决策 Trace。
Orbit OTEL 数据进了 structlog 日志，但驾驶舱没有可视化 Trace。
本模块提供 Span 模型 + 异步存储 + 三层保留（7d/30d/导出）。

埋点覆盖：orchestrator→task_runner→agent→tool→sandbox→verify。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field

# 默认保留配置（可通过 US-5 配置面板调整）
DEFAULT_FULL_RETENTION_DAYS = 7
DEFAULT_SUMMARY_RETENTION_DAYS = 30


class SpanStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    IN_PROGRESS = "in_progress"


class TraceSpan(BaseModel):
    """单个 trace span。"""

    span_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    parent_span_id: str | None = None
    task_id: str
    component: str   # "orchestrator" | "task_runner" | "agent" | "sandbox" | "tool"
    action: str      # "schedule" | "agent_call" | "tool_exec" | "verify" | "checkpoint"
    input_summary: str = ""
    output_summary: str = ""
    duration_ms: float = 0.0
    status: SpanStatus = SpanStatus.IN_PROGRESS
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict = Field(default_factory=dict)  # model, token_count, tool_name 等


class TraceTree(BaseModel):
    """完整 trace tree——API 返回结构。"""

    task_id: str
    root_spans: list[TraceSpan]
    total_duration_ms: float
    span_count: int


class _SpanRecord(BaseModel):
    """内部存储记录——span + task_id 索引。"""

    span_id: str
    parent_span_id: str | None
    task_id: str
    component: str
    action: str
    input_summary: str
    output_summary: str
    duration_ms: float
    status: str
    created_at: str
    metadata_json: str  # JSON-encoded metadata dict


class TraceCollector:
    """Span 收集器——异步批量写入 SQLite。

    用法（埋点侧）:
        span = TraceCollector.start_span(task_id, component="orchestrator", action="schedule")
        # ... 调度逻辑 ...
        TraceCollector.end_span(span, status=SpanStatus.OK)

    WHY 批量写入: 不阻塞主流程——span 先入 asyncio.Queue，后台 worker 批量 flush。
    """

    _queue: asyncio.Queue[_SpanRecord | None] = asyncio.Queue(maxsize=10000)
    _worker_task: asyncio.Task | None = None
    _db_path: str = ""

    @classmethod
    def start_span(
        cls,
        task_id: str,
        *,
        component: str,
        action: str,
        parent_span_id: str | None = None,
        input_summary: str = "",
        metadata: dict | None = None,
    ) -> TraceSpan:
        span = TraceSpan(
            task_id=task_id,
            component=component,
            action=action,
            parent_span_id=parent_span_id,
            input_summary=input_summary[:256],  # 截断长输入
            status=SpanStatus.IN_PROGRESS,
            metadata=metadata or {},
        )
        return span

    @classmethod
    def end_span(
        cls,
        span: TraceSpan,
        status: SpanStatus = SpanStatus.OK,
        output_summary: str = "",
        duration_ms: float | None = None,
    ) -> None:
        span.status = status
        span.output_summary = output_summary[:256]
        if duration_ms is not None:
            span.duration_ms = duration_ms
        # 入队异步写入
        record = _SpanRecord(
            span_id=span.span_id,
            parent_span_id=span.parent_span_id,
            task_id=span.task_id,
            component=span.component,
            action=span.action,
            input_summary=span.input_summary,
            output_summary=span.output_summary,
            duration_ms=span.duration_ms,
            status=span.status.value,
            created_at=span.created_at,
            metadata_json=json.dumps(span.metadata, ensure_ascii=False),
        )
        try:
            cls._queue.put_nowait(record)
        except asyncio.QueueFull:
            pass  # fail-open——不阻塞主流程

    @classmethod
    async def start_worker(cls, db_path: str) -> None:
        """启动后台 flush worker。"""
        cls._db_path = db_path
        if cls._worker_task is not None:
            return
        cls._worker_task = asyncio.create_task(cls._flush_loop())

    @classmethod
    async def stop_worker(cls) -> None:
        """停止 worker——flush 剩余 span 后退出。"""
        if cls._worker_task is None:
            return
        cls._queue.put_nowait(None)  # 哨兵
        await cls._worker_task
        cls._worker_task = None

    @classmethod
    async def _flush_loop(cls) -> None:
        """后台循环——每 500ms 或累积 50 条 flush 一次。"""
        import aiosqlite

        batch: list[_SpanRecord] = []
        while True:
            try:
                record = await asyncio.wait_for(cls._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                record = None  # 超时——flush 已有 batch

            if record is None and not batch:
                # 检查哨兵
                if cls._queue.empty():
                    break
                continue

            if record is not None:
                batch.append(record)

            # flush 条件：50 条或超时
            if record is None or len(batch) >= 50:
                if batch:
                    await cls._flush_batch(batch)
                    batch = []

    @classmethod
    async def _flush_batch(cls, batch: list[_SpanRecord]) -> None:
        """批量写入 SQLite。"""
        import aiosqlite

        try:
            async with aiosqlite.connect(cls._db_path) as db:
                await db.execute(
                    """CREATE TABLE IF NOT EXISTS trace_spans (
                        span_id TEXT PRIMARY KEY,
                        parent_span_id TEXT,
                        task_id TEXT NOT NULL,
                        component TEXT NOT NULL,
                        action TEXT NOT NULL,
                        input_summary TEXT DEFAULT '',
                        output_summary TEXT DEFAULT '',
                        duration_ms REAL DEFAULT 0,
                        status TEXT DEFAULT 'in_progress',
                        created_at TEXT NOT NULL,
                        metadata_json TEXT DEFAULT '{}'
                    )"""
                )
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_trace_task_id ON trace_spans(task_id)"
                )
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_trace_created ON trace_spans(created_at)"
                )
                await db.executemany(
                    """INSERT OR REPLACE INTO trace_spans
                       (span_id, parent_span_id, task_id, component, action,
                        input_summary, output_summary, duration_ms, status,
                        created_at, metadata_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (
                            r.span_id, r.parent_span_id, r.task_id, r.component,
                            r.action, r.input_summary, r.output_summary,
                            r.duration_ms, r.status, r.created_at, r.metadata_json,
                        )
                        for r in batch
                    ],
                )
                await db.commit()
        except Exception:
            pass  # fail-open——trace 写入失败不阻塞


class TraceStore:
    """Trace 查询接口——从 SQLite 读取 span 并构建 tree。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def get_trace_tree(self, task_id: str) -> TraceTree | None:
        """查询完整 trace tree。"""
        import aiosqlite

        try:
            async with aiosqlite.connect(self._db_path) as db:
                cursor = await db.execute(
                    "SELECT * FROM trace_spans WHERE task_id = ? ORDER BY created_at",
                    (task_id,),
                )
                rows = await cursor.fetchall()
        except Exception:
            return None

        if not rows:
            return None

        spans: list[TraceSpan] = []
        for row in rows:
            metadata = {}
            try:
                metadata = json.loads(row[10]) if row[10] else {}
            except (json.JSONDecodeError, TypeError):
                pass
            spans.append(TraceSpan(
                span_id=row[0],
                parent_span_id=row[1],
                task_id=row[2],
                component=row[3],
                action=row[4],
                input_summary=row[5] or "",
                output_summary=row[6] or "",
                duration_ms=row[7] or 0.0,
                status=row[8] or "in_progress",
                created_at=row[9] or "",
                metadata=metadata,
            ))

        root_spans = [s for s in spans if s.parent_span_id is None]
        total_duration = sum(s.duration_ms for s in root_spans)

        return TraceTree(
            task_id=task_id,
            root_spans=root_spans,
            total_duration_ms=total_duration,
            span_count=len(spans),
        )

    async def get_recent_tasks(self, limit: int = 20) -> list[dict]:
        """列出最近有 trace 的任务。"""
        import aiosqlite

        try:
            async with aiosqlite.connect(self._db_path) as db:
                cursor = await db.execute(
                    """SELECT task_id, COUNT(*) as span_count,
                              MAX(created_at) as last_seen
                       FROM trace_spans
                       GROUP BY task_id
                       ORDER BY last_seen DESC
                       LIMIT ?""",
                    (limit,),
                )
                rows = await cursor.fetchall()
        except Exception:
            return []

        return [
            {"task_id": row[0], "span_count": row[1], "last_seen": row[2]}
            for row in rows
        ]

    async def cleanup(self, full_days: int = 7, summary_days: int = 30) -> int:
        """三层保留清理——>30天删除，7-30天聚合为摘要。

        Returns:
            删除的 span 数量。
        """
        import aiosqlite

        now = datetime.now(UTC)
        full_cutoff = (now - timedelta(days=full_days)).isoformat()
        summary_cutoff = (now - timedelta(days=summary_days)).isoformat()

        try:
            async with aiosqlite.connect(self._db_path) as db:
                # >30 天：彻底删除
                cursor = await db.execute(
                    "DELETE FROM trace_spans WHERE created_at < ?",
                    (summary_cutoff,),
                )
                deleted = cursor.rowcount
                # 7-30 天：保留 root span（parent_span_id IS NULL），删子 span
                await db.execute(
                    "DELETE FROM trace_spans WHERE created_at < ? AND parent_span_id IS NOT NULL",
                    (full_cutoff,),
                )
                await db.commit()
                return deleted
        except Exception:
            return 0

    async def export_otel_json(self, task_id: str) -> str | None:
        """导出为 OTEL JSON 格式。"""
        tree = await self.get_trace_tree(task_id)
        if tree is None:
            return None
        # 简化的 OTEL 格式
        otel = {
            "resourceSpans": [{
                "scopeSpans": [{
                    "spans": [
                        {
                            "spanId": s.span_id,
                            "parentSpanId": s.parent_span_id,
                            "name": f"{s.component}.{s.action}",
                            "kind": 1,  # INTERNAL
                            "startTimeUnixNano": s.created_at,
                            "endTimeUnixNano": s.created_at,  # 简化——无精确 end time
                            "status": {"code": 1 if s.status == SpanStatus.OK else 2},
                            "attributes": [
                                {"key": "task_id", "value": {"stringValue": s.task_id}},
                                {"key": "component", "value": {"stringValue": s.component}},
                                {"key": "action", "value": {"stringValue": s.action}},
                            ],
                        }
                        for s in tree.root_spans
                    ]
                }]
            }]
        }
        return json.dumps(otel, indent=2, ensure_ascii=False)
