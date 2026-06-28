# PR #2 Type Safety — 阶段2 技术方案

> 基线: 阶段1-PRD-PR2-TypeSafety.md | 日期: 2026-06-28

## PRD 对照

| AC | 方案 |
|----|------|
| `_create_agent()` 无 `type: ignore` | ReActAgent.__init__ 加 `role: AgentRole \| None = None`，回退路径传 `role=role` 给构造函数 |
| 5 文件 `Any`→具体类型 | TYPE_CHECKING 导入 + `T \| None` 替换 `Any` |

## 类型映射

| 当前 | 具体类型 | 导入路径 |
|------|---------|---------|
| `llm: Any` | `LLMClient \| None` | `orbit.gateway.client` |
| `graph: Any` | `CodeGraphEngine \| None` | `orbit.graph.engines.code_graph` |
| `sandbox: Any` | `Sandbox \| None` | `orbit.sandbox.executor` |
| `event_bus: Any` | `EventBus \| None` | `orbit.events.bus` |
| `_compressor: Any` | `ContextCompressor \| None` | `orbit.compression.compressor` |
| `_budget_tracker: Any` | `TokenBudgetTracker \| None` | `orbit.compression.budget` |
| `actor_spawn: Any` | `ActorSpawn \| None` | `orbit.actors.spawn` |
| `registry: Any` | `ActorRegistry \| None` | `orbit.actors.registry` |
| `agent_factory: Any` | `type[AgentFactory] \| None` | `orbit.agents.factory` |

## 改动文件

### 1. `react_agent.py` — 基类 + Role 参数
- `__init__` 加 `role: AgentRole | None = None` → `self.role = role or type(self).role`
- `llm`, `graph`, `sandbox`, `event_bus` → 具体类型 `| None`
- `_compressor`, `_budget_tracker` → `ContextCompressor | None`, `TokenBudgetTracker | None`
- 已有 `TYPE_CHECKING` 块扩展导入

### 2. `factory.py` — AgentFactory
- `get_agent()` 参数 `llm`, `graph`, `sandbox`, `tools`, `event_bus` → 具体类型
- 构造 agent 时传 `role=role` 而非依赖类属性

### 3. `spawn.py` — ActorSpawn
- `__init__` 参数 `registry`, `agent_factory` → 具体类型
- `spawn()` 参数 `llm`, `tools`, `event_bus` → 具体类型
- `_create_agent()` → 传 `role=role` 给 SpawnedAgent，移除 `type: ignore`

### 4. `compose/orchestrator.py` — ComposeOrchestrator
- `actor_spawn` → `ActorSpawn | None`

### 5. `scheduler/orchestrator.py` — Scheduler
- `agent_factory`, `message_bus`, `tool_registry`, `router`, `audit_logger` → 具体类型 `| None`

## 风险

- **循环导入**：所有导入在 `TYPE_CHECKING` 块内，仅用于注解，运行时不会触发 import
- **ReActAgent 子类**：零子类覆盖 `__init__`，加 `role` 参数无影响
- **SpawnedAgent**：改回退路径 `class SpawnedAgent(ReActAgent): pass` → `SpawnedAgent(llm=..., tools=..., event_bus=..., role=role)`
