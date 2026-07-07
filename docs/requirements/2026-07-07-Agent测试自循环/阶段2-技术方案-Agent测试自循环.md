# 阶段 2 技术方案 —— Agent 测试自循环模块

> **基于阶段 1 PRD**：[`阶段1-PRD-Agent测试自循环.md`](阶段1-PRD-Agent测试自循环.md)
> PRD 验收标准共 12 条，本方案覆盖 12 条，无偏离。
> 详细设计见 [`Orbit测试环节设计——Agent自循环测试体系.md`](../../research/Orbit测试环节设计——Agent自循环测试体系.md)

---

## 一、PRD 验收标准 → 技术方案对照表

| # | PRD 验收标准 | 技术方案如何满足 | 实现位置 |
|---|-----------|----------------|---------|
| AC1 | 代码生成后自动触发测试 | orchestrator 注册为 Agent 代码生成完成回调 | `testing/orchestrator.py:on_code_generated()` |
| AC2 | 聊天流摘要卡片 | TestResultCard.vue + MessageItem 新增 `test_result` 段类型 | `frontend/.../TestResultCard.vue` |
| AC3 | 秒级测试 ≤30s | 沙箱同步执行单元+PBT，并行变异测试 | `testing/orchestrator.py:run()` |
| AC4 | 自修复 ≤3 轮 | orchestrator 循环：失败 → 读失败信息 → LLM 修复 → 重跑 | `testing/orchestrator.py:_repair_loop()` |
| AC5 | 3 轮未修复 → 标记 FAILED | 循环计数器 + GateDecision.FAILED_PERMANENT | `testing/gate.py` |
| AC6 | TDD 顺序：测试先于实现 | intention.py 提取 → strategy 生成测试 → 然后才调代码生成 Agent | `testing/orchestrator.py:run_tdd()` |
| AC7 | 覆盖率 <80% → 补测试 | gate.py 返回 SUPPLEMENT → orchestrator 调 strategy 补测试 | `testing/gate.py:evaluate()` |
| AC8 | RTS 只跑受影响模块 | rts.py 调 code_graph.get_callers/get_callees → 交集测试 | `testing/rts.py` |
| AC9 | 阶段1 生成 Gherkin 骨架 | intention.py 从 PRD 验收标准文本提取 → .feature 文件 | `testing/intention.py:extract_gherkin()` |
| AC10 | 阶段2 生成契约测试骨架 | intention.py 从 API 设计（OpenAPI/Pydantic）推导 → pytest 骨架 | `testing/intention.py:extract_contract()` |
| AC11 | AB 结果沉淀到 knowledge | ab_runner.py → knowledge 知识图谱 upsert AB 结果 | `testing/strategies/ab_runner.py` |
| AC12 | 框架冲突自动检测 | redundancy_check.py 调 code_graph.exists + get_all_edges + BGE 语义相似 → FrameworkFitReport | `testing/redundancy_check.py` |
| AC13 | testing/ 自身覆盖率 ≥80% | 自身单元测试放在 tests/unit/test_testing_*.py | `tests/unit/test_testing_*.py` |

---

## 二、影响范围

### 2.1 新增文件

```
src/orbit/testing/                    # 新模块（~10 文件）
├── __init__.py
├── orchestrator.py                   # 核心编排器
├── intention.py                      # Test Intention 提取
├── gate.py                           # 质量门禁
├── rts.py                            # 智能测试选择
├── agent_behavior.py                 # Agent 行为测试
├── feedback.py                       # 失败模式回灌
├── reporter.py                       # 测试报告生成
├── redundancy_check.py               # 框架适配检查——冗余/循环依赖/跨层调用
├── strategies/
│   ├── __init__.py
│   ├── intention_driven.py           # 意图驱动
│   ├── path_sensitive.py             # 路径敏感（Phase 2）
│   ├── mutation_guided.py            # 变异引导（Phase 3）
│   ├── property_based.py             # 属性测试（Phase 2）
│   └── ab_runner.py                  # AB 对比（Phase 3）
└── api/
    ├── __init__.py
    └── test_routes.py                # REST API

frontend/src/components/chat/
└── TestResultCard.vue                # 新组件（~60 行）

tests/unit/
├── test_testing_intention.py
├── test_testing_gate.py
├── test_testing_rts.py
├── test_testing_orchestrator.py
├── test_testing_reporter.py
├── test_testing_redundancy_check.py
└── test_testing_ab_runner.py
```

### 2.2 修改文件

| 文件 | 改动 | 理由 |
|------|------|------|
| `frontend/.../MessageItem.vue` | +~20 行：新增 `test_result` 段类型解析 | 测试摘要卡片内嵌在聊天流中 |
| `frontend/.../TestPanel.vue` | +~30 行：加 `compact` prop + 回调 | 复用现有面板，不加新面板 |
| `src/orbit/agents/base.py` | +~5 行：代码生成完成 → 调 orchestrator 回调 | 自动触发测试执行的钩子 |
| `pyproject.toml` | +1 行：`mutmut` dev dependency（Phase 2） | 变异测试引擎 |
| `orbit.spec` | +2 行：`testing` 模块 hiddenimport | PyInstaller 打包 |

### 2.3 不修改的文件

- 现有 45 个模块：零修改。testing/ 是纯编排层，通过已有公开接口调用。
- WORKFLOW.md：不修改。阶段 1-4 流程不变，testing/ 在阶段 3 自动运行，不改变流程结构。
- CI 配置 (.github/)：不修改。CI 已有 pytest 命令，testing/ 生成的测试 CI 自动覆盖。

---

## 三、API 设计

### 3.1 端点列表

| 方法 | 路径 | 请求体 | 响应 | 错误码 |
|------|------|--------|------|--------|
| POST | `/api/v1/tests/run` | `{ code, module, goal_id }` | `{ task_id, status }` | 422, 409 |
| GET | `/api/v1/tests/results/{task_id}` | — | `TestRunResult` | 404 |
| GET | `/api/v1/tests/coverage?module=` | — | `{ files: CoverageFile[], avg_pct }` | — |
| POST | `/api/v1/tests/ab-compare` | `{ code, strategies: [str] }` | `{ winner, scores }` | 422 |
| GET | `/api/v1/tests/history?module=&days=7` | — | `{ trend: DataPoint[] }` | — |
| WS | `/ws/tests/{task_id}` | — | `TestProgress` 事件流 | 404 |

### 3.2 Pydantic 模型

```python
# testing/api/models.py

from pydantic import BaseModel, Field
from datetime import datetime

class TestRunRequest(BaseModel):
    code: str = Field(..., description="被测代码内容")
    module: str = Field(..., description="所属模块名，如 scheduler.state_machine")
    goal_id: str | None = Field(None, description="关联的 Goal ID")

class TestCaseResult(BaseModel):
    name: str
    file: str
    status: str  # "passed" | "failed" | "skipped"
    duration: float
    error: str | None = None
    line: int | None = None  # 失败的代码行号

class CoverageGap(BaseModel):
    file: str
    line: int
    branch: str | None = None  # 未覆盖的分支描述
    reason: str | None = None  # 为什么未覆盖（Agent 分析）

class ABCompareResult(BaseModel):
    strategy_a: str
    score_a: float
    strategy_b: str
    score_b: float
    winner: str
    delta: float  # 分差

class TestRunResult(BaseModel):
    task_id: str
    status: str  # "running" | "passed" | "failed" | "supplement" | "failed_permanent"
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    coverage_pct: float = 0.0
    mutation_score: float | None = None
    duration_sec: float = 0.0
    cases: list[TestCaseResult] = []
    gaps: list[CoverageGap] = []
    ab_result: ABCompareResult | None = None
    repair_attempts: int = 0  # 修复尝试次数
    created_at: datetime = Field(default_factory=datetime.utcnow)

class TestProgress(BaseModel):
    """WebSocket 实时推送的测试进度"""
    task_id: str
    phase: str  # "generating" | "executing" | "verifying" | "done"
    current: int  # 当前进度
    total: int    # 总数
```

### 3.3 统一响应格式

```json
// 成功
{ "code": 0, "data": { <TestRunResult> }, "message": "ok" }

// 失败
{ "code": 409, "data": null, "message": "同一模块已有测试任务运行中" }
{ "code": 422, "data": null, "message": "code 字段不能为空" }
```

---

## 四、数据模型

### 4.1 不新增数据库表

testing/ 模块**不创建新表**。测试结果通过以下方式持久化：

| 数据 | 存储方式 | 位置 |
|------|---------|------|
| 测试执行日志 | 审计表（已有 `audit_entries`） | `observability/audit.py` |
| 失败模式 | 知识图谱（已有 knowledge.db） | `knowledge/` — BGE 向量 + JSON 元数据 |
| AB 结果 | 知识图谱 | `knowledge/` — 关联到模块名 |
| 覆盖率趋势 | 文件系统 `coverage.json`（已有） | 项目根目录 |
| 运行时状态 | 内存（`TestRunResult` 对象） | orchestrator 生命周期 |

**理由**：
- 测试结果是瞬态数据——人类看完摘要卡片（2 秒）后不再需要原始日志
- 长期需要的只有失败模式（回灌给 Agent）和覆盖率趋势（Dashboard）
- 不建表 = 零 schema 变更 = 零迁移脚本 = 零风险

### 4.2 knowledge/ 存储结构

```python
# 失败模式在 knowledge/ 中的存储
{
    "type": "test_failure_pattern",
    "module": "scheduler.state_machine",
    "error_type": "NullPointerError",
    "pattern": "状态转换时未检查 self.context 是否为 None",
    "frequency": 5,  # 出现次数
    "last_seen": "2026-07-07T12:00:00Z",
    "vector": "<BGE embedding>"  # 语义搜索用
}

# AB 结果在 knowledge/ 中的存储
{
    "type": "ab_result",
    "module": "scheduler.state_machine",
    "strategy_a": "path_sensitive",
    "score_a": 0.82,
    "strategy_b": "intention_driven",
    "score_b": 0.76,
    "winner": "path_sensitive",
    "delta": 0.06,
    "timestamp": "2026-07-07T12:00:00Z"
}
```

---

## 五、数据流

### 5.1 主流程：代码生成 → 测试 → 反馈

```
┌─────────────────────────────────────────────────────────────────────┐
│  1. 触发                                                             │
│  agents/base.py                                                      │
│  on_code_generated(code, module, goal_id)                            │
│  → testing/orchestrator.run(code, module, goal_id)                   │
│                                                                      │
│  2. 意图提取                                                         │
│  testing/intention.py                                                │
│  extract(code, goal_id) → TestIntention                              │
│  ├── 从 goal/ 获取 PRD 文本 → 提取验收标准                           │
│  ├── 从 code 提取函数签名/类名/参数                                  │
│  └── 输出: { positive, negative, invariants, edge_cases }            │
│                                                                      │
│  3. 知识检索                                                         │
│  knowledge/ 查询                                                      │
│  ├── 历史失败模式（同模块）                                          │
│  ├── AB 结果（同模块最优策略）                                       │
│  └── 相似场景测试模板                                                │
│                                                                      │
│  4. 策略选择 + 生成测试                                              │
│  testing/strategies/                                                 │
│  ├── AB 结果有历史胜者 → 直接用                                      │
│  ├── 两种策略都适用 → ab_runner.compare()                            │
│  ├── 一种策略 → 直接用                                              │
│  └── LLM (via gateway/) 生成测试代码                                 │
│                                                                      │
│  5. 框架适配检查（秒级，不阻塞）                                      │
│  testing/redundancy_check.py                                         │
│  ├── code_graph.exists() → 同名函数？→ ⚠️ 警告                       │
│  ├── BGE 语义相似度 >0.85 → 相似签名？→ ⚠️ 警告                      │
│  ├── code_graph.get_callees() 分析 import 图 → 循环依赖？→ 🔴 阻塞   │
│  ├── 架构规则匹配（API 层直接写 SQL？）→ ⚠️ 警告                     │
│  └── 输出: FrameworkFitReport { blockings, warnings }                │
│                                                                      │
│  6. 沙箱执行                                                         │
│  ── 仅当框架检查无阻塞项时才进入沙箱 ──                               │
│  checkpoint/ → save(task_id) → sandbox/ → run(tests + code)          │
│  输出: pytest JSON 结果                                              │
│                                                                      │
│  7. 门禁判定                                                         │
│  testing/gate.py                                                     │
│  ├── 编译失败 → FAILED → 进入修复循环                                │
│  ├── 覆盖率 <80% → SUPPLEMENT → 补测试                               │
│  ├── 变异评分 <70% → SUPPLEMENT（仅核心模块）                        │
│  └── 全部通过 → PASSED                                               │
│                                                                      │
│  8. 修复循环（最多 3 轮）                                            │
│  orchestrator._repair_loop()                                          │
│  ├── 分析失败原因（LLM 读 stderr）                                   │
│  ├── 生成修复代码                                                    │
│  ├── 重跑测试                                                        │
│  └── 3 轮仍失败 → FAILED_PERMANENT → 通知人类                        │
│                                                                      │
│  9. 反馈回灌                                                         │
│  testing/feedback.py                                                 │
│  ├── 失败模式 → knowledge/ 入库                                      │
│  ├── AB 结果 → knowledge/ 入库                                      │
│  ├── observability/ 记录审计                                         │
│  └── evolution/ 通知（失败率 > 阈值 → 调整 Prompt）                   │
│                                                                      │
│ 10. 生成报告                                                         │
│  testing/reporter.py + review/ → CrossReport                         │
│  ├── 合并测试结果 + 审查结果                                          │
│  ├── 交叉验证（测试和审查在同一代码点上的结论是否一致）                 │
│  ├── 一致 → 摘要卡片绿色 [通过]                                       │
│  └── 分歧 → 摘要卡片黄色 + divergent_points → 人类只看分歧点          │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 副流程：阶段 1/2 提前生成骨架

```
阶段 1 PRD 确认后:
  goal/ → intention.py:extract_gherkin(prd_text)
  → 正则提取验收标准行 → 模板生成 Gherkin .feature
  → 保存到 docs/requirements/.../阶段1-测试骨架.feature

阶段 2 技术方案确认后:
  API 设计文本 → intention.py:extract_contract(api_design)
  → 正则提取端点/方法/请求体/响应/错误码
  → 模板生成 pytest 骨架
  → 保存到 tests/integration/test_*_skeleton_*.py
```

### 5.3 副流程：AB 对比

```
ab_runner.compare(code, intention):
  ├── 并行跑策略 A 和策略 B                          ← 生成阶段
  ├── 各自跑变异测试 → mutation_score                 ← 评估阶段
  ├── 胜者 > 败者 20% → 记录到 knowledge/            ← 沉淀
  └── 返回胜者（orchestrator 用胜者的测试作为最终产物）
```

---

### 5.4 框架适配检查细节（`redundancy_check.py`）

**定位**：测试不判断"有没有更好的写法"——那是代码审查的职责。但**冗余和冲突**可以用代码图谱自动检测，测试在沙箱执行前先跑这个 Pass，给人类审查提供信号。

```
redundancy_check.run(code, module):
  ├── 1. 同名检查 (code_graph.exists)
  │     └── 新函数名是否已存在同模块？→ ⚠️ WARNING
  ├── 2. 语义相似检查 (BGE 向量相似度)
  │     └── 同模块内相似签名 >0.85？→ ⚠️ WARNING
  ├── 3. 导入冗余检查
  │     └── 新代码 import 了已有 util 但自己实现了等价逻辑？→ ℹ️ INFO
  ├── 4. 循环依赖检查 (code_graph.get_callees 分析 import 图)
  │     └── 新 import 关系是否形成环？→ 🔴 BLOCKING
  └── 5. 架构越界检查（规则引擎）
        └── API 层直接写 ORM 查询？utils/ import 了 api/？→ ⚠️ WARNING

输出: FrameworkFitReport
```

**Pydantic 模型**：

```python
class FrameworkIssue(BaseModel):
    severity: str  # "blocking" | "warning" | "info"
    type: str      # "name_conflict" | "semantic_duplicate" | "circular_dep" | "layer_violation" | "import_redundant"
    detail: str    # 人类可读描述，如 "函数 create_user 已在 users/service.py:45 定义"
    suggestion: str | None = None  # 建议修复方案

class FrameworkFitReport(BaseModel):
    blockings: list[FrameworkIssue] = []   # 🔴 阻塞——必须修复
    warnings: list[FrameworkIssue] = []    # ⚠️ 标记——人类审查确认
    infos: list[FrameworkIssue] = []       # ℹ️ 提示
```

**门禁集成**：循环依赖 → 阻塞，其余 → 标记在 TestRunResult 中，摘要卡片展示：

```
┌─ 📋 测试摘要 ─────────────────────────────────┐
│ ✓ 12 passed   ✗ 0 failed   ○ 2 skipped       │
│ ⚠️ 2 framework warnings                       │  ← 新增
│   - users.py:32 函数名 create_user 已存在      │
│   - users.py:78 API 层直接调用 ORM (跨层)      │
│ ████████████████████████░░░ 89% coverage       │
│ [查看详情]                                      │
└────────────────────────────────────────────────┘
```

### 5.5 测试与审查的协同模型（`testing/reporter.py` → CrossReport）

**前提**：测试 Agent 和审查 Agent 同时启动、并行执行。如果不交换信息，只是两份独立报告——1+1=2。定义它们的**信息交换协议**，形成 1+1>2。

#### 5.5a 互补盲区

```
测试 Agent 看得到              审查 Agent 看得到
─────────────────────          ─────────────────────
代码跑不跑得通                  架构是否符合项目模式
边界 case 覆盖率                命名是否符合约定
变异体杀不杀得死                有没有重复造轮子
循环依赖有没有                  是否过早抽象/过度抽象
                               安全漏洞/硬编码密钥
                               方案是否偏离 PRD

测试 Agent 看不到的              审查 Agent 看不到的
─────────────────────          ─────────────────────
架构是否合理                    运行时是否正确
命名是否好                       边界 case 是否全
模式是否一致                     变异体是否被杀
                               循环依赖（如果只是静态读代码）
```

#### 5.5b 信息交换协议

```
1. 测试 → 审查（测试先完成时）
   测试结果中的关键发现推送给审查 Agent：
   - 覆盖率低的分支 → 审查重点审视那段代码逻辑
   - 存活的变异体位置 → 审查检查是否有逻辑弱点
   - 循环依赖 → 审查确认是否需要重构

2. 审查 → 测试（审查先完成时）
   审查发现推送给测试 Agent：
   - "函数与已有 xxx 重复" → 测试对两个函数各跑一轮，验证行为是否等价
   - "缺少空值处理" → 测试自动生成 null-input 用例验证
   - "跨层调用" → 测试加架构规则验证（分层隔离）
   - "使用过时 util" → 测试对新/旧 util 各跑一轮，量化差异

3. 合并 → CrossReport
   两份结果合并 + 交叉验证 → 一份统一报告 → 人类只看一张卡片
```

#### 5.5c 协同效果（1+1>2 的具体场景）

| 场景 | 测试发现 | 审查发现 | 协同效果 |
|------|---------|---------|---------|
| 审查指路，测试验证 | — | "这段代码用了过时 util" | 测试对新/旧 util 各跑一轮 → 量化差异 → 审查结论有数据支撑 |
| 测试指路，审查深挖 | "分支 3 覆盖率 0%" | 重点审查那个分支 → 发现逻辑永远不成立 | 测试发现盲区，审查定位根因 |
| 分歧→升级人类 | 测试通过 ✓ | 审查拒绝 ✗（命名不规范） | 合并报告标注分歧点 → 人类只看这一处 |
| 一致→降低审查强度 | 全部通过 + 95% | 审查无警告 | 摘要卡片绿色 → 人类秒过 |
| 审查触发补测试 | — | "此函数缺少空值处理" | 测试自动生成 null-input 用例 → 验证审查怀疑 |
| 去重验证 | — | "与已有 xxx 重复" | 测试两函数各跑一轮 → 行为等价？→ 建议合并/保留 |

#### 5.5d Pydantic 模型

```python
# testing/reporter.py —— CrossReport 数据模型

class CrossReport(BaseModel):
    """测试 + 审查的合并报告——人类只看这一份"""
    test_result: TestRunResult
    review_result: ReviewResult  # 来自 review/ 模块
    cross_validations: list[CrossValidation] = []
    consensus: str  # "aligned" | "divergent" | "test_only" | "review_only"
    divergent_points: list[DivergentPoint] = []

class CrossValidation(BaseModel):
    """一条交叉验证——测试和审查在同一代码点上的结论"""
    target: str  # 如 "users.py:45::create_user"
    test_says: str  # 测试的发现（"passed, coverage 100%" / "branch 3 uncovered"）
    review_says: str  # 审查的发现（"LGTM" / "建议合并到已有函数"）
    aligned: bool  # 一致？分歧？

class DivergentPoint(BaseModel):
    """分歧——人类必须决策"""
    target: str
    test_verdict: str   # "PASSED"
    review_verdict: str  # "WARNING" | "REJECTED"
    review_reason: str  # 审查为什么拒绝/警告
    suggestion: str     # Agent 的建议解决方案
```

#### 5.5e 对人类 UX 的影响

```
一致场景（预计 80%+）:
  ┌─ 📋 质量报告 ─────────────────────────────────────────┐
  │ 🧪 ✓12 ✗0 89%  🔍 ✓ 0 issues          🟢 一致        │
  │ 测试与审查结论一致 ✓                                   │
  │ [通过]                                                 │
  └────────────────────────────────────────────────────────┘
  → 人类扫一眼（1 秒），点 [通过]

分歧场景（预计 <20%）:
  ┌─ 📋 质量报告 ─────────────────────────────────────────┐
  │ 🧪 ✓12 ✗0 89%  🔍 ⚠2 issues          🟡 1 处分歧     │
  │ ⚡ 以下需要你决策：                                     │
  │                                                       │
  │ users.py:45 create_user()                             │
  │ 🧪 测试: ✓ 通过, 覆盖率 100%                          │
  │ 🔍 审查: ⚠ 建议合并到已有 create_user (utils.py:32)   │
  │                                                       │
  │ [采纳审查建议] [保留新实现] [查看代码对比]              │
  └────────────────────────────────────────────────────────┘
  → 人类只看分歧点，做决策，其余自动通过
```

```python
# testing/orchestrator.py —— 协同调用
class TestOrchestrator:
    async def run_with_review(self, code, goal_id) -> CrossReport:
        # 并行启动测试和审查
        test_task = asyncio.create_task(self.run_test_cycle(code, goal_id))
        review_task = asyncio.create_task(self.review_service.review(code, goal_id))
        
        test_result, review_result = await asyncio.gather(test_task, review_task)
        
        # 交叉信号推送（不阻塞主流程）
        await self._push_signals(test_result, review_result)
        
        # 合并报告
        cross = CrossReporter.merge(test_result, review_result)
        
        # 如果一致 → 单张绿色卡片
        # 如果分歧 → 黄色卡片 + divergent_points
        return cross
```

---

### 6.1 新增任务类型

```python
# scheduler/models.py —— 新增枚举值
class TaskType(str, Enum):
    # ... 已有 ...
    TEST_RUN = "test_run"          # 新：测试执行任务
    TEST_REPAIR = "test_repair"    # 新：测试失败修复任务
```

### 6.2 状态转换路径

```
PENDING → RUNNING → DONE     # 测试通过
PENDING → RUNNING → FAILED   # 修复 3 轮仍失败
PENDING → RUNNING → SUPPLEMENT → RUNNING → DONE  # 补测试 → 重跑通过
```

不新增状态枚举值，复用现有 `PENDING/RUNNING/DONE/FAILED`。`SUPPLEMENT` 是门禁决策，不是调度器状态。

### 6.3 检查点策略

- 测试执行前 `checkpoint.save(task_id)` ——失败可回滚到测试前状态
- 修复循环中每轮开始前保存检查点（防止修复越修越坏）
- 测试通过后清理检查点

---

## 七、防幻觉层影响

### 7.1 哪些层受影响

| 层 | 影响 | 处理 |
|----|------|------|
| L1 静态校验 | 生成的测试代码通过 JSON Schema 校验结构 | 测试代码是 Python，不做 JSON Schema 校验——用 AST parse 替代 |
| L2 动态追踪 | 测试代码引用被测模块的函数/类——检测命名幻觉 | 调用 code_graph.exists() 验证符号存在 |
| L4 类型检查 | 测试代码的 mypy 类型一致性 | 对生成的测试代码跑 mypy --check-untyped-defs |
| L7 沙箱执行 | 测试代码在 Docker 内跑——防止恶意代码 | sandbox/ 已有隔离机制 |

### 7.2 测试代码专用验证规则

```
新增规则（testing/ 专用，不影响其他代码）:
1. 测试代码不得 import 被测模块以外的 Orbit 内部模块
   → 防止测试过度耦合（测试只能测它声明的目标）
2. 测试代码不得包含 os.system / subprocess / eval / exec
   → L7 沙箱已有拦截，但 L1 提前过滤减少沙箱调用
3. 测试代码的函数名必须以 test_ 开头
   → pytest 收集规则，不满足则无法被收集执行
```

### 7.3 误报/漏报风险

| 风险 | 场景 | 缓解 |
|------|------|------|
| 误报 | 合法测试需要 import 辅助模块（如 pytest-mock） | 白名单：pytest、unittest.mock、pytest_asyncio |
| 漏报 | 测试代码调用被测代码内部未导出的私有函数 | L2 动态追踪在运行时检测（沙箱执行时发现 ImportError） |

---

## 八、图谱 Schema 变更

### 8.1 无变更

testing/ 模块**不修改 CodeGraph SQLite 表结构**。现有 `code_nodes` 和 `code_edges` 表已经包含函数调用关系，足以支撑 RTS 的依赖查询。

### 8.2 查询接口复用

```
RTS 使用的现有查询:
├── code_graph.get_callers(symbol_name)  → 谁调用了这个函数
├── code_graph.get_callees(symbol_name)  → 这个函数调用了谁
└── code_graph.get_all_nodes()           → 按模块过滤

新功能使用现有接口，不新增查询。
```

---

## 九、边界 Case 清单（硬性验收——阶段 4 测试据此逐项核对）

| # | 场景 | 预期行为 | 触发条件 |
|---|------|---------|---------|
| C1 | 沙箱不可用（Docker 未启动） | 回退本地 pytest + 日志警告 | Docker daemon 不可达 |
| C2 | 知识图谱为空（首次运行） | 跳过知识检索，只用代码图谱 CFG | knowledge.db 无匹配记录 |
| C3 | 代码图谱未构建 | 回退纯 LLM 意图驱动生成，标注"无 CFG 增强" | code_graph.build_index() 未调用过 |
| C4 | 生成的测试代码有语法错误 | 计数为 gen_failure → 重试 2 次 → HUMAN_NEEDED | LLM 输出非合法 Python |
| C5 | 测试执行超时（>5 分钟） | 熔断，返回已有结果 + `timeout: true` 标记 | 死循环/无限等待 |
| C6 | 并发触发同一模块 | file-level lock（`asyncio.Lock` 按模块名），后到排队 | 两次快速连续请求 |
| C7 | 生成的测试含恶意代码 | L1 AST 预检 + L7 沙箱执行拦截 → `security_alert` | os.system/rm -rf 等模式 |
| C8 | 人类审查拒绝 Agent 通过的代码 | 拒绝原因入库 knowledge/ → 增强门禁 | 阶段 3b 审查拒绝 |
| C9 | AB 测试分数相同 | 选用成本低的策略（意图驱动 < 路径敏感） | 两种策略 mutation_score 相同 |
| C10 | coverage.json 不存在 | 初始化为空 dict，逐步累积 | 首次运行无历史数据 |
| C11 | 被测代码为空（0 行） | 跳过测试生成，返回 N/A | 删除操作后只剩空文件 |
| C12 | 被测代码只有 import 行 | 生成测试验证 import 是否成功即可 | 新文件——只有骨架 |
| C13 | 生成测试过程中 LLM API 超时 | gateway 重试 2 次 → 仍失败 → 标记 GATEWAY_FAILED | LLM provider 不可用 |
| C14 | 修复循环中覆盖率反而下降 | 回滚到修复前检查点，停止修复，通知人类 | 修复引入更多问题 |
| C15 | 新代码引入循环依赖（A import B, B import A） | 🔴 阻塞门禁，返回完整 import 链，Agent 必须修复后才能进入沙箱执行 | `code_graph` 检测到环 |
| C16 | 新代码跨层调用（API 路由直接写 SQL） | ⚠️ 警告标记，不阻塞——摘要在卡片中展示，人类审查时确认 | 架构规则匹配命中 |

---

## 十、风险与缓解

| # | 风险 | 严重度 | 缓解措施 |
|---|------|--------|---------|
| R1 | **LLM 生成低质量测试**——测试通过但不测真正重要的路径（"测试即演示"问题） | 高 | 变异测试验证测试质量（mutation score）；AB 对比选优；知识图谱历史模式注入 |
| R2 | **修复循环无限期**——Agent 反复修反复失败，耗尽 Token | 中 | 硬上限 3 轮 + Token 预算追踪（复用 `resource_guard/`）+ 超时熔断 |
| R3 | **测试执行拖慢 Agent 响应**——用户等 30 秒才能看到 diff | 中 | 秒级层异步执行，先展示 diff 骨架（代码片段）+ "测试运行中..."，结果以增量消息推送 |
| R4 | **沙箱资源竞争**——多个 Agent 同时跑测试抢 Docker 资源 | 低 | 沙箱执行串行化（单模块锁），测试生成可并行 |
| R5 | **知识图谱噪声**——失败模式积累过多低质量条目，影响后续 Prompt 质量 | 低 | 失败模式去重 + 频率阈值（同模式出现 ≥2 次才注入 Prompt）+ 定期清理 |

---

## 十一、依赖链

```
testing/ 调用链（全部已有模块，零新依赖）:

testing/orchestrator.py
├── orbit.goal         → GoalSession (获取 PRD 文本)
├── orbit.knowledge    → 查询历史模式 + AB 结果
├── orbit.graph        → code_graph.get_callers/get_callees (RTS) + exists (冗余检查) + get_all_edges (循环依赖)
├── orbit.sandbox      → process_sandbox.run (测试执行)
├── orbit.checkpoint   → manager.save/load (检查点)
├── orbit.hallucination → L1-L9 pipeline (测试代码验证)
├── orbit.review       → 代码审查 Agent (并行启动, CrossReport 合并)
├── orbit.gateway      → LLM 调用 (生成测试/修复代码)
├── orbit.observability → audit/feedback (审计 + 反馈)
├── orbit.evolution    → prompt 进化通知
└── orbit.resource_guard → Token 预算追踪

外部 Python 依赖:
├── pytest (已有) — 测试框架
├── pytest-cov (已有) — 覆盖率
├── pytest-xdist (已有) — 并行
├── mutmut (Phase 2 新增) — 变异测试 ← 需加 pyproject.toml
└── hypothesis (Phase 2 新增) — 属性测试 ← 需加 pyproject.toml
```

---

## 十二、方案决策记录

| 决策 | 选择 | 替代方案及拒绝理由 |
|------|------|-------------------|
| 持久化方式 | 复用 knowledge/ 知识图谱 | 新建表：增加 schema 变更风险，测试结果大部分瞬态不需要持久化 |
| 测试执行位置 | sandbox/ Docker 隔离 | 本地 pytest：安全风险（生成代码可能恶意），已有 L7 机制不重复造轮子 |
| RTS 依赖分析 | 复用 code_graph | 文件 mtime 对比：不精确——改了 import 不影响下游时不该重跑 |
| 人类报告形式 | 聊天流内嵌卡片 | 新面板/新页面：UX 负担，用户已有心智模型（跟 diff 一样看） |
| 修复循环上限 | 硬上限 3 轮 | 动态上限（根据复杂度调整）：过度设计，3 轮够覆盖 88% 场景（TDFlow 数据） |
| 框架适配检查 | 自动化信号（测试给警告，人类做决策） | 完全交给代码审查：自动化检查零成本，标出来比人类逐行比对快 10 倍 |

---

*— 阶段 2 技术方案 · 2026-07-07 · 基于阶段 1 PRD（12 条验收标准全覆盖，无偏离）—*
*— 等待用户确认 —*
