# Orbit 记忆库智能增强 — ADR（架构决策记录）

> 日期: 2026-06-28 | 设计原则: 最小侵入、渐进增强、审计可追溯

---

## ADR-1: CRAG 补充检索 vs GoalJudge 重写

**问题**: GoalJudge 判定 not_ok 后，现有行为是合成 `"请继续"` user turn，LLM 自行修复。有效但缺上下文。

**选项**:

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A: 重写 GoalJudge | 在 `evaluate()` 内加检索逻辑 | 集中 | 职责膨胀 |
| B: 在 react_agent 调用点加钩子 | GoalJudge 返回后，agent 自己做补充检索 | 不改 GoalJudge 接口 | 双重判定 |
| **C: GoalJudge 返回增强上下文** | `evaluate()` 返回 `verdict + suggestions` | 接口自然扩展，调用方只需消费 | 需改 GoalJudge 签名 |

**决策**: **方案 C**。`GoalJudge.evaluate()` 新增可选 `suggestions: list[str]` 字段。not_ok 时 Judge 内部调用 `MemoryStore.search(transcript)` 生成建议。agent 调用方将 suggestions 注入到合成 user turn 中。

**理由**: GoalJudge 已有 memory 访问能力（`src/orbit/goal_judge/judge.py`）。接口改动最小，向后兼容（新字段可选）。

---

## ADR-2: Memory 评分模型——简单线性 vs 复杂 Bayesian

**问题**: 如何给 memory 条目打分，使其随时间"进化"。

**选项**:

| 方案 | 描述 | 存储 | 计算 |
|------|------|------|------|
| A: 简单线性 | score=1.0，命中+1，每日×0.95 | SQLite 一个列 | O(1) |
| B: Bayesian 信心区间 | 每次命中更新 α/β 参数 | 两个列 | O(1) 但有除法 |
| **C: 二元指数衰减** | reward_score 命中+1，penalty_score 未命中-1，最终得分 = reward×decay - | penalty| 两个列 | O(1) |

**决策**: **方案 A（简单线性）**，后续可升级。

**理由**:
1. Orbit 的 memory 条目量级预估 <10K，不需要复杂模型
2. 单列实现，`/dream` DEDUP 阶段直接 `ORDER BY score DESC`
3. v4.0 文档的奖惩机制过度设计——Orbit 不是面向最终用户的问答系统，不需要区分"惩罚类型"

**数据模型**:
```sql
ALTER TABLE memory_entries ADD COLUMN score REAL NOT NULL DEFAULT 1.0;
ALTER TABLE memory_entries ADD COLUMN last_hit_at TEXT;  -- ISO timestamp
-- 每天凌晨 /dream 触发时执行: UPDATE memory_entries SET score = score * 0.95
```

---

## ADR-3: 黄金圈标签——Pydantic 字段 vs 独立表

**问题**: Task 的三元组标签存在哪里。

**选项**:

| 方案 | 描述 |
|------|------|
| A: Pydantic AgentInput 增加字段 | `why: str, how: str, what: str` 内嵌 |
| B: 独立 SQLite 表 `task_labels` | 外键关联 task_id |

**决策**: **方案 A**。三个字符串字段内嵌到 `AgentInput.context`。

**理由**:
1. AgentInput 已有 `context: dict[str, Any]`，天然支持扩展
2. Scheduler 读取 `context.get("golden_why")` 即可路由，无需新表查询
3. KISS——三个标签不需要关系模型

**路由表**:
```python
GOLDEN_ROUTE: dict[str, list[AgentRole]] = {
    "实现新功能": [ARCHITECT, DEVELOPER],
    "修复Bug":   [QA, DEVELOPER, REVIEWER],
    "代码审查":  [REVIEWER],
    "重构":      [ARCHITECT, DEVELOPER],
    "数据分析":  [DEVELOPER],  # 直接执行
}
```

---

## ADR-4: HyDE 存储——单独集合 vs 内嵌

**问题**: HyDE 生成的假设问题存在哪里。

**选项**:

| 方案 | 描述 |
|------|------|
| A: 独立 FTS5 虚拟表 | `memory_hyde` 表，外键关联 memory_id |
| B: 内嵌到 memory_entries | JSON 列 `hyde_questions`，写入时 LLM 生成 |

**决策**: **方案 B**（内嵌）。Phase 3 实现。

**理由**:
1. 避免外键 JOIN——检索时 `SELECT * FROM memory_entries WHERE memory_entries MATCH ?` 即可同时命中原文和 HyDE 问题
2. FTS5 支持 JSON 列内容索引（`MATCH` 会扫描所有文本列）
3. 不需要 ChromaDB，保持零外部依赖

**数据模型**:
```sql
ALTER TABLE memory_entries ADD COLUMN hyde_questions TEXT;  -- JSON array of strings
-- 写入时: LLM 根据 content 生成 3 条"这个记忆能回答什么问题"
-- 检索时: FTS5 MATCH 自动覆盖 content + hyde_questions
```

---

## ADR-5: Graph-RAG 扩展——轻量 NetworkX vs 继续 SQLite

**问题**: 跨文件代码关系存在哪里。

**选项**:

| 方案 | 描述 | 依赖 |
|------|------|------|
| A: NetworkX + gpickle | Python 内存图，序列化到文件 | 零新依赖（NetworkX 已在 pyproject.toml 吗？检查） |
| B: SQLite 邻接表 | `code_edges(source, target, relation_type)` 表 | 零新依赖 |

**决策**: **方案 B**（SQLite 邻接表）。Phase 3 实现。

**理由**:
1. Orbit 已用 SQLite 存储代码图谱（`src/orbit/graph/`），加表不加库
2. 1-2 跳图遍历用 SQL 递归 CTE 即可，不需要图算法库
3. 查询模式是 `WHERE source = ?` 或 `WHERE target = ?`，不是 PageRank

**数据模型**:
```sql
CREATE TABLE IF NOT EXISTS code_edges (
    source_path TEXT NOT NULL,
    target_path TEXT NOT NULL,
    relation_type TEXT NOT NULL,  -- 'imports' | 'calls' | 'inherits'
    source_name TEXT,
    target_name TEXT,
    UNIQUE(source_path, target_path, relation_type)
);
-- 2 跳查询: WITH RECURSIVE ... SELECT DISTINCT target_path FROM ...
```

---

## ADR-6: 不引入 ChromaDB / 外部向量库

**问题**: 三份文档多次建议 ChromaDB + bge-large-zh 向量存储。

**决策**: **不引入**。保持 Orbit 零外部依赖（SQLite + FTS5 + BM25）。

**理由**:
1. Orbit 的 memory 条目量级 <10K，BM25 精度足够
2. FTS5 已支持 BM25 排序（`ORDER BY rank`）
3. 部署成本——ChromaDB 需要额外进程/持久化目录，违反"单文件 keshen.db"架构
4. 如果未来量级突破 100K，考虑 sqlite-vec 扩展（纯 SQLite 生态内）

---

## 决策总览

| ADR | 决策 | Phase |
|-----|------|:--:|
| 1 | GoalJudge 返回 suggestions 字段 | 1 |
| 2 | 简单线性评分（score + last_hit_at） | 1 |
| 3 | 黄金圈内嵌 AgentInput.context | 2 |
| 4 | HyDE 内嵌 FTS5 JSON 列 | 3 |
| 5 | SQLite 邻接表做代码跨文件关系 | 3 |
| 6 | 不引入 ChromaDB/外部向量库 | 全部 |
