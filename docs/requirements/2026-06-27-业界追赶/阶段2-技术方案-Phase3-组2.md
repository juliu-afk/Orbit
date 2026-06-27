# 技术方案——Phase 3 组 2：子Agent并发 + Goal Judge（AC13-AC14）

> 日期: 2026-06-27 | 依赖: 组 1 流式接口（ReActAgent.execute_stream）
> 参考: MiMo Code actor/spawn.ts + actor/registry.ts + session/goal.ts

---

## 1. PRD 对照

| AC | 标准 | 技术方案覆盖 |
|----|------|------------|
| AC14.1 | ActorRegistry SQLite 状态机 | `actors/registry.py` — pending→running→idle + outcome |
| AC14.2 | ActorSpawn 生命周期 | `actors/spawn.py` — allocate→register→fork→Deferred |
| AC14.3 | stale 5min 检测 | `actors/watchdog.py` — asyncio 后台扫描 |
| AC14.4 | 并发限制 max 4 | ActorSpawn semaphore |
| AC13.1 | GoalJudge Verdict schema | `goal_judge/judge.py` — {ok, impossible, reason}, temp=0 |
| AC13.2 | fail-open | judge 异常→ok=true（不困住用户） |
| AC13.3 | MAX_GOAL_REACT=12 | 硬上限→force ok+WARN |
| AC13.4 | Task Gate→Goal Gate | 两级门禁 |

---

## 2. 架构

```
Compose/User
    │
    ├─ ActorSpawn.spawn(task, role, context)
    │     │
    │     ├─ ActorRegistry.allocate() → actor_id
    │     ├─ AgentFactory.create(role) → ReActAgent
    │     ├─ asyncio.create_task(agent.execute_stream(token))
    │     └─ return DeferredActor(actor_id, future)
    │
    ├─ ActorRegistry (SQLite)
    │     pending → running → idle
    │     outcome: success | failure | cancelled
    │
    ├─ Watchdog (60s 扫描)
    │     stale >5min → zombie → cleanup
    │
    └─ GoalJudge
          Task Gate (check pending actors) → cheap
          Goal Gate (LLM verdict) → expensive
```

---

## 3. 数据模型

### ActorRecord
```python
class ActorStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    IDLE = "idle"
    ZOMBIE = "zombie"

class ActorOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"

class ActorRecord(BaseModel):
    actor_id: str
    parent_task_id: str
    role: str  # AgentRole value
    task: str
    status: ActorStatus = PENDING
    outcome: ActorOutcome | None = None
    result: dict | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    session_id: str | None = None
```

### Verdict
```python
class Verdict(BaseModel):
    ok: bool
    impossible: bool = False
    reason: str = ""
```

---

## 4. 文件清单（预估）

| 文件 | 行数 | 职责 |
|------|:--:|------|
| `src/orbit/actors/__init__.py` | 10 | 模块导出 |
| `src/orbit/actors/models.py` | 40 | ActorRecord/ActorStatus/ActorOutcome |
| `src/orbit/actors/registry.py` | ~120 | SQLite CRUD + 状态机 |
| `src/orbit/actors/spawn.py` | ~100 | ActorSpawn + DeferredActor |
| `src/orbit/actors/watchdog.py` | ~60 | stale 检测 + zombie 清理 |
| `src/orbit/goal_judge/__init__.py` | 10 | 模块导出 |
| `src/orbit/goal_judge/models.py` | 20 | Verdict/Goal |
| `src/orbit/goal_judge/judge.py` | ~90 | GoalJudge + Task Gate + Goal Gate |
| `tests/unit/test_actors.py` | ~100 | ActorRegistry + Spawn + Watchdog |
| `tests/unit/test_goal_judge.py` | ~80 | Verdict + fail-open + MAX_REACT |

**合计**: 10 文件，~630 行新增。
