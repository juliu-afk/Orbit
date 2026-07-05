# 阶段2-技术方案-TokenPhase2-ContextPrebuilder

> 日期: 2026-07-05 | 版本: v1.0 | 状态: 待用户确认
> 基于: [阶段1-PRD-TokenPhase2-ContextPrebuilder](阶段1-PRD-TokenPhase2-ContextPrebuilder.md) — 验收标准 9 条，本次技术方案覆盖 9 条，无偏离

---

## 1. 需求回顾

基于阶段1 PRD 核心验收标准：

| AC | 需求 |
|----|------|
| AC1 | 5 个 ContextPrebuilder 子类——按角色裁剪 context |
| AC2 | TaskContext 字段硬上限 5000 chars |
| AC3 | 7 个 Context Builder——映射 Phase 2 脚本 |
| AC4 | 5 个预扫描器——确定性工具，不用 LLM |
| AC5 | Reviewer context 不含完整 diff |
| AC6 | SCOPING 状态 → 变更范围 → 测试粒度决策 |
| AC7 | Token 基准测试 ≤ 改造前 70% |
| AC8 | 已有压缩管线不受影响 |
| AC9 | py_compile 全通过 |

SCOPING 插入位置（PRD §8.1 已确认）：`IDLE → PARSING → SCOPING → PLANNING → CODING → VERIFYING → DONE`

---

## 2. 影响范围

### 2.1 新增文件（18 个）

```
src/orbit/context/
├── __init__.py                        # 更新——导出新模块
├── prebuilder.py                      # ContextPrebuilder 基类 + 工厂
├── prebuilders/
│   ├── __init__.py
│   ├── clarifier.py                   # ClarifierContextPrebuilder
│   ├── architect.py                   # ArchitectContextPrebuilder
│   ├── developer.py                   # DeveloperContextPrebuilder
│   ├── reviewer.py                    # ReviewerContextPrebuilder
│   └── qa.py                          # QAContextPrebuilder
├── builders/
│   ├── __init__.py
│   ├── test_builder.py                # → test-input（应测清单）
│   ├── design_builder.py              # → design-input（影响面+候选文件）
│   ├── impl_builder.py                # → implementation-input（最小变更任务书）
│   ├── debug_builder.py               # → debug-input（根因候选+trace）
│   ├── req_builder.py                 # → requirements-input（AC提取+边界）
│   ├── docs_builder.py                # → docs-input（文档更新点）
│   └── release_builder.py             # → release-input（release notes+风险）
└── scanners/
    ├── __init__.py
    ├── affected_files.py              # git diff → 分类文件列表
    ├── import_deps.py                 # Python AST → 依赖图
    ├── test_coverage.py               # coverage.json → 覆盖率缺口
    ├── schema_change.py               # Alembic → 表/列变更
    └── permission_string.py           # 正则 → 权限字符串比对
```

### 2.2 修改文件（5 个）

| 文件 | 改动 | 理由 |
|------|------|------|
| `src/orbit/agents/context.py` | TaskContext 加 `max_chars_per_field` + `truncate()` 方法 | AC2 |
| `src/orbit/api/schemas/task.py` | TaskState 加 `SCOPING` | AC6 |
| `src/orbit/scheduler/task_runner.py` | 集成 ContextPrebuilder + SCOPING 状态 + ROLE_MAP/STATE_TRANSITIONS 更新 | AC1/AC6/AC8 |
| `src/orbit/scheduler/orchestrator.py` | 注入 ContextPrebuilder 到 TaskRunner | AC1 |
| `src/orbit/communication/message_bus.py` | Agent 间消息 max_chars 约束 | US6(P2) |

---

## 3. 架构设计

### 3.1 数据流（改造后）

```
Orchestrator
  │
  ▼
TaskRunner.run_task(task_id, prd)
  │
  ├─ IDLE     → chatter  (ContextPrebuilder: 通用对话)
  ├─ PARSING  → clarifier(ContextPrebuilder: 只给用户输入+项目说明书)
  ├─ SCOPING  → [规则引擎] (git diff → 变更范围报告, 非LLM)
  ├─ PLANNING → architect(ContextPrebuilder: 影响面+候选文件)
  ├─ CODING   → developer(ContextPrebuilder: 变更范围≤5文件+现有测试)
  └─ VERIFYING→ reviewer (ContextPrebuilder: diff摘要+权限+schema, 不含完整diff)
       │
       ▼
  _run_agent(role, task_id, context)
       │
       ├─ 1. ContextPrebuilder.build(role, task_type, raw_context)  ← 新增
       ├─ 2. Scanner pipeline (确定性扫描)                           ← 新增
       ├─ 3. TaskContext.truncate()                                  ← 新增
       ├─ 4. AgentFactory.create(role, ...)
       └─ 5. agent.execute(AgentInput)                              ← 已有
              │
              └─ ReAct 循环中 L1-L5 压缩兜底（已有，不变）
```

### 3.2 ContextPrebuilder 基类设计

```python
# src/orbit/context/prebuilder.py

class ContextPrebuilder(ABC):
    """上下文预构建器基类——Agent dispatch 前裁剪 context。

    纯 Python，0 LLM 调用。异常时 fail-open（返回原始 context）。
    """

    role: AgentRole
    max_chars_per_field: int = 5000  # 默认与 PromptBuilder 一致

    @abstractmethod
    def build(self, raw_context: dict) -> dict:
        """裁剪 context——删除无关字段、截断超大值、注入角色特定摘要。"""
        ...

    def _truncate_field(self, value: str, max_chars: int | None = None) -> str:
        """截断超长字符串——head+tail 保留关键信息。"""
        limit = max_chars or self.max_chars_per_field
        if len(value) <= limit:
            return value
        half = limit // 2
        return value[:half] + f"\n... [{len(value) - limit} chars truncated] ...\n" + value[-half:]

    @staticmethod
    def build_for_role(role: str) -> "ContextPrebuilder":
        """工厂方法——按角色返回对应预构建器。"""
        # 返回子类实例
```

### 3.3 5 个角色子类——裁剪规则

| 子类 | 保留字段 | 删除字段 | 特殊处理 |
|------|---------|---------|---------|
| ClarifierCP | `prd`, `brief`, `keywords`, `l1` | `l2`(代码), `artifacts`, `coverage_data` | prd 截断到 3000 |
| ArchitectCP | `prd`, `l2.file_list`, `l2.import_deps`, `brief` | `l2.file_contents`(全量代码) | 注入影响面摘要 |
| DeveloperCP | `prd`, `l2.affected_files`(≤5), `l2.existing_tests`, `artifacts.design` | `l2.full_diff`, 无关模块代码 | 代码片段不超 5 文件 |
| ReviewerCP | `prd`, `l2.diff_summary`, `l2.permission_changes`, `l2.schema_changes`, `artifacts` | `l2.full_diff`(完整 diff) | diff_summary ≤3000 chars |
| QACP | `prd`, `l2.affected_files`, `l2.test_gaps`, `l2.scope_report` | `l2.full_diff`, 全量测试列表 | 注入应测清单 |

### 3.4 SCOPING 状态设计

SCOPING 是纯规则引擎——无 LLM 调用，直接分析 git diff 输出变更范围报告。

```python
# task_runner.py 新增

SCOPING_ROLE = "__scoping__"  # 非 Agent 角色，规则引擎

async def _run_scoping(self, task_id: str, context: dict) -> str:
    """SCOPING 状态——确定性变更范围分析。非 LLM。"""
    scanners = [
        AffectedFilesScanner(),
        ImportDependencyScanner(),
    ]
    scope_report = {}
    for scanner in scanners:
        try:
            result = scanner.scan(context.get("project_path", "."))
            scope_report[scanner.name] = result
        except Exception:
            scope_report[scanner.name] = {"error": "scan_failed"}

    # 决策测试粒度
    affected = scope_report.get("affected_files", {})
    test_scope = _decide_test_scope(affected)
    scope_report["test_scope"] = test_scope

    context["scope_report"] = scope_report
    return json.dumps(scope_report)


def _decide_test_scope(affected: dict) -> str:
    """变更范围 → 测试粒度决策。
    - 仅 frontend/ → "smoke"
    - 触及 src/orbit/agents/ 等核心 → "full_regression"
    - 其他 → "unit_integration"
    """
    files = affected.get("changed", []) + affected.get("added", [])
    if not files:
        return "smoke"
    core_modules = {"src/orbit/agents/", "src/orbit/scheduler/", "src/orbit/gateway/",
                    "src/orbit/compression/", "src/orbit/hallucination/"}
    if any(any(f.startswith(m) for m in core_modules) for f in files):
        return "full_regression"
    if all(f.startswith("frontend/") for f in files):
        return "smoke"
    return "unit_integration"
```

### 3.5 状态转换更新

```python
# task_runner.py 修改

ROLE_MAP 新增:
    TaskState.SCOPING: "__scoping__",  # 规则引擎，非 Agent

STATE_TRANSITIONS 更新:
    TaskState.IDLE: TaskState.PARSING,
    TaskState.PARSING: TaskState.SCOPING,     # ← 新
    TaskState.SCOPING: TaskState.PLANNING,    # ← 新
    TaskState.PLANNING: TaskState.CODING,
    TaskState.CODING: TaskState.VERIFYING,
    TaskState.VERIFYING: TaskState.DONE,

FAST_LANE_TRANSITIONS 更新:
    TaskState.IDLE: TaskState.PARSING,
    TaskState.PARSING: TaskState.CODING,       # 快车道跳过 SCOPING+PLANNING
    TaskState.CODING: TaskState.DONE,

_state_to_progress 新增:
    TaskState.SCOPING: 0.3,   # PARSING(0.2) < SCOPING(0.3) < PLANNING(0.4)
```

### 3.6 _agent_cycle 分流逻辑

```python
async def _agent_cycle(self, task_id, state, context):
    role = ROLE_MAP.get(state)

    # SCOPING 走规则引擎——非 Agent
    if role == "__scoping__":
        return await self._run_scoping(task_id, context)

    # 其他状态走 Agent（已有逻辑）
    if role and self._agent_factory is not None:
        ...
```

### 3.7 _run_agent 集成 ContextPrebuilder

```python
async def _run_agent(self, role, task_id, context, timeout=None):
    # ... 已有代码 ...

    # ★ 新增: 前置 context 裁剪
    agent_context = self._build_context(task_id, context)
    prebuilder = ContextPrebuilder.build_for_role(role)
    try:
        pruned = prebuilder.build(agent_context.to_dict())
        agent_context = TaskContext(**pruned)  # 重建
    except Exception:
        logger.warning("prebuilder_failed_fail_open", role=role)  # fail-open

    # ... 已有代码: AgentInput → agent.execute() ...
```

---

## 4. 接口设计

### 4.1 ContextPrebuilder 接口

```python
class ContextPrebuilder(ABC):
    role: AgentRole                          # 类属性——绑定角色
    max_chars_per_field: int = 5000          # 字段硬上限

    @abstractmethod
    def build(self, raw_context: dict[str, Any]) -> dict[str, Any]:
        """裁剪 context dict——返回裁剪后的 dict。纯函数，无副作用。"""
        ...

    @staticmethod
    def build_for_role(role: str) -> "ContextPrebuilder":
        """工厂方法。"""
        mapping = {
            "clarifier": ClarifierContextPrebuilder(),
            "architect": ArchitectContextPrebuilder(),
            "developer": DeveloperContextPrebuilder(),
            "reviewer": ReviewerContextPrebuilder(),
            "qa": QAContextPrebuilder(),
        }
        return mapping.get(role, DeveloperContextPrebuilder())
```

### 4.2 Scanner 接口

```python
class BaseScanner(ABC):
    name: str                               # "affected_files" / "import_deps" 等

    @abstractmethod
    def scan(self, project_path: str, **kwargs) -> dict[str, Any]:
        """扫描项目——返回结构化 dict。纯函数，异常时返回 {"error": ...}。"""
        ...
```

### 4.3 Builder 接口

```python
class BaseBuilder(ABC):
    name: str                               # "test" / "design" / "impl" 等

    @abstractmethod
    def build(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """构建上下文包——返回结构化 dict。纯函数，输出可直接注入 Agent context。"""
        ...
```

---

## 5. TaskContext 改动

```python
# src/orbit/agents/context.py 改动

@dataclass
class TaskContext:
    # ... 已有字段 ...

    max_chars_per_field: int = 5000  # ★ 新增

    def to_dict(self) -> dict[str, Any]:
        raw = { ... }  # 已有逻辑
        return self._truncate_all(raw)

    def _truncate_all(self, d: dict) -> dict:
        """递归截断所有字符串值到 max_chars_per_field。"""
        result = {}
        for k, v in d.items():
            if isinstance(v, str) and len(v) > self.max_chars_per_field:
                half = self.max_chars_per_field // 2
                result[k] = v[:half] + f"\n... [{len(v) - self.max_chars_per_field} chars truncated] ...\n" + v[-half:]
            elif isinstance(v, dict):
                result[k] = self._truncate_all(v)
            elif isinstance(v, list):
                result[k] = [
                    self._truncate_all(item) if isinstance(item, dict)
                    else (item[:self.max_chars_per_field] if isinstance(item, str) and len(item) > self.max_chars_per_field else item)
                    for item in v
                ]
            else:
                result[k] = v
        return result
```

---

## 6. MessageBus 改动（P2，Phase C 实现）

```python
# src/orbit/communication/message_bus.py 改动

MAX_MESSAGE_BODY_CHARS = 10000  # 新增常量

class AgentMessageBus:
    async def request(self, req: Request) -> Response:
        # 已有逻辑 ...
        # ★ 新增: 响应体截断
        if resp.body and isinstance(resp.body, str) and len(resp.body) > MAX_MESSAGE_BODY_CHARS:
            resp.body = _truncate_message(resp.body)
        return resp
```

---

## 7. 风险点

| 风险 | 影响 | 缓解 |
|------|------|------|
| ContextPrebuilder 裁剪过激——删除 Agent 需要的信息 | Agent 输出质量下降 | fail-open 兜底 + 每个角色保留字段经人工审查 |
| SCOPING 插入破坏已有状态流转 | 已有任务卡住 | 仅影响新任务；SCOPING 是纯函数——异常直接跳过 |
| Python AST 扫描大型项目慢 | SCOPING 耗时增加 | 超时保护 5s——超时跳过扫描，降级为 generic 报告 |
| 压缩管线与预构建冲突 | Agent 拿到已被预构建裁剪的 context，L1-L5 再裁一轮 | 预构建不碰 `messages` 列表——只裁剪 `TaskContext`。L1-L5 操作 messages，两者正交 |
| max_chars 截断破坏 JSON/代码结构 | Agent 读到不完整的 JSON | 截断时保留可读性标记 `... [N chars truncated] ...` |

---

## 8. 与 PRD 对照表

| PRD AC | 技术方案覆盖 | 实现位置 |
|--------|------------|---------|
| AC1: 5 个 ContextPrebuilder | §3.3 裁剪规则表 + 5 子类 | `context/prebuilders/` |
| AC2: TaskContext 字段 ≤5000 | §5 `_truncate_all()` | `agents/context.py` 修改 |
| AC3: 7 个 Context Builder | §4.3 Builder 接口 + 7 子类 | `context/builders/` |
| AC4: 5 个预扫描器 | §4.2 Scanner 接口 + 5 子类 | `context/scanners/` |
| AC5: Reviewer 不含完整 diff | §3.3 ReviewerCP 裁剪规则——`l2.full_diff` 删除 | `context/prebuilders/reviewer.py` |
| AC6: SCOPING → 测试粒度 | §3.4 `_run_scoping()` + `_decide_test_scope()` | `scheduler/task_runner.py` 修改 |
| AC7: Token ≤70% | 后续 Phase C 基准测试验证 | `docs/requirements/.../阶段4-测试报告.md` |
| AC8: 已有压缩不受影响 | §7 风险点——预构建不碰 messages，L1-L5 正交 | `scheduler/task_runner.py` 集成 |
| AC9: py_compile 通过 | CI 门禁 | GitHub Actions |
| US6: Agent 间消息约束 | §6 MessageBus max_chars（Phase C） | `communication/message_bus.py` 修改 |

---

## 9. 实施顺序

遵照 PRD 优先级：

**Phase A（第 1 周）—— P0**
1. `TaskState.SCOPING` + 状态转换更新（[task.py](d:\Orbit\src\orbit\api\schemas\task.py) + [task_runner.py](d:\Orbit\src\orbit\scheduler\task_runner.py)）
2. `ContextPrebuilder` 基类 + 工厂（[context/prebuilder.py](d:\Orbit\src\orbit\context\prebuilder.py)）
3. `TaskContext._truncate_all()` （[agents/context.py](d:\Orbit\src\orbit\agents\context.py)）
4. 5 个 Scanner 中前 2 个——`AffectedFilesScanner` + `ImportDependencyScanner`
5. 集成到 `TaskRunner._run_agent()` + SCOPING 分流

**Phase B（第 2 周）—— P0+P1**
6. 5 个 ContextPrebuilder 子类
7. 7 个 Context Builder
8. 剩余 3 个 Scanner
9. 单元测试

**Phase C（第 3 周）—— P1+P2**
10. MessageBus 约束
11. 集成测试 + Token 基准测试
12. 文档更新

---

> 阶段门禁：请用户确认以上技术方案（特别是 §3.4 SCOPING 规则引擎设计、§3.5 状态转换更新、§7 风险点），确认后进入阶段 3 编码。
