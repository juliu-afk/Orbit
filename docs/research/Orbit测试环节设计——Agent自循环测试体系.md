# Orbit 测试环节设计 —— Agent 自循环测试体系

> 基于 [`测试设计V4.html`](测试设计V4.html) 工业级 AI-Native 测试工程报告 + 2025-2026 前沿研究 + Orbit 现有架构
> 目标：将测试从"人类驱动的阶段 4 门禁"升级为"Agent 内建质量闭环"

---

## 一、核心命题：Orbit 的测试环节解决什么问题

Orbit 是**多 Agent 软件开发自循环系统**。当前测试是**外部人类驱动**的（阶段 4 人类跑 pytest），不是 Agent 自循环的一环。

### 1.1 三个核心目标

| 目标 | 当前状态 | 目标状态 |
|------|---------|---------|
| **生成时引导** | Agent 生成代码后无测试信号驱动 | Agent 先生成测试意图 → 测试代码 → 实现代码（TDD 内循环） |
| **生成后验证** | 人类手动跑 pytest + CI 门禁 | Agent 自主执行测试套件、分析失败、迭代修复 |
| **持续反馈** | 失败信息不回流到 Agent | 失败模式 → 知识图谱沉淀 → 后续生成策略优化 |

### 1.2 设计原则

- **测试即规格** — 测试用例是 Agent 可执行的需求规格，不是事后检验
- **双 Agent 架构** — Generator + Verifier 独立角色，对抗性验证（参考 Replit Agent 3、ASEA-X）
- **失败即信号** — 测试失败直接驱动 Agent 的修复迭代，不是阻塞人类审批
- **内建闭环** — 测试不是"阶段 4"，而是贯穿 Agent 全生命周期的持续活动

---

## 二、Orbit 测试现状与缺口

### 2.1 已有资产

| 维度 | 现状 |
|------|------|
| 测试文件 | unit 203 + integration 10 + e2e 8 + perf 5 + chaos 2 + lib 40 = **~270 文件** |
| 测试 lib | factories / builders / mocks / assertions / scenarios 五层测试基建 |
| 测试设计 | `05-测试体系.md`：10 维度 × 200+ 场景 |
| 覆盖率 | 行 75% / 分支 60% / 综合 72%，冲刺 80% |
| CI 门禁 | pytest + coverage + semgrep + bandit + gitleaks |

### 2.2 缺口

| # | 缺口 | 影响 |
|---|------|------|
| 1 | **测试环节未集成到 Agent 工作流** | Agent 生成代码后不会自己跑测试、不会根据失败修复 |
| 2 | **无 Agent 行为测试 (L4)** | 无法自动发现 Agent 的弱点——对话质量、任务分解、模式选择 |
| 3 | **无属性测试 (L5/PBT)** | 只验证具体输入输出，不验证程序不变量 |
| 4 | **无测试生成模块** | Agent 不会自动为新代码生成测试，依赖人类手写 |
| 5 | **无智能测试选择 (RTS)** | 每次跑全量，45 模块改一行也要全跑 |
| 6 | **失败不回流** | 测试失败后 Agent 不学习，下次犯同样错误 |
| 7 | **测试与 Agent 能力脱节** | 防幻觉 L1-L9、沙箱、合规验证已有，但未被测试流程编排使用 |
| 8 | **无 AB 测试体系** | 已有 `tests/ab/` 骨架但仅覆盖减熵策略——缺乏策略/模型/Prompt 多层 AB 对比，无法自动选择最优方案 |

---

## 三、测试环节在 Agent 工作流中的定位

### 3.1 从"阶段 4 外部门禁"到"五阶段内循环"

```
当前（人类驱动）:
  Agent 生成代码 → 人类审查 → 人类跑 pytest → 人类修 bug → 合并

目标（Agent 自循环）:
  ┌─────────────────────────────────────────────────────┐
  │  Agent 内循环                                        │
  │  ┌──────────┐   ┌──────────┐   ┌──────────┐        │
  │  │ 意图理解  │ → │ 测试生成  │ → │ 代码生成  │        │
  │  │(Test      │   │(Gen       │   │(TDD       │        │
  │  │ Intention)│   │ Strategy) │   │ Generate) │        │
  │  └──────────┘   └──────────┘   └──────────┘        │
  │       ↑                              ↓              │
  │  ┌──────────┐                 ┌──────────┐         │
  │  │ 反馈学习  │ ←────────────── │ 验证执行  │         │
  │  │(Feedback  │   失败/覆盖率   │(Execute   │         │
  │  │ Loop)     │   回灌          │ + Verify) │         │
  │  └──────────┘                 └──────────┘         │
  └─────────────────────────────────────────────────────┘
                           ↓ 通过门禁
                    人类审查 → 合并
```

### 3.2 对应 Orbit 现有模块映射

| 内循环阶段 | 对应 Orbit 模块 | 说明 |
|-----------|----------------|------|
| 意图理解 | `goal/` + `clarifier/` | Goal 解析出测试意图，Clarifier 澄清歧义 |
| 测试生成 | **新模块 `testing/`** | 编排测试生成策略（见 §五） |
| 代码生成 | `agents/` + `prompt/` | 现有代码生成 Agent + TDD Prompt 注入 |
| 验证执行 | `sandbox/` + `hallucination/` + `compliance/` + `review/` | 沙箱隔离执行 + 9 层防幻觉 + 合规 + 代码审查 |
| 反馈学习 | `observability/` + `knowledge/` + `evolution/` | 失败模式入库 + 知识图谱更新 + Prompt 进化 |

---

## 四、五层测试架构（适配 Orbit）

### 4.1 架构总览

```
┌──────────────────────────────────────────────────┐
│  L5  反馈闭环层                                   │
│  observability/feedback → knowledge/ → evolution/ │
│  失败模式 → 知识图谱 → 后续生成策略优化            │
├──────────────────────────────────────────────────┤
│  L4  编排执行层                                   │
│  新 testing/ 模块：协调整体测试流程                 │
│  Sandbox(Docker) + pytest/vitest/Playwright       │
├──────────────────────────────────────────────────┤
│  L3  多验证器协作层                                │
│  hallucination/L1-L9 + compliance/ + review/       │
│  sandbox/ 隔离执行 + checkpoint/ 回滚              │
├──────────────────────────────────────────────────┤
│  L2  知识检索层                                   │
│  knowledge/ 知识图谱：历史用例 + 缺陷模式 + 业务规则 │
│  graph/ 代码图谱：AST/CFG 静态分析                  │
├──────────────────────────────────────────────────┤
│  L1  意图理解层                                   │
│  goal/ + modes/ + clarifier/                      │
│  PRD → 验收标准 → 测试意图 (Test Intention)        │
└──────────────────────────────────────────────────┘
```

### 4.2 各层详解

#### L1 · 意图理解层

**输入**：PRD / User Story / API 契约 / 验收标准
**处理**：
- Goal 模块解析需求 → 提取可测试的验收条件
- Clarifier 对歧义需求主动澄清（如"这个字段允许空值吗？"）
- Modes 模块根据任务复杂度选择测试深度（简单 CRUD → 轻量 / 核心调度器 → 全量）

**输出**：结构化的 Test Intention（测试意图）
```python
# 示例：提取出的 Test Intention
{
    "target": "scheduler/state_machine.py::transition()",
    "positive": ["valid_state_A_to_B", "valid_state_B_to_C"],
    "negative": ["invalid_jump_A_to_C", "null_context"],
    "invariants": ["total_tasks == len(tasks)"],
    "edge_cases": ["concurrent_transition", "rollback_during_transition"]
}
```

**参考依据**：IntUT 框架——显式测试意图可提升分支覆盖 94%

#### L2 · 知识检索层

**输入**：Test Intention
**处理**：
- 知识图谱检索历史相似场景的测试用例、已知缺陷模式
- 代码图谱 (Tree-sitter) 提取目标代码的 AST/CFG/数据流
- 混合检索：BGE 语义搜索 + TF-IDF 关键词降级

**输出**：上下文增强的 Test Plan
- 已有的相关测试（避免重复生成）
- 该模块的历史缺陷模式（高频错误类型）
- 代码复杂度指标（圈复杂度 → 需要的测试密度）

**参考依据**：ATA 框架——通过知识图谱检索历史用例和缺陷模式

#### L3 · 多验证器协作层

**输入**：生成的测试代码 + 被测代码
**处理**（并行执行）：

| 验证器 | 对应 Orbit 模块 | 验证内容 |
|--------|----------------|---------|
| 编译验证 | — (pytest 收集阶段) | 测试代码能否编译/导入 |
| 静态分析 | L1 静态校验 | JSON Schema / AST 结构合规 |
| 动态追踪 | L2 动态追踪 | 命名幻觉（引用不存在符号） |
| 类型检查 | L4 类型检查 | mypy 类型一致性 |
| 形式化验证 | L5 Z3 | 核心算法不变量 |
| 合约验证 | L6 合约验证 | 前置/后置条件 |
| 沙箱执行 | L7 沙箱 | 隔离执行，检测恶意代码 |
| 合规验证 | L9 动态合规 | 法规/标准符合性 |
| 代码审查 | review/ | 代码质量、方案偏差 |

**输出**：多维度验证报告（每层通过/失败 + 具体违规位置）

**参考依据**：ScenGen 五智能体协作（观察者→决策者→执行者→监督者→记录者）

#### L4 · 编排执行层（新 `testing/` 模块）

这是本次设计的**核心新增模块**，负责协调整个测试流程。

**职责**：
1. 接收 L1 的 Test Intention + L2 的 Test Plan
2. 选择合适的测试生成策略（见 §五）
3. 调度 L3 的验证器
4. 收集结果 → 判定门禁 → 触发修复循环或通过
5. 将结果回灌给 L5

**不负责**（由现有模块负责）：
- 实际代码执行 → sandbox/
- 实际 LLM 调用 → gateway/
- 检查点管理 → checkpoint/

#### L5 · 反馈闭环层

**输入**：L4 的测试结果（通过/失败/覆盖率/存活变异体）
**处理**：
- `observability/feedback` 收集失败模式
- `knowledge/` 入库：相似场景 → 常见缺陷 → 测试模板
- `evolution/` 更新 Prompt 策略（如"该模块空指针高频 → 生成代码时加强空检查提示"）
- `metacognition/` 元认知监控：Agent 是否在重复相同错误？

**输出**：后续任务的知识增强

**参考依据**：ATA 自适应测试——LLM-as-a-Judge 评分 → 调整测试难度

---

## 五、测试生成策略（L4 的核心决策）

### 5.1 四种策略及 Orbit 实现映射

| 策略 | 原理 | Orbit 实现 |
|------|------|-----------|
| **路径敏感生成** | 静态分析提取 CFG → 引导 LLM 覆盖深层路径 | `graph/code_graph.py` 提取 CFG → 注入 Prompt |
| **变异引导生成** | 运行变异测试 → 识别存活变异体 → 针对性补充 | `testing/` 调用 `mutmut` → 分析存活变异体 → 生成杀死用例 |
| **意图驱动生成** | 显式告诉 LLM 测试意图（不隐式推测） | L1 输出的 Test Intention → Prompt 显式字段 |
| **属性测试生成** | 提取程序不变量 → 生成 PBT | `testing/` 从代码/文档提取不变量 → Hypothesis 框架生成 |

### 5.2 策略选择决策树

```
被测代码类型？
├── 纯函数/工具函数 → 路径敏感 + 属性测试
├── API 端点 → 意图驱动 + 契约测试（从 OpenAPI 推导）
├── 状态机/调度器 → 路径敏感（全状态转换路径）+ 属性测试（不变量）
├── LLM 交互层 → 意图驱动 + Agent 行为测试（L4 新增）
└── UI 组件 → 意图驱动 + Playwright E2E 快照测试
```

### 5.3 Agent 行为测试（L4 新增——Orbit 最大增量）

这是参考文档 §二 定义的 L4 层，对 Orbit 是**全新测试类型**：

**测试对象**：Orbit 的 Agent 本身（而非 Agent 生成的代码）

**测试内容**：
| 维度 | 测试方法 | 通过标准 |
|------|---------|---------|
| 任务分解质量 | 给定 Goal → 检查 Task DAG 是否合理 | 无循环依赖、无遗漏子任务 |
| 澄清能力 | 给定模糊需求 → Agent 是否主动提问 | 3 轮内澄清完成 ≥80% |
| 模式选择 | 给定任务 → 选择的 architect/clarify/review 模式是否正确 | 准确率 ≥85% |
| 代码生成质量 | 生成代码 → 编译通过率 | ≥90% |
| 自修复能力 | 生成代码失败 → Agent 修复成功率 | ≥70%（3 次内） |
| 幻觉率 | 引用不存在符号/API/文件 | ≤5% |

**实现方式**：
- 利用 ATA 框架模式——元 Agent 自动测试对话式 Agent
- 利用 Orbit 自己的 `metacognition/` 模块监控 Agent 行为
- 利用 `observability/traces` 收集 Agent 轨迹 → 分析失败模式

### 5.4 AB 测试 —— 策略/模型/Prompt 四层对比（为 Agent 自动选择最优方案）

Orbit 已有 `tests/ab/test_entropy_ab.py`（减熵策略效果对比），但仅覆盖单一场景。AB 测试在 Agent 自循环体系里有**四个层次**，从秒级到月级：

| 层级 | 对照组 | 实验组 | 触发时机 | 成本 | 目的 |
|------|--------|--------|---------|------|------|
| **L1 策略 AB** | 策略 A（路径敏感） | 策略 B（意图驱动） | 两种策略都适用时（~30% 场景） | +10-20 秒 | 同段代码哪种策略杀更多变异体 |
| **L2 模型 AB** | T3 模型（便宜） | T2 模型（贵） | 核心模块变动时 | 秒-分钟级 | 比代码质量/幻觉率/Token 消耗/成本 |
| **L3 Prompt AB** | Prompt 版本 A | Prompt 版本 B | `evolution/` 调整 Prompt 时 | 分钟级 | 比生成代码的编译通过率+测试通过率 |
| **L4 分支 AB** | feature 分支 A | feature 分支 B | 人工触发 | 小时级 | 两个实现方案全量回归对比（传统 AB） |

**核心决策**：L1 策略 AB 结果沉淀到 `knowledge/`，记录"模块 X → 最优策略 Y"。后续同类模块直接用胜者策略，不重复 AB——**一次成本，长期收益**。

**实现**：`testing/strategies/ab_runner.py`

```python
# AB 策略选择器
class ABRunner:
    async def compare_strategies(self, code, intention) -> StrategyResult:
        # 并行跑两种策略
        result_a, result_b = await asyncio.gather(
            self.path_sensitive.generate(code, intention),
            self.intention_driven.generate(code, intention),
        )
        # 跑变异测试 → 比较 mutation_score
        score_a = await self.run_mutation_test(result_a.tests, code)
        score_b = await self.run_mutation_test(result_b.tests, code)
        # 胜者入库
        winner = result_a if score_a > score_b else result_b
        await self.knowledge.record_ab_result(
            module=code.module,
            winner=winner.strategy_name,
            scores=(score_a, score_b),
        )
        return winner
```

**不每次跑的场景**：
- 只有一种策略适用 → 跳过 AB
- knowledge/ 已有该模块历史 AB 结果且胜率差距 >20% → 直接用历史胜者
- 简单 CRUD / 字段变更（圈复杂度 <3）→ 跳过 AB，默认意图驱动

---

## 六、质量门禁体系

### 6.1 分层门禁

```
代码级（每次 Agent 生成后自动）
├── 编译门禁：生成的测试代码编译通过
├── 覆盖率门禁：分支覆盖 ≥80%
├── 变异评分门禁：Mutation Score ≥70%
└── 静态分析门禁：无 Critical 漏洞

模块级（PR 前）
├── 单元测试全绿
├── 集成测试全绿
├── 新代码有对应测试（强制）
└── 回归测试通过（核心模块变动时）

系统级（合并前）
├── E2E 冒烟 5 场景全绿
├── 全量回归 19+ 场景全绿
├── 安全扫描通过（semgrep + bandit + gitleaks）
└── 性能无退化

发布级（Tag 前）
├── 混沌实验通过率 ≥90%
├── 7×24 小时稳定性测试通过
└── AI 质量评分 ≥85/100
```

### 6.2 Agent 自主判定

```python
# testing/gate.py —— Agent 内循环的门禁判定
class QualityGate:
    def evaluate(self, result: TestResult) -> GateDecision:
        if not result.compiled:
            return GateDecision.FAILED  # 编译失败 → 直接修复
        if result.branch_coverage < 0.80:
            return GateDecision.SUPPLEMENT  # 覆盖率不足 → 补测试
        if result.mutation_score < 0.70:
            return GateDecision.SUPPLEMENT  # 变异体存活 → 补测试
        if result.critical_vulnerabilities > 0:
            return GateDecision.FAILED  # 安全问题 → 直接修复
        return GateDecision.PASSED
```

---

## 七、加速策略（适配 Orbit 45 模块规模）

### 7.1 四层加速

| 层 | 策略 | Orbit 实现 | 预期收益 |
|----|------|-----------|---------|
| L1 左移 | 测试在 Agent 生成代码时同步生成 | 意图驱动——Test Intention → 测试代码 → 实现代码 | 缺陷发现提前到生成阶段 |
| L2 智能选择 | 只跑受变更影响的测试 | `graph/code_graph.py` 计算依赖 → 只跑受影响模块 | 减少 60-80% 测试时间 |
| L3 并行执行 | 分片并行 | `pytest-xdist` + 多核并行 + 按模块分片 | 全量回归 ≤5 分钟 |
| L4 AI 生成 | Agent 自动生成测试 | 本节设计的 testing/ 模块 | 节省人类 30-40% 测试编写时间 |

### 7.2 RTS（Regression Test Selection）——L2 智能选择的核心

```
改动文件 → 代码图谱查询受影响模块 → 只跑这些模块的测试

示例：
  改了 scheduler/state_machine.py
  → 代码图谱查询：哪些模块 import 了 state_machine？
  → 结果：scheduler/*, checkpoint/*, loop/*
  → 只跑 tests/unit/test_scheduler.py, test_checkpoint.py, test_loop*.py
  → 跳过其余 180+ 与本次改动无关的测试文件
```

---

## 八、新增模块设计：`src/orbit/testing/`

### 8.1 模块结构

```
src/orbit/testing/
├── __init__.py
├── orchestrator.py        # 测试流程编排器——L4 核心
├── intention.py           # 从 Goal/PRD 提取 Test Intention —— L1
├── strategies/
│   ├── __init__.py
│   ├── path_sensitive.py  # 路径敏感生成（依赖 code_graph）
│   ├── mutation_guided.py # 变异引导生成（调用 mutmut）
│   ├── intention_driven.py# 意图驱动生成
│   ├── property_based.py  # 属性测试生成（Hypothesis）
│   └── ab_runner.py       # AB 对比——策略/模型/Prompt 四层对比
├── gate.py                # 质量门禁判定
├── rts.py                 # 智能测试选择（依赖 code_graph）
├── agent_behavior.py      # Agent 行为测试 —— L4 新增测试类型
└── feedback.py            # 失败模式 → knowledge/ 回灌
```

### 8.2 与现有模块的关系

```
testing/orchestrator.py
  ├── 调用 goal/           → 解析任务目标
  ├── 调用 knowledge/      → 检索历史用例 + 缺陷模式
  ├── 调用 graph/          → 提取 CFG + 依赖分析
  ├── 调用 sandbox/        → 隔离执行测试
  ├── 调用 hallucination/  → L1-L9 验证生成的测试
  ├── 调用 compliance/     → L9 合规验证
  ├── 调用 review/         → 代码审查
  ├── 调用 observability/  → 收集轨迹 + 反馈
  ├── 调用 checkpoint/     → 测试前保存检查点
  └── 调用 evolution/      → 失败模式 → Prompt 进化
```

### 8.3 Orchestrator 核心流程

```python
# testing/orchestrator.py —— 伪代码
class TestOrchestrator:
    async def run(self, goal: Goal, code: GeneratedCode) -> TestCycleResult:
        # 1. 提取测试意图
        intention = await self.intention.extract(goal)
        
        # 2. 知识检索增强
        knowledge = await self.knowledge.search(intention)
        plan = TestPlan(intention=intention, knowledge=knowledge)
        
        # 3. 选择生成策略
        strategy = self.select_strategy(code)  # 见 §5.2 决策树
        
        # 4. 生成测试代码
        tests = await strategy.generate(plan, code, self.gateway)
        
        # 5. 沙箱执行
        result = await self.sandbox.execute(tests, code)
        
        # 6. 多验证器并行验证
        verdicts = await asyncio.gather(
            self.hallucination.verify(tests),   # L1-L9
            self.compliance.verify(tests),       # L9
            self.review.review(tests, code),     # code review
        )
        
        # 7. 变异测试（仅核心模块）
        if code.is_core_module:
            result.mutation_score = await self.run_mutation_test(tests, code)
        
        # 8. 门禁判定
        decision = self.gate.evaluate(result, verdicts)
        
        # 9. 反馈闭环
        await self.feedback.record(result, decision)
        
        # 10. 不通过 → 触发修复循环
        if decision == GateDecision.SUPPLEMENT:
            return await self.supplement_and_retry(tests, result, plan)
        elif decision == GateDecision.FAILED:
            return await self.fix_and_retry(code, result)
        
        return TestCycleResult(passed=True, result=result)
```

---

## 九、与 WORKFLOW.md 的集成

### 9.1 修改现有四阶段流程——测试生成前移

当前 WORKFLOW.md 的阶段 4（测试）是**人类手动执行**的。引入 testing/ 模块后，**测试生成贯穿全部阶段，测试执行由 Agent 自主完成**：

```
阶段 1 需求澄清 ──→ Agent 从 PRD 自动：
                    ├── 提取 Test Intention
                    ├── 从验收标准生成 Gherkin 场景骨架（E2E 骨架）
                    └── 标记 Non-Goals → 显式标注"不测什么"

阶段 2 技术方案 ──→ Agent 从技术方案自动：
                    ├── 从 API 设计生成契约测试骨架
                    ├── 从数据模型生成模型校验测试骨架
                    ├── 从调度器状态变更生成状态转换测试骨架
                    └── 生成 Test Plan（哪个模块用什么策略，测试密度分配）

阶段 3 编码实现 ──→ Agent TDD 循环（主战场）：
                    ├── 填充阶段1/2的测试骨架
                    ├── 生成单元测试代码 → 生成 PBT（条件触发）
                    ├── 生成实现代码（TDD——已有测试约束）
                    ├── 沙箱执行测试 → 失败 → 自修复（≤3 轮）
                    ├── AB 测试（条件触发）→ 记录最优策略
                    └── 通过 → 展示 diff（含测试结果摘要卡片）

阶段 3b 代码审查 ──→ 人类审查（不变）——但多了测试报告可参考

阶段 4 验证交付 ──→ Agent 跑全部门禁 → 人类验收（减负，不做手动测试）
```

### 9.1a 提前生成：阶段 1/2 的测试骨架（零成本左移）

**为什么提前**：PRD 和技术方案出来后，已知信息足够生成测试框架。空骨架提前暴露需求歧义——"这条验收标准没法转成测试场景" → 需求不清晰 → 回阶段 1 澄清，不用等到阶段 3 才发现。

**阶段 1 PRD 产出**：

| PRD 包含 | 自动生成的测试骨架 | 形式 |
|----------|-------------------|------|
| 验收标准列表 | Gherkin 场景骨架 | `.feature` 文件或 `test_e2e_skeleton_xxx.py` |
| 业务规则约束 | 边界值测试骨架（输入边界/状态边界） | `test_boundary_skeleton_xxx.py` |
| 用户故事（P0/P1/P2） | 优先级标签 → 测试密度分配 | Test Plan 元数据 |
| Non-Goals | 显式标注 `# NO-TEST: xxx` | 防止 Agent 过度测试 |

```gherkin
# 阶段1 自动产出：从 PRD 验收标准提取的 Gherkin 骨架
# docs/requirements/2026-07-07-测试模块/阶段1-测试骨架.feature
Feature: Agent 测试自循环
  Scenario Outline: 代码生成后自动跑测试    ← 从验收标准 "生成后立即执行单元测试" 提取
  Scenario Outline: 测试失败自修复           ← 从验收标准 "失败后 3 轮内自动修复" 提取
  Scenario Outline: 覆盖率不达标补测试       ← 从验收标准 "分支覆盖 ≥80%" 提取
```

**阶段 2 技术方案产出**：

| 技术方案包含 | 自动生成的测试骨架 | 形式 |
|-------------|-------------------|------|
| API 设计（端点/请求/响应/错误码） | 契约测试骨架（每个端点 + 每个错误码） | `test_contract_skeleton_xxx.py` |
| 数据模型（字段/类型/约束） | 模型校验测试骨架（必填/类型/长度/外键） | `test_validation_skeleton_xxx.py` |
| 调度器状态变更 | 状态转换测试骨架（正向 + 非法拦截） | `test_state_skeleton_xxx.py` |
| 防幻觉层影响 | 各层验证用例骨架（误报 + 漏报各一） | `test_hallucination_skeleton_xxx.py` |

```python
# 阶段2 自动产出：从 API 设计生成的契约测试骨架
# tests/integration/test_testing_api_skeleton.py
async def test_run_tests_200(): ...        # 正向：触发测试 → 返回结果
async def test_run_tests_422_no_code(): ... # 错误码：空代码体
async def test_run_tests_409_conflict(): ... # 边界：并发触发同一任务
```

**命名约定**：`test_*_skeleton_xxx.py` 标记骨架——阶段 3 Agent 知道这是待填充的，不是最终测试。

### 9.2 人类角色变化

| 当前 | 目标 |
|------|------|
| 人类写测试策略 | Agent 自动选择策略，人类审核 |
| 人类跑 pytest | Agent 自主跑，人类看报告 |
| 人类分析失败 | Agent 自动分析 + 修复，人类确认 |
| 人类判定门禁 | Agent 自动判定，人类处理阻塞 |

---

## 十、人类测试报告 —— 像 diff 一样展示，零 UX 负担

### 10.1 设计原则

- **复用现有 UI**：已有 `TestPanel.vue` + `MessageItem.vue` 的代码块展示模式，不新建面板
- **测试结果 = 聊天消息的一种段类型**（类似 ` ``` ` 代码块），内嵌在 Agent 回复里
- **默认折叠，按需展开**——摘要 2 秒扫一眼，有问题再展开，不刷屏
- **Agent 修复优先于人类阅读**——失败时 Agent 先自己修，修完再展示结果

### 10.2 三级展示

| 层级 | 展示内容 | 展示位置 | 人类交互 |
|------|---------|---------|---------|
| **L1 秒级摘要** | 通过/失败/跳过计数 + 覆盖率% + 耗时 | 聊天流内嵌卡片（默认可见） | 扫一眼（2 秒） |
| **L2 按需详情** | 逐用例状态 + 覆盖率缺口（文件:行号） + 存活变异体 | 抽屉展开（点击"查看详情"） | 定位问题代码 |
| **L3 趋势报告** | 本周覆盖率趋势 / 高频失败模块 / AB 策略胜率 | Dashboard（已有，不在此次范围） | 管理视角 |

### 10.3 聊天流内嵌展示

Agent 回复中，测试结果以卡片形式内嵌，跟代码块同级：

```
agent[developer]> 生成完成。测试结果 ↓

┌─ 📋 测试摘要 ──────────────────────────────┐
│ ✓ 12 passed   ✗ 0 failed   ○ 2 skipped    │
│ ████████████████████████░░░ 89% coverage    │
│ 🧬 72% mutation score                       │
│ ⏱ 3.2s total    [查看详情] [查看覆盖率缺口]  │
└────────────────────────────────────────────┘

agent[developer]> 代码 diff：

┌─ 📝 changes ───────────────────────────────┐
│ + def create_user(...)                      │
│ ...                                         │
└────────────────────────────────────────────┘
```

### 10.4 展开"查看详情"——抽屉面板

复用已有右侧面板区域（跟 CodeDiffPanel 同一位置），TestPanel 的完整模式：

```
┌─ 📋 测试结果 · 详情 ──────────────────────────┐
│ ✓ test_create_user_201              0.45s     │
│ ✓ test_create_user_422              0.12s     │
│ ○ test_update_user_batch   0.00s [跳过原因]   │
│                                                │
│ 📊 覆盖率                                      │
│ ████████████████████░░░░ 89% (112/126 分支)    │
│ 未覆盖: users.py:45 (email 空值分支)            │
│         users.py:78 (并发冲突回滚)              │
│                                                │
│ 🧬 变异评分                                    │
│ ██████████████████░░░░░░ 72% (18/25 杀灭)     │
│ 存活: users.py:32 (> 变 >=)                    │
│                                                │
│ 📐 AB 策略对比                                 │
│ 路径敏感: 76% │ 意图驱动: 72% → 本次选用前者    │
│                                                │
│ [📎 查看关联 diff] [🔄 补测试] [✅ 确认通过]    │
└────────────────────────────────────────────────┘
```

### 10.5 实现方式：复用现有组件，零新面板

**不改架构，加三样东西**：

1. **`MessageItem.vue`** — 新增 `type: 'test_result'` 消息段解析（类似现有的 `type: 'code'` 代码块解析）

```typescript
// MessageItem.vue —— 新增 test_result 段类型
interface Segment {
  type: 'text' | 'code' | 'test_result'
  content: string        // JSON 结构化测试结果
  collapsed: boolean     // 默认折叠为摘要，展开为详情
}
```

模板中 `type === 'test_result'` 时渲染 `<TestResultCard>`（内联组件），而非 `<pre>`。

2. **`TestPanel.vue`**（已有）——加 compact 模式 + 交互回调

```typescript
// TestPanel.vue —— 新增 props
defineProps<{
  compact?: boolean              // true = 摘要条（聊天内嵌），false = 完整面板（抽屉）
  result?: TestRunResult         // 外部传入结果，不传则从 API 拉
  onExpand?: () => void          // 点击展开 → emit 给父组件打开抽屉
  onFixTests?: (gaps: CoverageGap[]) => void  // 点击补测试 → Agent 触发
  onViewDiff?: (file: string) => void         // 点击关联 diff → 打开 Monaco
}>()
```

3. **`TestResultCard.vue`**（新增，~60 行）——聊天流内嵌的摘要卡片组件

```vue
<!-- TestResultCard.vue —— 聊天流内嵌摘要卡片 -->
<template>
  <div class="test-result-card" :class="{ collapsed }">
    <div class="trc-summary" @click="collapsed = !collapsed">
      <span class="trc-passed">✓ {{ result.passed }} passed</span>
      <span v-if="result.failed" class="trc-failed">✗ {{ result.failed }} failed</span>
      <span v-if="result.skipped" class="trc-skipped">○ {{ result.skipped }} skipped</span>
      <span class="trc-coverage">{{ result.coverage }}% coverage</span>
      <span class="trc-time">⏱ {{ result.duration }}s</span>
      <button class="trc-expand">{{ collapsed ? '展开' : '折叠' }}</button>
    </div>
    <div v-if="!collapsed" class="trc-detail">
      <!-- 逐用例列表 + 覆盖率缺口 + 操作按钮 -->
      <slot />
    </div>
  </div>
</template>
```

### 10.6 人类交互流全链路

```
Agent 生成代码 + 测试
  │
  ├──→ 聊天流出现测试摘要卡片（L1 摘要，2 秒扫视）
  │      ├── "12 passed 0 failed 89%" → 好，不展开，直接审 diff
  │      ├── "8 passed 4 failed"      → 展开看失败用例
  │      │    └── 点 [查看关联 diff] → Monaco 定位到问题代码
  │      │    └── 点 [让 Agent 修复]  → Agent 重新修 → 新卡片出现
  │      └── "coverage 56%"           → 展开看覆盖率缺口
  │           └── 点 [补测试]         → Agent 补 → 重跑 → 新卡片出现
  │
  └──→ 人类点 [确认通过]
         └── 测试结果 + diff 一起进入阶段 3b 审查
```

### 10.7 与已有 TestPanel 的关系

| 组件 | 位置 | 用途 | 改动 |
|------|------|------|------|
| `TestPanel.vue` | 编辑器右侧面板 | 手动触发测试、查看历史结果 | 加 `compact` 模式 + 回调 props |
| `TestResultCard.vue` | 聊天流 (`MessageItem` 内) | Agent 自动化测试结果摘要 | **新增** ~60 行 |
| `MessageItem.vue` | 聊天流 | 消息渲染 | 加 `test_result` 段类型解析，~20 行 |
| `CodeDiffPanel.vue` | 编辑器右侧抽屉 | 代码 diff 展示 | 不变 |

**总改动量**：3 个文件修改（~50 行）+ 1 个新文件（~60 行）= ~110 行前端代码。零新面板，零新路由。

---

## 十一、实施路线

### Phase 1：基础内循环（1-2 周）

| 任务 | 内容 |
|------|------|
| 创建 `testing/` 模块骨架 | orchestrator / intention / gate |
| 实现意图驱动生成 | goal/ → Test Intention → Prompt 注入 |
| 集成沙箱执行 | sandbox/ 跑生成的测试 |
| 基础门禁 | 编译 + 覆盖率判定 |

### Phase 2：策略增强（2-3 周）

| 任务 | 内容 |
|------|------|
| 路径敏感生成 | code_graph/ CFG → Prompt |
| RTS 智能选择 | code_graph/ 依赖分析 → 选择性执行 |
| 变异引导生成 | mutmut 集成 |

### Phase 3：闭环反馈（3-4 周）

| 任务 | 内容 |
|------|------|
| 失败模式入库 | observability/feedback → knowledge/ |
| Prompt 进化 | evolution/ 根据失败模式调整生成策略 |
| Agent 行为测试 | metacognition/ 监控 → 自动发现弱点 |

### Phase 4：生产化（4-6 周）

| 任务 | 内容 |
|------|------|
| 属性测试生成 | Hypothesis 集成 |
| 混沌测试编排 | chaos-mesh 集成到 Agent 内循环 |
| 多 Agent 协作测试 | compose/ 编排 Generator + Verifier 对抗 |

---

## 十二、参考文献

| # | 来源 | 核心贡献 | 对 Orbit 的启发 |
|---|------|---------|----------------|
| 1 | **测试设计V4.html**（本报告参考文献） | AI-Native 测试工程五层架构 + 四层加速 | 本文档的设计框架 |
| 2 | JUnitGenie (ASE 2025) | 路径敏感的 LLM 单元测试生成，分支覆盖 +29.6% | testing/strategies/path_sensitive.py |
| 3 | IntUT (ICSE 2025) | 意图驱动测试生成，分支覆盖 +94% | testing/intention.py |
| 4 | Meta ACH (FSE 2025) | 变异引导 LLM 测试生成，10,795 个类验证 | testing/strategies/mutation_guided.py |
| 5 | ATA (2025) | 元 Agent 自动测试对话式 Agent | testing/agent_behavior.py |
| 6 | ScenGen (arXiv 2025) | 五智能体协作 GUI 测试 | testing/orchestrator.py 的多验证器编排 |
| 7 | Google Speculative Testing (ICSE SEIP 2025) | ML 驱动测试调度，检测时间 -65% | testing/rts.py |
| 8 | TDFlow (EACL 2026) | 测试驱动 Agent 工作流，SWE-Bench 88.8% | TDD 内循环设计 |
| 9 | Replit Agent 3 (2026) | 双 Agent 架构 + REPL 自验证 | Generator + Verifier 双 Agent 模式 |
| 10 | coSTAR / Databricks (2026) | Agentic Judge + 双循环对齐 | gate.py 的门禁判定 + 人类 gold set 对齐 |
| 11 | RAMPART / Microsoft (2026) | CI 管道中的 Agent 安全回归测试 | 安全门禁的 CI 集成 |
| 12 | TestSprite CLI (2026) | Agent 自验证 + 建议修复 + 重跑循环 | orchestrator.py 的修复循环设计 |

---

> **结论**：Orbit 的测试环节不应是"人类驱动的外部门禁"，而应是 **Agent 自循环的内建质量闭环**。
> 新增 `testing/` 模块作为编排核心，复用 Orbit 已有的 45 个模块能力（防幻觉、沙箱、合规、审查、知识图谱、代码图谱），
> 实现"意图理解 → 测试生成 → 代码生成 → 沙箱执行 → 多验证器验证 → 反馈闭环"的完整内循环。
> 人类从"测试执行者"变为"测试审核者"——Agent 跑测试、Agent 修 bug、人类确认。
