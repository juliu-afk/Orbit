# 阶段1-PRD-Grill交互协议层.md

> 基于 `docs/research/grill-ecosystem-deconstruction.html`（2026-07-06）
> 研究范围：grill-me / grill-with-docs / drill-me / mattpocock/skills 仓库架构

## 一、问题陈述

### 当前状态

Orbit 基础设施层已做到极致——37 个 Python 包、8 层防幻觉、6 种图谱、毫秒级熔断。
但 **交互协议层**存在空白：

1. **Agent 行为硬编码在 Python 类中**。要让 ClarifierAgent 换一种提问策略，需要改 `agents/clarifier.py` 源码
2. **TaskContext L1–L5 一次性全量构建**。简单任务（fast lane）token 消耗是必要量的 3-5 倍
3. **决策日志无过滤**。`memory/decision_log.py` 记录所有决策，信噪比低
4. **Clarifier 提问模式未结构化**。可能广度优先遍历，浅层扫过决策分支
5. **Agent 行为不可由用户扩展**。无法像 grill-me 的 10 行 SKILL.md 那样定义新行为

### 用户问题

- 用户想定制 Agent 交互策略 → 必须改 Python 源码
- 用户想复用成功任务的行为模式 → 只能手动复制粘贴代码
- 简单查询消耗过多 token → 全量上下文加载无谓浪费

### 为什么现在做

grill-me 生态（92K star）证明了一个范式：**交互协议层的投资回报率远超基础设施层**。
10 行 markdown 可以定义的行为模式，不需要 1000 行 Python 类。
Orbit 基础设施竞争已赢，交互协议层是下一个杠杆点。

## 二、目标

1. **短期（本次迭代 P0）**：引入模式文件系统 + 渐进式上下文加载，让 Agent 行为从代码解耦
2. **中期（P1）**：ADR 三重过滤 + Clarifier 决策树结构化
3. **长期（P2）**：FSRS 学习模块 + 自扩展模式生成器

## 三、用户角色

| 角色 | 描述 |
|------|------|
| Orbit 用户（开发者） | 使用 Orbit 做多 Agent 开发，想定制 Agent 行为 |
| Orbit 管理员 | 管理 Orbit 部署，想为团队定义统一的交互策略 |
| Agent 开发者 | 为 Orbit 编写自定义 Agent，想要简单的配置接口 |

## 四、用户故事

### P0（本次实现）

**US1: 模式文件定义 Agent 行为**
> 作为 Orbit 用户，我希望用 YAML 文件定义 Agent 的交互策略（提问模式、上下文范围、验证规则），
> 以便不改 Python 源码就能切换和分享 Agent 行为。

验收标准：
- 新建 `src/orbit/modes/` 目录，包含 clarify/architect/review 三个内置模式
- 每个模式用 ≤30 行 `mode.yaml` 定义行为参数
- 详细规则放在 `references/` 子目录（按需加载）
- `AgentFactory` 创建 Agent 时自动加载对应 mode 配置
- 不改 `agents/clarifier.py` 源码，换 mode 文件就能换提问策略

**US2: 渐进式上下文加载**
> 作为 Orbit 用户，我希望 Agent 先加载最少上下文，仅在需要时才深化，
> 以便简单任务的 token 消耗降低 60–80%。

验收标准：
- TaskContext 从"全量一次构建"改为"三阶段按需加载"
- Stage 1：直接上下文（当前文件+直接依赖），~2K tokens，始终加载
- Stage 2：扩展上下文（调用链+相关测试），~5K tokens，首次失败/不确定时加载
- Stage 3：全局上下文（架构文档+历史决策），~10K tokens，Agent 显式请求时加载
- Fast lane 任务只用到 Stage 1

### P1（后续迭代）

**US3: ADR 三重过滤门**
> 作为 Orbit 管理员，我希望只有"难逆转 + 令人惊讶 + 真实权衡"的决策才被记录为 ADR，
> 以便决策日志保持高信噪比。

**US4: 深度优先 Clarifier 决策树**
> 作为 Orbit 用户，我希望需求澄清阶段按决策树深度优先遍历，
> 以便每个决策分支被穷尽，不漏设计死角。

### P2（远期）

**US5: FSRS 间隔重复学习** — Agent 发现新模式 → 自动生成学习卡片，按遗忘曲线排期复习

**US6: 自扩展模式生成器** — 从成功任务执行轨迹自动生成 mode.yaml

## 五、解决方案概述

### 核心概念：模式文件（Mode File）

```
src/orbit/modes/
├── clarify/
│   ├── mode.yaml          ← ≤30 行，行为配置
│   └── references/        ← 按需加载的细节规则
│       ├── question-tree.md
│       └── domain-checks.md
├── architect/
│   ├── mode.yaml
│   └── references/
└── review/
    ├── mode.yaml
    └── references/
```

`mode.yaml` 定义：
- 适用的状态机阶段（applies_to）
- 提问策略（depth_first / breadth_first / mixed）
- 每个分支最大问题数
- 是否必须带推荐答案
- 是否代码库优先
- 按需加载的 references 列表

### 核心概念：渐进式上下文

```
Stage 1 (always):         L1 直接上下文      ~2K tokens
Stage 2 (on failure):     L2+L3 扩展上下文   ~5K tokens
Stage 3 (on request):     L4+L5 全局上下文   ~10K tokens
```

## 六、成功指标

| 指标 | 目标 | 测量方式 |
|------|------|---------|
| 模式文件可切换性 | 换 mode.yaml → Agent 行为变化，无需改 Python 代码 | 手动测试：换 clarify/mode.yaml 中 question_strategy |
| Token 节省率 | fast lane 任务 token 消耗降 ≥50% | 对比修改前后 `scheduler/task_runner.py` 中 token 计数 |
| 代码改动量 | `agents/clarifier.py` 改动 ≤30 行（加载 mode 逻辑） | git diff --stat |
| 新增模块行数 | `src/orbit/modes/` ≤300 行 Python + 150 行 YAML/Markdown | cloc |
| 测试覆盖 | 新增测试 ≥10 条（mode 加载 + 上下文阶段切换） | pytest --cov |
| 不破坏现有 | 现有 453 测试全部通过 | CI |

## 七、Non-Goals（本次不做）

- ❌ FSRS 学习模块（P2）
- ❌ 自扩展模式生成器（P2）
- ❌ 模式文件热加载（本次只做启动时加载）
- ❌ 模式文件 GUI 编辑器
- ❌ 用户自定义 mode 的 Web 界面

## 八、风险与边缘情况

| 风险 | 影响 | 缓解 |
|------|------|------|
| mode.yaml 解析失败 | Agent 创建失败 | 默认回退到硬编码行为 + 日志警告 |
| 渐进式加载导致上下文缺失 | Agent 做出错误决策 | Stage 升级阈值保守（失败即升级） |
| references/ 文件过大 | 按需加载变成"延迟全量" | references 单文件 ≤200 行限制 |
| 与现有 Agent 类耦合 | mode 加载逻辑分散 | 集中在 `agents/factory.py` 注入 |

## 九、验收标准汇总

| # | 标准 | 对应 US |
|---|------|--------|
| AC1 | `src/orbit/modes/` 目录存在，含 3 个内置 mode | US1 |
| AC2 | `AgentFactory` 创建 Agent 时读取 mode.yaml | US1 |
| AC3 | 换 mode.yaml 中 `question_strategy` 后 ClarifierAgent 行为变化 | US1 |
| AC4 | TaskContext 三阶段加载，Stage 1 默认 ≤2K tokens | US2 |
| AC5 | fast lane 任务只触发 Stage 1 | US2 |
| AC6 | Stage 2 在工具调用失败时自动触发 | US2 |
| AC7 | 现有 453 测试全绿 | 回归 |
| AC8 | 新增 mode 加载 + 上下文阶段的单元测试 ≥10 条 | 覆盖率 |

---

> 基于阶段1 PRD（验收标准共 8 条），进入阶段2 技术方案。
> 前提：用户确认 PRD 后。
