# 阶段1 PRD — Step 5.1 调度器 DAG

> 基线来源：`docs/PRD+ADR_5阶段.md` Step 5.1 章节。

## 背景

MVP 状态机串行单路径，无法表达并行任务。需升级为 DAG 编排引擎。

## 用户故事

| 优先级 | 故事 |
|--------|------|
| P0 | 作为调度器，接收 TaskGraph（节点+依赖边），拓扑排序+并发执行，自动保存检查点 |
| P0 | 崩溃恢复：resume(task_id) 从检查点加载，跳过已完成节点 |
| P1 | 节点超时(30s)+重试(2次)，失败不影响其他节点 |

## 验收标准

| # | 验收标准 |
|----|---------|
| AC1 | DAG(A→B,A→C,B→D,C→D) → 拓扑序满足依赖（B/C在A后，D在B/C后） |
| AC2 | 两无依赖节点并发启动，时间差 <100ms |
| AC3 | 模拟崩溃→resume→已完成节点不重复执行 |
| AC4 | 节点超时→自动重试2次→最终失败不影响其他节点 |

## 范围

**Do**: DAG 并行执行、检查点自动保存/恢复、节点超时+重试、并发上限控制
**Don't**: 动态图修改、跨任务依赖

## 新增文件

| 文件 | 说明 |
|------|------|
| `src/orbit/scheduler/graph.py` | TaskGraph / GraphNode / NodeStatus |
| `src/orbit/scheduler/orchestrator.py` | 扩展 DAG 拓扑排序 + 并发执行 + 恢复 |

---

> 阶段1 PRD 基线：基于 `docs/PRD+ADR_5阶段.md` Step 5.1，验收标准 4 条。
