# 阶段2 技术方案 — Step 5.1 调度器 DAG

> 基于阶段1 PRD（验收标准 4 条），覆盖 4 条。

## PRD 对照表

| AC | 方案覆盖 | 实现文件 |
|----|---------|---------|
| AC1 拓扑排序 | Kahn 算法 + 循环检测 | `graph.py` TaskGraph.topological_sort() |
| AC2 并发执行 | asyncio.gather + Semaphore(MAX_CONCURRENT) | `orchestrator.py` _run_dag() |
| AC3 检查点恢复 | CheckpointManager 每节点完成后保存，resume 跳过已完成 | `orchestrator.py` resume() |
| AC4 超时重试 | asyncio.wait_for(30s) + 重试计数 ≤2 | `orchestrator.py` _execute_node() |

## 影响范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/orbit/scheduler/graph.py` | 新增 | TaskGraph / GraphNode / NodeStatus 数据模型 + 拓扑排序 |
| `src/orbit/scheduler/orchestrator.py` | 修改 | 扩展 run(graph) + resume(task_id) + 并发/超时/重试 |
| `src/orbit/core/config.py` | 修改 | +MAX_CONCURRENT_NODES + NODE_TIMEOUT + MAX_RETRIES |
| `tests/unit/test_scheduler.py` | 修改 | 扩展：拓扑排序/并发/恢复/超时/重试 |
| `tests/unit/test_graph.py` | 新增 | TaskGraph 数据模型 + 拓扑排序测试 |

## 核心设计

```python
class NodeStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"  
    FAILED = "failed"
    SKIPPED = "skipped"

class GraphNode(BaseModel):
    id: str
    agent_role: str = "developer"
    input: dict = {}
    output: dict | None = None
    status: NodeStatus = NodeStatus.PENDING
    retry_count: int = 0

class TaskGraph(BaseModel):
    task_id: str
    nodes: list[GraphNode]
    edges: list[tuple[str, str]]  # (src_id, dst_id)
    
    def topological_sort(self) -> list[list[str]]  # 分层拓扑（同层可并行）
    def validate(self) -> bool  # 无环检测
```

数据流: `API → TaskGraph → orchestrator.run(graph) → 拓扑分层 → asyncio.gather 每层 → 每节点 CheckpointManager.save()`

## 边缘 case

| 场景 | 预期行为 |
|------|---------|
| 空 DAG（0 节点） | 直接返回成功 |
| 单节点 | 正常执行 |
| 循环依赖 | validate() 抛出 DAGCycleError |
| 所有节点失败 | 快速失败，停止执行 |
| 并发数=1 | 退化为串行 |

## 风险

| # | 风险 | 缓解 |
|---|------|------|
| R1 | 并发 LLM 调用耗尽资源 | Semaphore(MAX_CONCURRENT_NODES=3) |
| R2 | 大 DAG 检查点序列化慢 | orjson + 仅保存状态元数据 |
| R3 | 无限重试 | max_retries=2 硬上限 |

## 测试策略

| 用例 | 覆盖 |
|------|------|
| test_topological_sort | AC1: 依赖顺序 |
| test_cycle_detection | 循环检测→异常 |
| test_concurrent_execution | AC2: 并行 <150ms |
| test_checkpoint_resume | AC3: 已完节点不重复 |
| test_node_timeout | AC4: 超时→重试→失败 |
| test_max_retries_exceeded | AC4: 2次重试后 FAILED |

---

> 阶段2 技术方案基线：基于阶段1 PRD（验收标准 4 条），方案覆盖 4 条。
