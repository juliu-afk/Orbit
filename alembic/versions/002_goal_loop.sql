-- Goal+Loop 模式数据表 (v5 PR-per-task 架构)
-- 可重复执行: 全部使用 IF NOT EXISTS

CREATE TABLE IF NOT EXISTS goal_sessions (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    constraints TEXT DEFAULT '[]',
    verification_commands TEXT DEFAULT '[]',
    sub_tasks TEXT DEFAULT '{}',
    spec TEXT,
    react_count INTEGER DEFAULT 0,
    max_react INTEGER DEFAULT 12,
    status TEXT DEFAULT 'active',
    total_token_budget INTEGER DEFAULT 0,
    token_consumed INTEGER DEFAULT 0,
    max_runtime_seconds INTEGER DEFAULT 0,
    max_parallel_tasks INTEGER DEFAULT 5,
    started_at TEXT DEFAULT (datetime('now')),
    last_verdict TEXT,
    verdict_history TEXT DEFAULT '[]',
    critique_history TEXT DEFAULT '[]',
    ensemble_results TEXT DEFAULT '[]',
    alignment_checks TEXT DEFAULT '[]',
    consecutive_failures INTEGER DEFAULT 0,
    consecutive_misalignments INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS loop_schedules (
    id TEXT PRIMARY KEY,
    interval_seconds INTEGER NOT NULL,
    command TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    last_run_at TEXT,
    next_run_at TEXT NOT NULL,
    run_count INTEGER DEFAULT 0,
    last_result TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
