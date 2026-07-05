-- Trace 链路追踪表（Inkeep 借鉴 #4 / PR #195）
-- 可重复执行: 全部使用 IF NOT EXISTS

CREATE TABLE IF NOT EXISTS trace_spans (
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
);

CREATE INDEX IF NOT EXISTS idx_trace_task_id ON trace_spans(task_id);
CREATE INDEX IF NOT EXISTS idx_trace_created ON trace_spans(created_at);
