# grill-me 生态系统解构 —— Orbit 可借鉴的模式

> 2026-07-06 | 研究范围：grill-me、grill-with-docs、drill-me 三项目 + mattpocock/skills 仓库架构

---

## 一、生态全景

grill-me 不是一个孤立项目。它是 Matt Pocock 公开的 18+ 技能仓库中最具影响力的一个，
衍生出一个"交互协议优先"的工具家族：

```
mattpocock/skills (92K star)
├── grill-me          ← 核心：AI 面试你，不是写代码
├── grill-with-docs   ← 扩展版：+ 统一语言 + ADR
├── to-prd            ← 对话→PRD 合成
├── to-issues         ← PRD→垂直切片 Issue
├── tdd               ← 红-绿-重构循环
├── triage-issue      ← Issue 状态机
├── diagnosing-bugs   ← 结构化调试（先建反馈环）
├── handoff           ← 跨会话上下文压缩
├── domain-model      ← 领域模型设计
├── zoom-out          ← 代码库宏观理解
├── caveman           ← 极简 token 压缩模式
├── write-a-skill     ← 自扩展：技能写技能
└── ... (deprecated: ubiquitous-language, design-an-interface, request-refactor-plan)

timini/drill-me       ← 镜像：AI 用间隔重复教你
├── /drill:me         ← FSRS 自适应导师
└── /drill:status     ← 进度仪表盘
```

三项目的共同基因：**Process over Prompt，Interaction Protocol over Infrastructure。**

---

## 二、逐项目解构

### 2.1 grill-me —— 三句话的威力

**完整 SKILL.md**（仅 10 行）：

```
Interview me relentlessly about every aspect of this plan until we reach a
shared understanding. Walk down each branch of the design tree, resolving
dependencies between decisions one-by-one. For each question, provide your
recommended answer.

Ask the questions one at a time.

If a question can be answered by exploring the codebase, explore the codebase
instead.
```

**解构**：

| 设计元素 | 实现方式 | 为什么有效 |
|----------|---------|-----------|
| 交互协议 | 一次一个问题，禁止打包 | 消除认知过载，每步一个决策 |
| 决策树遍历 | 深度优先，完成一个分支再开下一个 | 防止浅层遍历，保证每个决策被穷尽 |
| 推荐答案 | 每个问题带 AI 推荐 | 从"你来想"变成"你来审"，降低用户负担 |
| 代码库优先 | 能自己查的不问用户 | 减少交互轮次，尊重用户时间 |
| 渐进式加载 | 根文件 10 行，细节在 references/ | 主 SKILL.md 不膨胀，节省上下文 token |

**社区扩展版**（alirezarezvani/claude-skills）增加了三个脚本：

- `scripts/decision_tree_extractor.py` — 从用户方案中提取决策分支
- `scripts/question_generator.py` — 为每个分支生成推荐问题
- `scripts/grill_session_tracker.py` — 记录会话状态和已解决决策

**核心洞察**：grill-me 不定义"问什么"，它定义"怎么问"。Prompt 是触发器，
Process 才是产品。这跟模型升级正交——GPT-5 不会让这个交互模式过时。

### 2.2 grill-with-docs —— 领域语言工程化

**三层叠加**（在 grill-me 基础上）：

1. **CONTEXT.md** — 严格词汇表，零实现细节。定义"是什么"不说"怎么做"
2. **docs/adr/** — 架构决策记录，三重过滤门：
   - 难逆转（改的成本高）
   - 缺上下文会惊讶（未来读者会问"为什么这么做"）
   - 真实权衡结果（存在替代方案，你选了其中一个）
   - → 三者全满足才创建 ADR，否则跳过
3. **四种会话行为**：
   - 术语冲突检测：用户用词与 CONTEXT.md 冲突 → 立即挑战
   - 模糊语言锐化："account"→"Customer 还是 User？"
   - 边界压力测试：发明边缘场景迫使概念精确化
   - 代码交叉验证：用户声称的 vs 实际代码实现 → 暴露不一致

**目录结构**：

```
# 单上下文仓库
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md

# 多上下文仓库（monorepo）
/
├── CONTEXT-MAP.md              ← 指向各上下文
├── docs/adr/                   ← 系统级决策
├── src/ordering/
│   ├── CONTEXT.md
│   └── docs/adr/
└── src/billing/
    ├── CONTEXT.md
    └── docs/adr/
```

**核心洞察**：共享词汇建立后，AI 响应大幅变短——不用每次重新解释定义。
统一语言不仅改善人-AI 通信，也改善 AI 内部推理链。

### 2.3 drill-me —— 间隔重复的知识逆向传输

**架构**：

```
drill-me/
├── skills/
│   ├── me/
│   │   ├── SKILL.md                    # /drill:me 导师（~60行）
│   │   └── reference/
│   │       ├── scheduling.md           # FSRS 算法 + 账本格式
│   │       └── teaching-playbook.md    # 会话结构、提示阶梯、难度伺服
│   └── status/
│       └── SKILL.md                    # /drill:status 进度仪表盘
└── docs/
    └── the-science.md                  # 每个设计决策的学术引用
```

**FSRS 简化算法**（来自 scheduling.md）：

| 组件 | 定义 | 范围 |
|------|------|------|
| Difficulty (D) | 材料固有难度 | 1.0–10.0 |
| Stability (S) | 记忆强度（遗忘到 90% 的天数） | 天 |
| Retrievability (R) | 即时回忆概率 | 0–1 |

遗忘曲线（幂律，非指数）：`R(t, S) = (1 + 0.2346 × t/S)^(-0.5)`

更新规则：
- 正确回忆 → 间隔约翻倍
- 错误回忆 → 间隔重置为 1 天
- 自信错误 → 标记 + 插队

**教学 playbook 核心规则**（认知科学驱动）：

| 聊天机器人默认行为 | drill-me 的实际做法 | 效应量 |
|-------------------|-------------------|--------|
| 向你解释 | **测验你** — 检索练习 > 重读 | g ≈ 0.61 |
| 一次性全讲完 | **间隔复习** — 按遗忘曲线排期 | FSRS |
| 让你觉得容易 | **~15% 错误率** — 最佳难度 | 挑战点假说 |
| 大段文字 | **≤150 词/块** — 认知负荷理论 | 组块化 |
| 直接给答案 | **让你先猜** — 预测试增强记忆 | pre-testing effect |

**记忆存储**：`~/.drill-me/` 下纯 Markdown 文件，可读可编辑，git 可追踪。

**核心洞察**：grill-me 把人的知识灌给 AI，drill-me 把 AI 的知识灌给人。
两个方向用同一种设计哲学：**一次一件事，按科学规律排期，可审计可追溯。**

---

## 三、mattpocock/skills 仓库架构原则

### 3.1 目录组织模式

```
skills/
├── SKILL.md              ← 根技能文件（≤50行）
├── references/           ← 按需加载的细节（算法、模板、检查清单）
├── scripts/              ← 可执行工具（提取器、生成器、追踪器）
└── deprecated/           ← 废弃技能（ubiquitous-language, design-an-interface, ...）
```

### 3.2 六条设计原则

| 原则 | 含义 | 反模式 |
|------|------|--------|
| **Process > Prompt** | Skill 定义工作流，Prompt 只是触发器 | 把 Skill 写成超长 prompt |
| **Progressive Disclosure** | 根文件 ≤50 行，细节在 references/ | 一个 500 行 SKILL.md |
| **Vertical Slice** | 端到端，非水平分层 | "先写所有 Model，再写所有 Service" |
| **Self-extending** | write-a-skill 技能写技能 | 手动复制粘贴模板 |
| **Explore before ask** | 代码库能回答的不问用户 | 无脑抛回问题 |
| **Depth-first** | 一个分支穷尽再开下一个 | 浅层扫一遍，每个分支都没到底 |

### 3.3 完整工程流水线

```
Setup → Clarify → Shape → PRD → Issues → Triage → Build → Debug → Repair → Handoff
  │       │         │       │       │         │        │       │        │        │
  │   grill-me   to-prd  to-issues triage    tdd   diagnose  repair   handoff
  │       │                        -issue   implement  -bugs
  │   grill-with
  │     -docs
setup-matt-
pocock-skills
```

每个节点是 Agent 失败模式的**刹车**，不是强制流水线。技能可组合、独立使用。

---

## 四、Orbit 对比分析

### 4.1 Orbit 当前架构（概要）

| 维度 | Orbit 现状 |
|------|-----------|
| 模块数 | 37 个 Python 包 |
| Agent 角色 | 8 种（Chatter, Clarifier, Architect, Developer, Reviewer, QA, ConfigManager, Dream） |
| 状态机 | IDLE→PARSING→SCOPING→PLANNING→CODING→VERIFYING→DONE |
| 防幻觉 | 8 层（L1 符号引用 → L8 配置漂移） |
| 图谱 | 6 种（代码/数据库/配置/知识/元/文档） |
| 通信 | 4 种消息类型（Request/Response/Notification/StreamChunk） |
| 上下文 | L1–L5 分层上下文模型 |
| 记忆 | 情景/语义/决策日志 |
| 自进化 | dream/ + evolution/（GRPO, GEPA） |

### 4.2 差距分析：Orbit 缺什么？

| # | grill 生态有的 | Orbit 的对应物 | 差距 |
|---|--------------|---------------|------|
| 1 | **轻量交互协议**（10 行 SKILL.md 定义一个完整行为模式） | Agent 类用 Python 硬编码，ClarifierAgent 行为写死在代码里 | **缺"模式文件"层**——无法不改代码就换交互策略 |
| 2 | **渐进式上下文加载**（references/ 按需加载） | TaskContext L1–L5 一次性构建 | **缺按需深化**——总是加载全部 5 层 |
| 3 | **ADR 三重过滤门**（防止决策日志膨胀） | memory/decision_log.py 记录所有决策 | **缺过滤逻辑**——可能记录过多低价值决策 |
| 4 | **统一语言注册表**（CONTEXT.md + 自动术语冲突检测） | knowledge/ 模块有本体论但未整合到 agent 交互 | **术语漂移无检测**——agent 可能用不同词说同一概念 |
| 5 | **深度优先决策树遍历**（完成一个分支再开下一个） | ClarifierAgent 提问模式未结构化 | **提问可能是广度优先**——容易浅层扫过 |
| 6 | **间隔重复学习**（FSRS 调度 + 记忆 Markdown 账本） | dream/ 做记忆巩固，但不是间隔重复 | **缺验证过的学习调度**——不知道什么时候复习什么 |
| 7 | **自扩展技能系统**（write-a-skill） | dream/ + evolution/ 过于复杂（GRPO） | **缺简单自扩展**——不能从成功任务自动生成可复用模式 |

### 4.3 Orbit 已经做对的（不需要改的）

| grill 原则 | Orbit 对应实现 | 评价 |
|-----------|---------------|------|
| Process > Prompt | 状态机驱动（IDLE→...→DONE），不是 prompt 驱动 | ✅ 已做到 |
| Explore before ask | SCOPING 阶段用 AffectedFilesScanner + ImportDependencyScanner 先查代码 | ✅ 已做到 |
| Vertical Slice | Golden Route 按任务类型路由（implement feature → architect+developer） | ✅ 已做到 |
| 可审计追溯 | task_audit_trail + checkpoint + message bus audit ring buffer | ✅ 已做到 |
| 安全沙箱 | Docker sandbox + ProcessSandbox 回退 | ✅ 已做到 |

---

## 五、具体建议（按优先级）

### P0 —— 立即值得做

#### 5.1 引入"模式文件"（Mode File）系统

**灵感来源**：grill-me 的 10 行 SKILL.md 定义完整交互模式。

**当前问题**：Orbit 的 Agent 行为硬编码在 Python 类中。要让 ClarifierAgent 换一种提问策略，需要改 `agents/clarifier.py`。

**建议方案**：

```
src/orbit/modes/
├── clarify/
│   ├── mode.yaml          # 模式元数据（名称、适用任务类型、状态机钩子）
│   └── references/
│       ├── question-tree.md     # 决策树模板
│       └── domain-checks.md     # 领域检查规则
├── architect/
│   ├── mode.yaml
│   └── references/
│       ├── perspectives.md      # 多视角设计模板
│       └── tradeoff-matrix.md   # 权衡矩阵
└── review/
    ├── mode.yaml
    └── references/
        ├── checklist.md
        └── severity-rubric.md
```

`mode.yaml` 结构（≤30 行）：

```yaml
name: clarify
version: 1
description: 需求澄清——深度优先决策树遍历
applies_to: [PARSING]
behavior:
  question_strategy: depth_first    # depth_first | breadth_first | mixed
  max_questions_per_branch: 20
  require_recommendation: true     # 每个问题必须带推荐答案
  codebase_first: true             # 能查代码就不问用户
references:
  - question-tree.md               # 按需加载
  - domain-checks.md               # 仅在术语冲突时加载
```

**改动范围**：
- 新增 `src/orbit/modes/` 模块（~200 行）
- 修改 `agents/clarifier.py`：加载 mode 配置替代硬编码行为
- 修改 `agents/factory.py`：Agent 创建时注入 mode

**收益**：
- 不改代码换交互策略
- 用户可以写自己的 mode 文件
- git 可追踪行为变更

#### 5.2 TaskContext 渐进式加载

**灵感来源**：grill-me 根文件 10 行，references/ 按需加载。

**当前问题**：`TaskContext` 在每次 agent 循环开始时构建全部 L1–L5 层。对于简单任务（fast lane），大部分上下文用不上。

**建议方案**：修改 `agents/context.py`，引入三阶段加载：

```
Stage 1 (always): L1 直接上下文（当前文件、直接依赖）      → ~2K tokens
Stage 2 (on first failure): L2+L3 扩展上下文（调用链、相关测试）→ ~5K tokens  
Stage 3 (on explicit request): L4+L5 全局上下文（架构文档、历史决策）→ ~10K tokens
```

Agent 在每次工具调用失败或不确定时自动升级阶段。

**收益**：
- 简单任务 token 消耗降 60–80%
- Agent 不会在不需要时被全局上下文干扰
- 符合 grill-me 的"先查代码库，再问用户"哲学

### P1 —— 值得规划

#### 5.3 ADR 三重过滤门

**灵感来源**：grill-with-docs 的 ADR 创建决策树。

**当前问题**：`memory/decision_log.py` 可能记录过多决策，导致决策日志膨胀、信噪比低。

**建议方案**：在 `DecisionLog.log()` 前加三重过滤：

```python
def should_create_adr(decision: Decision) -> bool:
    """ADR 三重过滤门——只有三项全满足才记录"""
    if not decision.is_hard_to_reverse():
        return False  # 容易改的决定不需要 ADR
    if not decision.is_surprising_without_context():
        return False  # 显而易见的决定不需要 ADR
    if not decision.involves_real_tradeoff():
        return False  # 没有替代方案的不算决策
    return True
```

**收益**：决策日志从"所有决策"变成"值得记录的决策"，信噪比大幅提升。

#### 5.4 深度优先 Clarifier 决策树

**灵感来源**：grill-me 核心算法——决策树深度优先遍历。

**当前问题**：Orbit 的 ClarifierAgent 做需求澄清，但提问模式未显式化为树遍历算法。

**建议方案**：在 `scheduler/clarifier.py` 增加 `DecisionTreeWalker`：

```python
class DecisionTreeWalker:
    """深度优先遍历需求决策树"""
    def extract_branches(self, requirement: str) -> list[DecisionBranch]:
        """从需求描述中提取决策分支"""
    
    def walk(self, branches: list[DecisionBranch]) -> Generator[Question]:
        """深度优先遍历，每步产出一个问题 + 推荐答案"""
        for branch in branches:
            yield from self._resolve_branch(branch)  # 完成一个分支再开下一个
    
    def _resolve_branch(self, branch: DecisionBranch) -> Generator[Question]:
        """递归解决一个分支的所有子决策"""
```

**收益**：需求澄清从"随机提问"变成"结构化遍历"，不漏决策分支。

### P2 —— 长期可考虑

#### 5.5 轻量 FSRS 学习模块

**灵感来源**：drill-me 的 FSRS 间隔重复。

**建议**：新增 `src/orbit/learning/` 模块，约 300 行：

- `scheduler.py` — FSRS 简化版（Difficulty/Stability/Retrievability 三变量）
- `cards.py` — Markdown 卡片存储（`~/.orbit/learning/`）
- `modes/clarify/references/learning-hooks.md` — 当 agent 发现新模式时自动生成卡片

**用途**：
- Orbit 发现新的 bug 模式 → 自动生成学习卡片
- 用户想理解某个架构决策 → `/orbit:learn event-sourcing`
- Agent 在类似上下文再现时 → 自动复习相关卡片

#### 5.6 从成功任务自动生成模式文件

**灵感来源**：mattpocock 的 `write-a-skill` 技能。

**建议**：新增 `/api/v1/modes/generate` 端点：

```
POST /api/v1/modes/generate
Body: { "task_id": "uuid", "name": "my-custom-review-mode" }

→ Orbit 分析任务执行轨迹
→ 提取关键决策点、使用的工具、上下文加载模式
→ 生成 mode.yaml + references/
→ 保存到 src/orbit/modes/
```

**收益**：Orbit 能从成功经验中学习，不需要人工编写 mode 文件。

---

## 六、总结：核心教训

### grill-me 生态的本质

这三个项目不是技术创新——它们几乎没有"算法"。**它们的创新在交互协议层**：

| 传统 AI 工具 | grill-me 生态 |
|-------------|--------------|
| 定义 AI 应该**输出什么** | 定义 AI 应该**怎么交互** |
| 长 prompt = 更好的输出 | 短协议 = 更好的过程 |
| 基础设施竞争（更好的模型、更快的推理） | 过程竞争（更好的决策树遍历、更好的术语管理） |
| 一次性的代码生成 | 可复用的交互模式 |

### Orbit 的定位

Orbit 在基础设施层已经做到极致——37 个模块、8 层防幻觉、6 种图谱、毫秒级熔断。
**基础设施竞争已经赢了。**

但 Orbit 在交互协议层有空白。grill-me 生态给的最大启发是：

> **10 行 markdown 可以定义的行为模式，不需要 1000 行 Python 类。**
> **基础设施做重，交互协议做轻。**

**一句话**：Orbit 不需要更多模块。它需要一个"模式文件"系统，让交互策略从代码中解耦出来，
实现 grill-me 级别的灵活性和可组合性。

---

## 附录：参考来源

- [mattpocock/skills](https://github.com/mattpocock/skills) — 92K star，18+ 技能
- [timini/drill-me](https://github.com/timini/drill-me) — FSRS 间隔重复导师
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) — grill-me 社区扩展版
- [Matt Pocock's Agent Skills — 30K Stars and the Start of the Skill Economy](https://dev.to/_46ea277e677b888e0cd13/matt-pococks-agent-skills-30k-stars-and-the-start-of-the-skill-economy-lg2)
- [grill-me + goal: AI 编码完整工作流](https://global.v2ex.co/t/1214285)
