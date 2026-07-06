# 阶段2-技术方案-Grill交互协议层.md

> 基于阶段1 PRD（验收标准共 8 条），本次技术方案覆盖 8 条，无偏离。
> 研究基线：`docs/research/grill-ecosystem-deconstruction.html`

---

## 一、需求回顾

| AC# | 验收标准 | 对应 US |
|-----|---------|--------|
| AC1 | `src/orbit/modes/` 目录存在，含 3 个内置 mode | US1 |
| AC2 | `AgentFactory` 创建 Agent 时读取 mode.yaml | US1 |
| AC3 | 换 mode.yaml 中 `question_strategy` 后 ClarifierAgent 行为变化 | US1 |
| AC4 | TaskContext 三阶段加载，Stage 1 默认 ≤2K tokens | US2 |
| AC5 | fast lane 任务只触发 Stage 1 | US2 |
| AC6 | Stage 2 在工具调用失败时自动触发 | US2 |
| AC7 | 现有 453 测试全部通过 | 回归 |
| AC8 | 新增 mode 加载 + 上下文阶段的单元测试 ≥10 条 | 覆盖率 |

---

## 二、影响范围

### 新增文件（8 个）

| 文件 | 用途 | 预估行数 |
|------|------|---------|
| `src/orbit/modes/__init__.py` | 包初始化，导出 ModeLoader | 10 |
| `src/orbit/modes/schemas.py` | ModeConfig / BehaviorConfig Pydantic 模型 | 50 |
| `src/orbit/modes/loader.py` | ModeLoader——读取/校验/缓存 mode.yaml | 80 |
| `src/orbit/modes/clarify/mode.yaml` | 需求澄清模式配置 | 20 |
| `src/orbit/modes/clarify/references/question-tree.md` | 决策树模板 | 30 |
| `src/orbit/modes/clarify/references/domain-checks.md` | 领域检查规则 | 20 |
| `src/orbit/modes/architect/mode.yaml` | 架构设计模式配置 | 15 |
| `src/orbit/modes/review/mode.yaml` | 代码审查模式配置 | 15 |

### 修改文件（4 个）

| 文件 | 改动内容 | 预估改动行数 |
|------|---------|-------------|
| `src/orbit/agents/factory.py` | `get_agent()` 新增 `mode` 参数；注入 `self.mode` 到 Agent 实例 | +15 |
| `src/orbit/agents/clarifier.py` | 从 `self.mode` 读取行为参数；`question_strategy` 控制提问模式 | +10 |
| `src/orbit/agents/context.py` | 新增 `ContextStage` 枚举；`TaskContext.load_stage()` 方法；三阶段数据源 | +40 |
| `src/orbit/scheduler/task_runner.py` | `_agent_cycle()` 加载 mode；`_build_context()` 改为仅构建 Stage 1；`_run_agent()` 失败自动升级 | +30 |

**总计**：新增 ~240 行 Python + ~100 行 YAML/Markdown，修改 ~95 行。

---

## 三、数据模型设计

### 3.1 ModeConfig (schemas.py)

```python
from enum import StrEnum
from pydantic import BaseModel, Field

class QuestionStrategy(StrEnum):
    DEPTH_FIRST = "depth_first"      # 深度优先——完成一个分支再开下一个
    BREADTH_FIRST = "breadth_first"  # 广度优先——先扫所有分支顶层
    MIXED = "mixed"                  # 混合——关键分支深度优先，次要广度优先

class BehaviorConfig(BaseModel):
    """Agent 行为参数——从 mode.yaml 加载，注入 Agent 实例"""
    question_strategy: QuestionStrategy = QuestionStrategy.DEPTH_FIRST
    max_questions_per_branch: int = Field(default=20, ge=1, le=100)
    require_recommendation: bool = True   # 每个问题必须带推荐答案
    codebase_first: bool = True           # 能查代码就不问用户
    auto_upgrade_context: bool = True     # 失败时自动升级上下文阶段

class ModeConfig(BaseModel):
    """模式文件顶层结构"""
    name: str                            # clarify / architect / review
    version: int = 1
    description: str = ""
    applies_to: list[str] = Field(default_factory=list)  # [PARSING] / [PLANNING] / [VERIFYING]
    behavior: BehaviorConfig = Field(default_factory=BehaviorConfig)
    references: list[str] = Field(default_factory=list)   # 按需加载的文件名列表
```

### 3.2 ContextStage (context.py 追加)

```python
from enum import IntEnum

class ContextStage(IntEnum):
    """上下文加载阶段——渐进式披露"""
    STAGE1 = 1  # 直接上下文（当前文件+直接依赖）~2K tokens
    STAGE2 = 2  # 扩展上下文（调用链+相关测试）~5K tokens
    STAGE3 = 3  # 全局上下文（架构文档+历史决策）~10K tokens

# TaskContext 新增字段
# stage: ContextStage = ContextStage.STAGE1
# 方法: async def load_stage(self, stage: ContextStage, **sources) -> None
```

### 3.3 mode.yaml 实例（clarify/mode.yaml）

```yaml
name: clarify
version: 1
description: "需求澄清——深度优先决策树遍历，一次一个问题，带推荐答案"
applies_to:
  - PARSING
behavior:
  question_strategy: depth_first
  max_questions_per_branch: 20
  require_recommendation: true
  codebase_first: true
  auto_upgrade_context: true
references:
  - question-tree.md
  - domain-checks.md
```

---

## 四、API / 接口设计

### 4.1 ModeLoader（新增，无 HTTP API）

```python
class ModeLoader:
    """模式文件加载器——启动时加载，缓存到内存"""

    def __init__(self, modes_dir: str = "src/orbit/modes"):
        self._modes_dir = Path(modes_dir)
        self._cache: dict[str, ModeConfig] = {}

    def load(self, mode_name: str) -> ModeConfig:
        """加载 mode.yaml → ModeConfig。解析失败抛 ModeLoadError，上游降级到默认行为。"""

    def load_reference(self, mode_name: str, ref_name: str) -> str:
        """按需加载 references/ 下的文件内容。≤200 行限制。"""

    def list_modes(self) -> list[str]:
        """列出所有可用 mode 名。"""

    def resolve_for_state(self, state: str) -> ModeConfig | None:
        """根据状态机阶段（PARSING/PLANNING/VERIFYING）自动匹配 mode。"""
```

### 4.2 AgentFactory 接口变更

```python
# 旧签名
cls.get_agent(role: AgentRole | str, llm=..., graph=..., ...) -> BaseAgent

# 新签名——追加 mode 参数
cls.get_agent(
    role: AgentRole | str,
    llm=..., graph=..., ...,  # 现有参数不变
    mode: ModeConfig | None = None,  # 新增——注入行为配置
) -> BaseAgent

# 注入方式：agent._mode = mode  # 设置实例属性
```

### 4.3 TaskContext 接口变更

```python
# 旧：_build_context 一次性构建全部 5 层
ctx = TaskContext(task_id=..., l1=..., l2=..., l3=..., l4=..., l5=...)

# 新：_build_context 只构建 Stage 1（L1+L3 核心字段）
ctx = TaskContext(task_id=..., l1=..., l3=...)  # l2/l4/l5 延迟加载

# Agent 需要更深上下文时：
await ctx.load_stage(ContextStage.STAGE2, memory_store=store, graph=graph)
# → 填充 l2（图谱查询结果）+ l4（工作记忆）

await ctx.load_stage(ContextStage.STAGE3, knowledge=kb)
# → 填充 l5（长期记忆检索结果）
```

---

## 五、数据流

### 5.1 Mode 加载流程

```
scheduler/task_runner.py:_agent_cycle()
  │
  ├─ 1. role = ROLE_MAP[state]                    # "clarifier"
  ├─ 2. mode = ModeLoader().resolve_for_state(state)  # PARSING → clarify/mode.yaml
  ├─ 3. agent = AgentFactory.get_agent(role, mode=mode, ...)
  │      └─ factory.py: agent._mode = mode         # 注入到实例
  ├─ 4. result = await self._run_agent(role, task_id, context)
  │      └─ agent.execute(input_data)
  │           └─ clarifier.py: strategy = self._mode.behavior.question_strategy
  │              if strategy == "depth_first": ...   # 行为分支
  └─ 5. mode 加载失败 → 日志警告 → 降级到默认行为
```

### 5.2 渐进式上下文加载流程

```
_run_agent() 执行前：
  ctx = _build_context(task_id, context)             # Stage 1 only

Agent 执行中：
  try:
    result = agent.execute(input_data)
  except ToolCallFailed:                             # Stage 2 触发条件
    await ctx.load_stage(ContextStage.STAGE2, ...)   # 加载 L2+L4
    result = agent.execute(input_data)               # 重试

Agent 显式请求更深上下文：
  if "需要架构文档" in result:
    await ctx.load_stage(ContextStage.STAGE3, ...)   # Stage 3——L5 全局
```

---

## 六、与 PRD 对照表

| AC# | 技术实现 | 验证方式 |
|-----|---------|---------|
| AC1 | 新建 `src/orbit/modes/` + 3 个子目录 + mode.yaml | `ls src/orbit/modes/clarify/mode.yaml` |
| AC2 | `AgentFactory.get_agent()` 新增 `mode` 参数，注入 `agent._mode` | 单元测试：mock ModeLoader，断言 agent._mode 非 None |
| AC3 | `clarifier.py` 中读取 `self._mode.behavior.question_strategy` | 集成测试：换 mode.yaml 中 strategy → 断言 agent 行为变化 |
| AC4 | `TaskContext` 新增 `ContextStage`，`_build_context` 只构建 Stage 1 | 单元测试：断言 ctx.stage == STAGE1, ctx.l2 == {} |
| AC5 | `ComplexityScorer` 返回 fast → SCOPING 阶段直接走 CODING，不触发 Stage 2 | 集成测试：fast lane 任务断言 ctx.stage 始终为 STAGE1 |
| AC6 | `_run_agent()` 中 ToolCallFailed/AgentOutput error → `ctx.load_stage(STAGE2)` | 单元测试：mock 失败，断言 load_stage 被调用 |
| AC7 | 不改核心模型/调度器逻辑，mode 参数有默认值 None→降级 | `pytest tests/ -q` 453 passed |
| AC8 | `tests/unit/test_modes/` 6 条 + `tests/unit/test_context_stage.py` 4 条 | pytest --cov |

---

## 七、风险点

| 风险 | 触发条件 | 缓解 |
|------|---------|------|
| mode.yaml 格式错误 | 用户手动编辑出错 | `ModeLoader.load()` 捕获 Pydantic ValidationError → 日志警告 → 降级 None |
| references 文件过大 | 用户写入超大 markdown | `load_reference()` 截断 >200 行 |
| Stage 升级循环 | Agent 反复失败→反复升级 | Stage 每任务最多升级一次（Stage 1→2→3，不回退） |
| 与现有 ContextPrebuilder 冲突 | 两个上下文构建路径重叠 | Mode 系统不替代 ContextPrebuilder，只在 Agent 层追加行为参数 |

---

> 基于阶段2 技术方案（覆盖 PRD 8 条验收标准），等待用户确认后进入阶段3 编码实现。
