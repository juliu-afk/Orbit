# Orbit 记忆库智能增强 — 阶段1 PRD

> 日期: 2026-06-28 | 参考: DIKWP+黄金圈+RAG 记忆库设计 v1.0/v4.0 + CARO 类比推理方案
> 设计原则: **只取可落地的、适合代码 Agent 系统的、不违背 CLAUDE.md 审计要求的**

---

## 1. 背景

### 1.1 三份外部文档的核心洞察

| 来源 | 核心概念 | Orbit 缺口 |
|------|---------|-----------|
| CARO 类比推理方案 | CRAG 纠正检索、跨域类比、冷启动通用类比源 | GoalJudge 只判定不补充检索 |
| DIKWP+RAG v1.0 | 黄金圈检索权重、HyDE 查询扩展、Graph-RAG 多跳 | Memory 无评分进化、Scheduler 无意图路由 |
| v4.0 升级版 | CRAG 优先于 CARO、奖惩机制、金字塔结构 | Memory 条目权重均等 |

### 1.2 不适合直接移植的（含理由）

| 概念 | 理由 |
|------|------|
| A 层完整类比层（ChromaDB+CMS） | Orbit 是代码 Agent，不需要"投资↔生态系统"级跨域类比 |
| 逆推五层门控（P←W←K←I←D） | GoalJudge 已覆盖；5 层完整实现性价比低 |
| 直觉跳跃（intuition_jump） | 代码生产不可审计，违反审计要求 |
| RAPTOR 递归摘要 | /dream 5 阶段合并已覆盖 |
| 金字塔结构强制 | 代码输出天然金字塔（接口→实现），不需要额外结构 |

### 1.3 设计目标

1. GoalJudge 判定 not_ok 时，能从 memory 检索相似经验注入下一轮——而非单靠 LLM 自行修复
2. Memory 条目有质量评分——高频有效记忆优先保留，一次性噪音自动降权
3. Scheduler 按任务意图（Why/How/What）分类路由——不同任务走不同 Agent 链
4. Architect Agent 输出广度提升——多视角方案生成

---

## 2. 用户故事

### Phase 1：CRAG + 记忆评分（P0）

| # | 优先级 | 描述 | AC |
|---|:--:|------|-----|
| P1-1 | P0 | GoalJudge 判定 not_ok 时补充检索 | not_ok → memory.search() → 有结果则注入 "类似问题曾被这样解决: ..." |
| P1-2 | P0 | Memory 条目有评分，按评分排序 | 写入 score=1.0；每次命中 +1；每天 ×0.95 衰减 |
| P1-3 | P0 | /dream 合并时低分条目优先淘汰 | DEDUP 阶段按 score 排序，低于阈值的优先移除 |

### Phase 2：黄金圈路由 + 多视角提示（P1）

| # | 优先级 | 描述 | AC |
|---|:--:|------|-----|
| P2-1 | P1 | Task 创建时标注 Why/How/What 三元组 | Task API 接受黄金圈标签，写入 AgentInput.context |
| P2-2 | P1 | Scheduler 按 Why 分类选择初始 Agent 链 | Why=实现→Architect→Developer；Why=修复→QA→Developer→Reviewer |
| P2-3 | P1 | ArchitectAgent 多视角方案生成 | 输出 ≥2 个备选方案，从 [可行性/可维护性/性能] 评分 |

### Phase 3：HyDE + Graph-RAG 扩展（P2）

| # | 优先级 | 描述 | AC |
|---|:--:|------|-----|
| P3-1 | P2 | Memory 写入时生成 HyDE 假设问题 | 每条 memory 附带 3 条假设问答，检索时匹配 |
| P3-2 | P2 | 代码图谱支持跨文件关系检索 | import/调用/继承关系边，Agent 查询支持 1-2 跳扩展 |

---

## 3. Non-Goals

- 不新增外部依赖（ChromaDB、NetworkX 等——保持 SQLite+BM25 栈）
- 不改变 /dream 的 5 阶段合并架构（只在 DEDUP 阶段增加评分排序）
- 不修改 ReAct 循环控制流（GoalJudge 增强是 context 注入，不改逻辑）
- 不导入投资/金融领域的通用类比源库（Orbit 定位是代码 Agent）

---

## 4. 验收标准总览

| Phase | PR 数 | 预估工作量 | 关键 AC |
|-------|:--:|:--:|------|
| Phase 1 | 1 PR | ~2 天 | GoalJudge 补充检索 + memory 评分衰减 |
| Phase 2 | 1 PR | ~2 天 | 黄金圈任务路由 + 多视角架构师 |
| Phase 3 | 1 PR | ~5 天 | HyDE 查询扩展 + Graph-RAG 跨文件 |
