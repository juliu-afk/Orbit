# Phase 1 技术方案——CRAG + Memory 评分

> 基线: 阶段1-PRD-记忆库智能增强.md + ADR-记忆库智能增强.md
> 参考 ADR: #1 (GoalJudge suggestions), #2 (简单线性评分), #6 (不引入外部向量库)

## 改动文件

| File | Change | Detail |
|------|--------|--------|
| `memory/models.py` | 新增 `MemoryEntry` 字段 | score + last_hit_at |
| `memory/store.py` | 新增 search() + hit() + decay() | 评分读写方法 |
| `goal_judge/judge.py` | evaluate() 返回 suggestions | 内部调用 MemoryStore.search() |
| `agents/react_agent.py` | GoalJudge 调用点 | 注入 suggestions 到合成 user turn |
| `dream/engine.py` | DEDUP 阶段 | 按 score 排序优先淘汰 |
| `migrations/` | 新 SQL | ALTER TABLE memory_entries ADD COLUMN score/last_hit_at/hyde_questions |

## 数据流

### CRAG 补充检索
```
Agent turn → LLM 返回 → GoalJudge.evaluate() → not_ok
  → MemoryStore.search(transcript) → ["相关经验1", "相关经验2"]
  → evaluate() 返回 GoalVerdict(ok=False, suggestions=["经验1","经验2"])
  → react_agent 合成 user turn: "任务尚未完成——{reason}。相关经验：{suggestions}。请继续。"
```

### Memory 评分
```
写入: memory.put(key, value) → 新条目 score=1.0, last_hit_at=now()
命中: memory.hit(key) → score += 1, last_hit_at=now()
衰减: /dream 触发 → 所有条目 score *= 0.95（每天一次）
/dream DEDUP: ORDER BY score ASC → 低分优先移除
```

## 实现细节

### 1. MemoryEntry 模型扩展
```python
@dataclass
class MemoryEntry:
    key: str
    content: str
    memory_type: MemoryFileType
    score: float = 1.0        # NEW
    last_hit_at: float = 0.0  # NEW (epoch seconds)
```

### 2. MemoryStore.search() — 已存在，只需复用
现有 `search()` 方法返回 `list[MemoryEntry]`，GoalJudge 直接调用。

### 3. GoalJudge.evaluate() 签名
```python
# 现有
async def evaluate(self, goal: Goal, transcript: str, task_id: str) -> GoalVerdict

# 改进——GoalVerdict 增加 suggestions 字段
class GoalVerdict(BaseModel):
    ok: bool
    reason: str = ""
    suggestions: list[str] = []  # NEW
```

### 4. 迁移 SQL
```sql
ALTER TABLE memory_entries ADD COLUMN score REAL NOT NULL DEFAULT 1.0;
ALTER TABLE memory_entries ADD COLUMN last_hit_at REAL NOT NULL DEFAULT 0.0;
ALTER TABLE memory_entries ADD COLUMN hyde_questions TEXT DEFAULT '[]';
```

## 风险

- GoalJudge 调用 MemoryStore.search() 增加延迟——但 FTS5 搜索毫秒级，可接受
- 评分衰减需要在 /dream 定时任务中执行——如果 /dream 未触发，旧记忆不会衰减（可接受）
