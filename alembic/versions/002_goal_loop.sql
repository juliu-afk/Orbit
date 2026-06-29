-- Goal+Loop 模式数据表 (v5 PR-per-task 架构)
-- 可重复执行: 全部使用 IF NOT EXISTS

CREATE TABLE IF NOT EXISTS goal_sessions (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
<<<<<<< HEAD
    -- P2-2: JSON 字段使用 json_valid CHECK
    constraints TEXT DEFAULT '[]' CHECK(json_valid(constraints)),
    verification_commands TEXT DEFAULT '[]' CHECK(json_valid(verification_commands)),
    sub_tasks TEXT DEFAULT '{}' CHECK(json_valid(sub_tasks)),
    spec TEXT,
    react_count INTEGER DEFAULT 0,
    max_react INTEGER DEFAULT 12,
    -- P2-1: 枚举字段 CHECK 约束
    status TEXT DEFAULT 'active' CHECK(status IN ('active','done','failed','cancelled','paused')),
=======
    constraints TEXT DEFAULT '[]',
    verification_commands TEXT DEFAULT '[]',
    sub_tasks TEXT DEFAULT '{}',
    spec TEXT,
    react_count INTEGER DEFAULT 0,
    max_react INTEGER DEFAULT 12,
    status TEXT DEFAULT 'active',
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
    total_token_budget INTEGER DEFAULT 0,
    token_consumed INTEGER DEFAULT 0,
    max_runtime_seconds INTEGER DEFAULT 0,
    max_parallel_tasks INTEGER DEFAULT 5,
    started_at TEXT DEFAULT (datetime('now')),
    last_verdict TEXT,
<<<<<<< HEAD
    verdict_history TEXT DEFAULT '[]' CHECK(json_valid(verdict_history)),
    critique_history TEXT DEFAULT '[]' CHECK(json_valid(critique_history)),
    ensemble_results TEXT DEFAULT '[]' CHECK(json_valid(ensemble_results)),
    alignment_checks TEXT DEFAULT '[]' CHECK(json_valid(alignment_checks)),
=======
    verdict_history TEXT DEFAULT '[]',
    critique_history TEXT DEFAULT '[]',
    ensemble_results TEXT DEFAULT '[]',
    alignment_checks TEXT DEFAULT '[]',
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
    consecutive_failures INTEGER DEFAULT 0,
    consecutive_misalignments INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

<<<<<<< HEAD
-- P1-4: 调度查询索引
CREATE INDEX IF NOT EXISTS idx_goal_sessions_status ON goal_sessions(status, created_at);

-- P2-3: updated_at 自动刷新 trigger
CREATE TRIGGER IF NOT EXISTS trg_goal_sessions_updated_at
AFTER UPDATE ON goal_sessions
BEGIN
    UPDATE goal_sessions SET updated_at = datetime('now') WHERE id = NEW.id;
END;

=======
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
CREATE TABLE IF NOT EXISTS loop_schedules (
    id TEXT PRIMARY KEY,
    interval_seconds INTEGER NOT NULL,
    command TEXT NOT NULL,
<<<<<<< HEAD
    -- P2-1: 枚举字段 CHECK 约束
    status TEXT DEFAULT 'active' CHECK(status IN ('active','paused','stopped')),
=======
    status TEXT DEFAULT 'active',
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
    last_run_at TEXT,
    next_run_at TEXT NOT NULL,
    run_count INTEGER DEFAULT 0,
    last_result TEXT,
<<<<<<< HEAD
    -- P2-6: 统一包含 updated_at
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- P1-4: 调度器轮询索引
CREATE INDEX IF NOT EXISTS idx_loop_schedules_next_run ON loop_schedules(next_run_at, status);

-- P2-3: updated_at 自动刷新 trigger
CREATE TRIGGER IF NOT EXISTS trg_loop_schedules_updated_at
AFTER UPDATE ON loop_schedules
BEGIN
    UPDATE loop_schedules SET updated_at = datetime('now') WHERE id = NEW.id;
END;
=======
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
