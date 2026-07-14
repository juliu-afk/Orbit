# 微信文章调研报告 —— Orbit 可借鉴/集成分析

> 日期：2026-07-13 | **状态：✅ 已全部落地（2026-07-14）**
> 来源：4 篇微信公众号文章 + Unreal Engine MCP 生态调研
> 目的：识别对 Orbit 多 Agent 自循环系统有直接价值的架构设计、开源工具和集成机会
> 交付：5 PRs (#300+#301+#305+#310+#312)，22 条行动项全覆盖

---

## 文章目录

| # | 标题 | 作者/来源 | 核心主题 |
|---|------|-----------|---------|
| 1 | Zerox Agent 正式发布：一个人用 Cursor 做了 DeepSeek 产品经理的活 | Zerox张探索 | 单人 35 天从零构建 macOS Agent 全记录 |
| 2 | Agent 专用搜索登顶 Product Hunt，Token 更省搜得更准 | 量子位 | AnySearch — Agent 原生搜索引擎 |
| 3 | OpenTab：像 lazygit 一样钻取 AI 编程每一分钱的 Terminal UI | 开源HubLab | AI 编程成本可观测性 TUI 工具 |
| 4 | Claude Code + Excel 自动化数据分析 | 杰之念7 | MCP 连接 Excel 的实操（内容较薄） |
| 5 | Unreal Engine MCP 生态调研 | Epic Games + 社区 | UE 5.8 官方 MCP + 6 个第三方开源方案的深度对比 |

---

## 文章 1：Zerox Agent —— 单人全栈 Agent 构建实录

### 摘要

单人（自称"不会写代码的产品经理"）用 Cursor 在 35 天内从零构建了一个完整的 macOS AI Agent 应用：**374 次提交，14.3 万行 TypeScript，0 依赖 AI Agent 框架（拒绝 LangChain），全部自己写**。

### 技术栈

```
Electron (macOS 原生壳)
├── Main Process: Agent 内核全部逻辑（1570 行核心循环）
├── Preload Bridge: 安全 IPC 通道
└── Renderer Process: React 界面（270 文件，9.5 万行）
    存储层: SQLite + JSON 双写
```

### 关键架构决策

#### 1. Agent 核心循环（1570 行，单文件）

```
Loop:
  1. 检查用户停止信号
  2. 注入系统提示
  3. 压缩上下文（超限时）
  4. 调用模型
  5. 解析模型回复
  6. 执行工具调用
  7. 记录检查点（JSON checkpoint）
→ 回到步骤 1
```

每个步骤都有坑：
- **重复工具调用检测**：同一工具同一参数连续调用 ≥4 次 → 强制停止，要求重新规划
- **上下文压缩**：Kernel 自动摘要 + checkpoint 重建上下文路径
- **检查点**：JSON 格式，崩了不丢失进度

#### 2. Goal Mode（目标模式）—— 规划→执行→验证闭环

与普通 Agent 的"说一句做一步"不同：
```
用户目标
  → 规划阶段：自动拆解为多个里程碑，每个有明确成功标准
  → 执行阶段：逐个里程碑执行
  → 验证阶段：每步执行后验证结果
  → 汇报阶段：汇总所有验证结果
```

核心理念：**LLM 说"完成了"不算数。文件系统自己验证才算。**

#### 3. 五层记忆体系

| 记忆类型 | 生命周期 | 检索方式 | 用途 |
|----------|---------|---------|------|
| core | 永久 | 直接读取 | 核心偏好设置 |
| session | 当前会话 | 直接读取 | 当前上下文 |
| semantic | 长期 | FTS5 + 向量 RRF 混合 | 概念性记忆 |
| episodic | 长期 | 自动从执行轨迹提取 | 过往经验 |
| procedural | 长期 | 偏好驱动的操作模板 | 常用操作流程 |

**检索实现**：SQLite FTS5 关键词索引 + BGE 向量搜索 → hybrid RRF（Reciprocal Rank Fusion）融合排序。

#### 4. Shell 安全 —— 自研 tree-sitter AST 分析器

不依赖黑名单正则匹配。做法：
- tree-sitter 解析 shell 命令为 AST
- 识别：分号链、管道注入、命令替换符号、重定向
- 检测到危险操作时，**allow 规则自动失效**，弹窗人工确认
- 硬危险清单：`rm -rf`、`git push -f`、`sudo`、网络下载+管道执行（`curl ... | bash`）

#### 5. 权限模型 —— 动态权限 + 沙箱

```
默认：~/projects 目录下自由读写，禁止网络
  ├── 超出 workspace → sandbox 约束
  ├── 网络请求 → 弹窗确认
  └── 危险命令 (rm -rf / git push -f / sudo) → 强制人工确认
```

设计原则：99% 操作自动执行，1% 危险操作必须人工确认。

#### 6. 证据驱动验证

两层验证：
1. **确定性检查**：文件系统自证——文件创建了？内容正确？目录结构对？
2. **模型检查**：LLM 审查执行记录，但必须引用文件系统证据，瞎编的证据被拒绝

#### 7. Skill 系统 —— Markdown 即 Skill

用户写 Markdown 文件放到指定目录 → Agent 自动扫描发现 → 按需加载调用。不写代码就能扩展 Agent 能力。

#### 8. 单人开发的工程纪律

- main 分支永远可发布（曾因在 main 上直接改导致 SQLite 数据损坏）
- 每次改动走 feature 分支 → 验证 → 合并
- 事故归档到 `docs/audit/` 目录
- 自建"三人角色"流程：规划者 → 实现者 → 验证者（一个人扮演三个角色）
- 前端三版设计迭代：Material → Soft Blue → Obsidian 暗色

---

### 对 Orbit 的借鉴价值

| # | 借鉴点 | Orbit 现状 | 差距/机会 | 优先级 |
|---|--------|-----------|----------|--------|
| 1 | **Goal Mode 闭环** | `goal/` + `goal_judge/` 模块存在 | 缺"执行前先规划→每步验证"显式闭环。Zerox 的规划阶段+里程碑验证可直接参考 | **P1** |
| 2 | **FTS5 + RRF 混合检索** | `memory/` 分层记忆已实现 | 检索层可增强：SQLite FTS5 关键词 + RRF 融合。约 30 行代码 | **P2** |
| 3 | **Tree-sitter Shell AST 安全** | `sandbox/` Docker 隔离 + `security/` | AST 级 shell 分析是 Docker 隔离的轻量补充，双重防护 | **P1** |
| 4 | **重复工具调用熔断** | `resource_guard/` 已有 token + 延迟熔断 | 加一条同签名工具调用计数规则即可 | **P2** |
| 5 | **证据驱动验证** | L1-L9 防幻觉体系 | L7（沙箱执行）后可加确定性验证层 | **P2** |
| 6 | **Skill 自动发现** | `compose/` SKILL.md 注入 | Zerox 的"用户创建→自动发现→按需加载"模式更开放 | **P3** |
| 7 | **单人工程纪律** | Orbit 本身开发流程 | 事故归档、main 分支保护是通用最佳实践 | P3 |
| 8 | **Electron 架构** | Orbit 用 Tauri (Rust WebView) | 不同技术选型，但 Main Process 管理 Agent 生命周期、Preload Bridge 安全 IPC 的模式可参考 | P3 |

### Zerox 五层记忆 vs Orbit 记忆体系 —— 深度对照

> 2026-07-13 补充：对 Orbit `memory/` 模块（8 个组件）全文审查后的逐层对比。

#### Orbit 记忆体系全景（8 组件）

| # | 组件 | 位置 | 存储 | 做什么 |
|---|------|------|------|--------|
| 1 | **MemoryStore** | `memory/store.py` | Markdown 文件 | 文件级 CRUD——5 种文件类型，BM25 搜索，双向同步 |
| 2 | **EpisodicMemory** | `memory/episodic.py` | SQLite 图结构 | 事件节点 + 关系边（CAUSED_BY/FOLLOWED_BY/CONTRADICTS），时序推理 |
| 3 | **AgenticMemory** | `memory/agentic.py` | SQLite | "遇到 X → 做 Y → 结果 Z"，效用评分 ±0.1，Q-learning 式强化 |
| 4 | **ProfileStore** | `memory/profile.py` | SQLite | 用户画像——per-client 偏好/目标/沟通风格 |
| 5 | **DecisionLog** | `memory/decision_log.py` | JSONL | 决策日志——线程安全追加写，Jaccard 冲突检测 |
| 6 | **ScopeMemory** | `evolution/scope.py` | SQLite | SCOPE 双流：战术规则(per-task) 自动升级为战略规则(跨任务) |
| 7 | **ThreeTierMemory** | `goal/memory_tiers.py` | 内存+文件 | Ledger 层(永久) / Beads 层(会话) / Execution 层(每轮)——三层生命周期 |
| 8 | **FTS5 + BM25** | `memory/fts.py` | SQLite FTS5 | 全文索引 + 纯 Python BM25，CJK bigram/jieba 分词 |

#### 逐层对比

| Zerox 五层 | Orbit 对应 | 谁更强 | 差距分析 |
|------------|-----------|--------|---------|
| **core** (核心偏好) | ProfileStore.preferences | 大致持平 | Orbit 是 per-client，缺**全局系统偏好**层（"这个 Agent 本身的性格"）。但 AgenticMemory + ScopeMemory 的战略规则已部分覆盖 |
| **session** (会话上下文) | ThreeTierMemory.Execution + checkpoint.md | 大致持平 | Orbit 是文件 IO，Zerox 是内存级。长会话下 Orbit 有 IO 开销，但 ThreeTierMemory 的三层压缩策略更精细 |
| **semantic** (语义记忆) | MemoryStore + FTS5/BM25 | **Zerox 强** 🔴 | **Orbit 只有 BM25 关键词匹配，没有向量语义搜索**。Zerox 用 FTS5 + BGE 向量 → RRF 混合融合。BM25 对中文 CJK 效果差。这是最大差距 |
| **episodic** (情节记忆) | EpisodicMemory (图结构) | **Orbit 强** ✅ | Orbit 的图结构（节点+关系边+时序推理）远强于 Zerox 的简单事件列表。但 Zerox **自动从执行轨迹提取**，Orbit 需要显式调用 `record_event()` |
| **procedural** (操作流程) | AgenticMemory + ScopeMemory | **Orbit 强** ✅ | AgenticMemory 的 trigger→action→feedback 闭环 + ScopeMemory 的战术→战略自动升级。Zerox 的 procedural 是静态流程模板，Orbit 是动态规则+效用驱动的强化学习 |

#### 结论

Orbit 的记忆体系在**深度**上超过 Zerox（图结构、Q-learning 式反馈、SCOPE 自动升级、三层生命周期），但两条短板必须补：

1. **向量语义搜索**（只有 BM25，中文差）→ 提至 **P1**
2. **自动记忆提取**（需手动 record，Zerox 自动从轨迹学）→ 提至 **P1**

这两条加上后，Orbit 的记忆体系就是 Zerox 的超集——既有图的深度，又有向量的广度，还带 SCOPE 自动进化。

---

## 文章 2：AnySearch —— Agent 原生搜索引擎

### 摘要

AnySearch 是一款**专门给 AI Agent 用的搜索引擎**（不是给人用的），Product Hunt 周榜 Top 1。中国团队开发。核心差异化：不做"全网网页搜索+模型后过滤"，而是**搜索前智能路由到垂直数据源 + 搜索中前置筛选 + 输出结构化 Markdown**。

- GitHub: [anysearch-ai](https://github.com/anysearch-ai)
- 官网: [www.anysearch.com](http://www.anysearch.com)
- 免费额度：注册后 1000 次/天
- 接入方式：API / MCP / Skill 三种

### 核心架构

```
用户查询
  → 智能意图路由（自动识别：代码？法律？金融？学术？）
  → 多源并行查询（20+ 垂直数据源 + 通用搜索）
  → 前置筛选（同源衰减 + 信息密度仲裁 + 语义+时效混合排序）
  → 正文提取 + 去噪 + Markdown 结构化
  → 交付给 Agent（已去重、已格式化、可直接推理）
```

### 搜索质量

在一项 300 道题的基准测试中（Frames + FreshQA + WebwalkerQA），同一 LLM 条件下：
- AnySearch: **76.4%** 综合准确率
- Parallel Search: 低于 AnySearch
- Brave Search: 低于 AnySearch
- 延迟也是三家最优

### 与 Exa/Tavily/Brave 的关键差异

| 维度 | Exa/Tavily/Brave | AnySearch |
|------|-----------------|-----------|
| 数据源 | 全网网页 | 20+ 垂直数据源 + 通用搜索 |
| 筛选时机 | 搜索后 LLM 过滤 | 搜索中前置筛选 |
| 输出格式 | 链接+摘要为主 | 结构化 Markdown |
| 去重方式 | 基础去重 | 同源衰减 + 信息密度仲裁 |
| Token 效率 | 低（Agent 需多轮筛选） | 高（一步到位） |

### 关键算法

1. **同源衰减算法**：同一站点占据多个搜索结果位时，主动降低权重
2. **信息密度仲裁算法**：相关性相近时，优先保留信息量更丰富的内容
3. **混合排序算法**：语义相关性 + 内容时效性联合排序

### 工程能力

- 自动容错：某一路数据源异常 → 自动切换可用路径
- 超时管控：不拖慢整体搜索流程
- 页面去噪：自动剥离广告、SEO 垃圾
- 正文提取 → Markdown 结构化

---

### 对 Orbit 的直接集成价值

**Orbit 当前 `knowledge/` 模块**：
```
SQLite 本地知识库 + BGE 向量语义搜索 + TF-IDF 关键词降级 + MCP 接口
```

**集成方案**：AnySearch 提供 MCP 接口 → Orbit 的 `knowledge/` 或 `gateway/` 模块直接接 MCP。

```
Orbit knowledge/
├── 本地 SQLite（代码图谱/数据库图谱/配置图谱）
├── BGE 向量语义搜索
├── TF-IDF 关键词降级
└── AnySearch MCP  ← 新增：实时外部信息检索
```

**Orbit Agent 需要外部信息的场景**：
- 代码审查：查最新库版本、CVE 安全漏洞公告
- 技术方案生成：查 best practice、最新 API 文档
- 依赖分析：查 license 信息、已知 bug
- 自进化模块：追踪最新 AI 技术进展
- 配置漂移检测（L8）：对比外部基准

| 集成项 | 方案 | 工作量 | 优先级 |
|--------|------|--------|--------|
| AnySearch MCP 接入 | `knowledge/` 添加 AnySearch MCP connector | 低（MCP 协议标准，~1h） | **P0** |
| 搜索意图路由 | 复用 AnySearch 的意图识别，或自建轻量路由器映射到 Orbit 五图谱查询 | 中 | P2 |
| 前置筛选链 | 借鉴同源衰减+信息密度仲裁算法，应用到 Orbit 知识检索 | 中 | P2 |
| Agent 搜索范式 | 将 AnySearch 的"搜索即基础设施"理念融入 Orbit 知识模块设计哲学 | 低（文档+设计层面） | P2 |

---

## 文章 3：OpenTab —— AI 编程成本可观测性 TUI

### 摘要

OpenTab 是一个**纯标准库（curses + sqlite3）的 Terminal UI**，lazygit 风格。读取 AI 编程工具本地存储的 token/cost 数据，提供多层钻取和可视化。**全部 read-only、不联网（除手动刷新模型价格）、零遥测**。

- GitHub: [hamidi-dev/opentab](https://github.com/hamidi-dev/opentab)
- PyPI: `opentab-ai`
- 一行试用: `uvx --from opentab-ai opentab --demo`

### 核心设计

#### 统一 Store 契约（核心抽象）

每个数据源实现统一接口：
```python
class Store:
    def workflows()        # 快速 per-root session rollup（首帧立刻画）
    def summary()          # app-wide totals
    def workflow_nodes(id) # recursive subagent cost tree
    def model_breakdown()  # per-model 统计（deferred）
    # 可选
    def tool_breakdown()
    def message_timeline()
```

**所有数据源**（Claude Code JSONL、OpenCode SQLite、Codex rollout JSONL、GitHub Copilot OTEL、VS Code chatSessions 等 12 种）→ 统一 Store 接口 → 同一套 TUI/Web 浏览器。

#### 架构分层

```
src/opentab/
├── stores/          # 每个数据源一个 store + CachedStore + CombinedStore
│   ├── opencode.py, claude.py, codex.py, hermes.py,
│   ├── copilot.py, vscode.py, pi.py, openclaw.py, zaly.py,
│   ├── csv_source.py, jsonl_source.py, combined.py, cached.py
├── tui/
│   ├── app.py       # 状态机 + key/mouse handler
│   └── renderer.py  # 所有绘制（return list[str]）
├── pricing.py       # 两层 models.dev 定价模型
├── models.py        # 数据模型
├── web.py           # build_payload + serve
├── webpage.py       # self-contained HTML
└── cli.py           # 入口
```

依赖图严格分层：leaves → stores → tui → sources/state/web → cli。无环。

#### 关键特性

| 特性 | 实现 |
|------|------|
| **多层钻取** | 月份→日→项目→session→模型→subagent 树→turns 时间线→tools 归因 |
| **Cost what-if** | 双 cost snapshot——recorded（真实花费）vs API list price（等效花费），一键切换 |
| **Subagent 成本归属** | 递归 workflow_nodes，每个 parent 含整个 subtree 成本 |
| **CachedStore** | fingerprint (path, size, mtime_ns)，命中则跳过解析（~0.8s→~50ms warm） |
| **CombinedStore** | 多源合并，同一 repo 自动 rollup，Src 列显示来源 |
| **12 种数据源** | Claude Code、OpenCode、Codex、Hermes、Copilot CLI、VS Code Chat、pi-agent、OpenClaw、zaly、CSV、JSONL 等 |
| **Web Twin** | `--html` 生成自包含 HTML；`--serve` 启动 localhost:8321 服务 |
| **主题** | Catppuccin / Tokyo Night / Gruvbox / Nord / Dracula / Rosé Pine，TUI+Web 共享 |
| **Demo 模式** | `--demo` 内存匿名化，安全截图/演示 |
| **隐私** | 100% read-only，无网络（除手动刷新价格），无遥测，无账号 |

#### 定价模型设计

每个 Workflow 同时携带两套 cost：
1. **recorded**：工具记录的真实花费（subscription 用户显示 $0.00）
2. **api-equivalent**：recorded + unpriced tokens × API list price

`$` 键一键切换。`P` 键打开完整 per-model 价格表（models.dev 快照，~5000 行），支持按 vendor/provider 视图、pin 常看模型、eff $/M 按实际 token mix 混合计算。

---

### 对 Orbit 的借鉴价值

Orbit 已有 `observability/` 模块（OpenTelemetry + 审计 + 反馈引擎 + 轨迹收集）。OpenTab 提供了三个维度的启发：

#### 1. 成本可观测性子系统（Orbit 当前缺）

Orbit 的 `gateway/` 模块通过 LiteLLM 做三层模型路由（T1/T2/T3）+ 降级，`observability/` 有审计和轨迹。但**缺少面向用户的成本可视化**。

OpenTab 的 store 契约模式可以直接适配：

```python
# Orbit 可以实现的 Store 接口
class OrbitCostStore:
    def workflows()        # 按 project/session 聚合
    def workflow_nodes(id) # 递归 subagent 成本树
    def model_breakdown()  # T1/T2/T3 路由的模型用量分布
    def circuit_breaker_events()  # Orbit 特有：熔断事件时间线
```

#### 2. Subagent 成本归属

Orbit 的 `compose/` 多 Agent 编排会生成嵌套的 Agent 调用树。OpenTab 的 `workflow_nodes` 递归成本归属模式**直接适用于 Orbit**——每个 subagent 的成本递归汇总到父 Agent。

#### 3. CachedStore 模式

Orbit 的轨迹/审计数据量增长后，OpenTab 的 fingerprint 缓存策略（path + size + mtime_ns → 跳过解析）可直接复用。

| # | 借鉴点 | Orbit 现状 | 优先级 |
|---|--------|-----------|--------|
| 1 | **成本 TUI 仪表盘** | `observability/` 有数据采集但无可视化前端 | **P1** |
| 2 | **Subagent 成本归属** | `compose/` 编排无成本归因 | **P1** |
| 3 | **Store 契约抽象** | 无统一数据源接口 | P2 |
| 4 | **CachedStore** | 轨迹数据无缓存层 | P2 |
| 5 | **What-if 定价** | LiteLLM 路由但用户看不到不同模型的成本差异 | P2 |
| 6 | **Web Twin** | 无可分享的 HTML 报告 | P3 |

---

## 文章 4：Claude Code + Excel 自动化数据分析

### 摘要

内容较薄，主要演示通过 MCP 协议连接 Claude Code 与 Excel（`excel-mcp-server`），实现 AI 驱动的 Excel 数据分析。本质是课程推广文章。

### 对 Orbit 的参考价值

仅一个可提取的点：**MCP Server 即插即用模式的验证**。Excel 这种非代码工具通过 MCP 接入 AI Agent 的范式已经成熟。Orbit 的 MCP 集成策略是正确的。

无其他实质性技术内容。

---

## 文章 5：Unreal Engine MCP 生态 —— Agent 驱动专业工业软件的范式验证

### 背景

2026 年 7 月，Epic Games 在 Unreal Engine 5.8 中**首次内置 MCP 插件**（Experimental），标志着 MCP 协议从 AI 工具链进入**专业工业软件领域**。与此同时，社区涌现了 6+ 个高质量第三方 MCP 方案，工具数从 62 到 1710 不等，覆盖 UE 编辑器的几乎所有子系统。

这不是一个"做完了"的故事——而是 MCP 作为一种**通用 AI-to-Application 桥梁协议**在复杂 GUI 应用中的可行性得到官方和社区双重验证。

### Epic 官方 MCP 插件（UE 5.8，Experimental）

**来源**：[Epic Developer Community — Unreal MCP in Unreal Editor](https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor?application_version=5.8)

#### 架构

```
AI Agent (Claude Code / Cursor / VS Code / Gemini / Codex)
    │ MCP (HTTP, stdio)
    ▼
Unreal MCP Plugin (嵌入 Editor 进程内)
    │ HTTP server @ http://127.0.0.1:8000/mcp
    ▼
Toolset Registry (C++ + Python toolsets, 可扩展)
    │
    ▼
Unreal Editor API (Spawn Actor / Material / Slate / Automation / ...)
```

核心设计：
- **嵌入 Editor 进程内**：不需要外部 bridge 进程，MCP Server 直接跑在 UE 内
- **Toolset Registry**：工具发现和注册中心，支持 C++ 和 Python 两种编写方式
- **一键生成客户端配置**：`ModelContextProtocol.GenerateClientConfig` 自动生成 Claude Code / Cursor / VS Code / Gemini / Codex 的 MCP 配置
- **与 Terminal 插件集成**：编辑器内嵌终端，AI 交互不离开编辑器窗口
- **局限性**：仅本地（无认证）、API 实验性（可能变化）、UE 5.8+ 独占

#### 官方暴露的工具类别

- Actor 生成与配置（灯光、碰撞、Transform）
- Material 实例创建与参数调整
- Slate Widget 检视与调试
- Automation 测试执行
- Level 内容查询与修改
- （可扩展，C++ / Python Toolset）

### 社区第三方方案全景（2026 年 7 月）

#### 六方案速览

| 项目 | 规模 | UE 版本 | 架构 | 许可证 | 差异化 |
|------|------|---------|------|--------|--------|
| **PrismMCP** (Asara Tech) | 1710 命令 / 60 系统 | 5.3–5.8 | MCP ↔ C++ Plugin | Lite 免费 + Pro $49/yr | 覆盖面最广，Fab 市场上架 |
| **UE-MCP** (db-lyon) | 612+ 动作 / 22 类别 | 5.8 | C++ Plugin + YAML 流引擎 | MIT | YAML 定义多步工作流 |
| **GenOrca/unreal-mcp** | 253 动作 / 21 域 | 5.6+ | Python MCP + C++ Plugin | 开源 | Python 可扩展，无需 C++ rebuild |
| **ultimateunrealenginemcp** | 133 工具 / 26 域 | 5.7 | TS MCP (stdio) ↔ TCP ↔ C++ Plugin | 开源 | Visual Review Loop（视觉反馈闭环） |
| **IvanMurzak/Unreal-MCP** | 62 工具 / 8 家族 | 5.5+ | C++ Plugin + .NET Bridge + Cloud | 开源 | Blueprint 编译反馈 + 云端模式 |
| **AgentBridge** (Incurian) | ~100 工具 | 5.6+ | gRPC ↔ Tempo 仿真 | 开源 | 仿真控制 + PCG 图编辑 |

#### 关键架构模式：三层桥接

几乎所有方案（除 Epic 官方）遵循同一个三层模式：

```
┌──────────────┐   MCP (stdio/HTTP)   ┌──────────────────┐   TCP/WS/gRPC   ┌──────────────────┐
│  AI Agent    │ ────────────────────→│  MCP Bridge       │ ──────────────→ │  Unreal Editor   │
│  (Claude,     │ ←───────────────────│  (Python/TS/.NET) │ ←──────────────│  (C++ Plugin)    │
│   Cursor...)  │                     │                   │  JSON-RPC      │                  │
└──────────────┘                     └──────────────────┘                 └──────────────────┘
```

**为什么需要 Bridge？**
- UE Editor 运行在 C++ 进程内，无法直接暴露 MCP Server（MCP 生态主要是 Python/TS）
- Bridge 负责协议翻译：MCP tool call → JSON-RPC → UE C++ API
- Bridge 进程可独立部署（本地/云端），不与 UE 进程耦合

**这条架构模式对 Orbit 的启示**：
> Orbit 的 `sandbox/` + `tools/` 模块本质上也是"桥接"——将 Agent 的工具调用翻译为宿主机操作。UE MCP 的三层模式验证了"AI ↔ 协议翻译层 ↔ 目标应用"的通用性。Orbit 如果要集成第三方 GUI 应用（如 Blender、Figma、VS Code），这套模式就是路线图。

### 值得 Orbit 深度学习的 5 个设计

#### 1. Visual Review Loop（视觉反馈闭环）

ultimateunrealenginemcp 的核心创新：

```
AI 操作 → 截图(baseline) → AI 分析变化 → 调整参数 → 再截图 → 验证 → 清理
```

具体工具：
- `ue_look_at`：相机对准目标
- `ue_orbit_review`：环绕观察
- `ue_fly_through`：飞行穿越场景
- `ue_visual_review`：全场景视觉审查
- `ue_focus_actor`：聚焦特定 Actor

截图以 base64 内联在 MCP response 中 → AI "真正看到"场景变化。

**Orbit 借鉴**：这是 Zerox Agent "证据驱动验证"在 3D 场景中的实现。Orbit 的 `hallucination/` L7（沙箱执行验证）可以扩展到视觉维度——UI 测试、前端渲染验证、图表生成正确性检查。

#### 2. Toolset Registry —— 可扩展工具发现

Epic 官方的 Toolset Registry 设计：
- 工具不是硬编码的，而是注册到 Registry
- C++ Toolset：编译时注册，性能关键路径
- Python Toolset：运行时注册，快速迭代无需编译
- Agent 启动时通过 MCP `list_tools` 自动发现所有已注册工具

**Orbit 借鉴**：Orbit 的 `tools/` 模块可以借鉴这种双层注册机制（编译型 + 脚本型），让用户无需改代码就能扩展 Agent 工具。

#### 3. Domain Action 模式 —— 避免 Context Bloat

GenOrca/unreal-mcp 的设计（253 个动作，但只有 21 个 MCP tool）：

```json
// 一个 "actor" tool，通过 action 参数路由到不同操作
{ "action": "spawn_from_class", "params": { "class_path": "...", "location": [0,0,200] } }
{ "action": "delete",          "params": { "actor_name": "..." } }
{ "action": "set_transform",    "params": { "actor_name": "...", "location": [0,50,0] } }
```

**优势**：
- 253 个动作不会让 MCP `list_tools` 爆掉（只有 21 个 tool 注册）
- 同一领域的操作共享上下文描述
- LLM 更容易理解"对 actor 我能做什么"而不是遍历 253 个独立工具

**Orbit 借鉴**：Orbit 的工具数量增长后（目前已 45 个模块，每个模块都有暴露的工具），Domain Action 模式可以避免工具列表上下文爆炸。比 GenOrca 更进一步，Orbit 可以用知识图谱自动将工具按领域聚类。

#### 4. 结构化编译反馈闭环

IvanMurzak/Unreal-MCP 的 Blueprint/C++ 编译流程：

```
AI 生成 Blueprint 节点 → 触发编译 → 解析编译错误（结构化 JSON）
  → 将错误位置 + 错误信息反馈给 AI → AI 修正 → 重新编译
  → 循环直到编译通过
```

这不是简单返回"编译失败"，而是：
- 错误位置（文件:行号:列号）
- 错误类型（语法/类型/链接/依赖）
- 建议修复方向

**Orbit 借鉴**：Orbit 的 `sandbox/` 执行代码时，可以加同样的"结构化错误反馈→AI 修正→重新执行"闭环。当前 Orbit 的沙箱执行只是 pass/fail，缺少"为什么失败 + 怎么修"的结构化反馈。

#### 5. MCP 辅助工具：API 文档防幻觉

`unreal-api-mcp`（PyPI）是一个独立于编辑器的 MCP Server——不控制 UE，**只提供 API 签名**：
- 114,000+ 条 UE C++ API 记录（5.5–5.7）
- 每条记录包含：精确函数签名 + `#include` 路径 + 所属模块
- 用途：防止 LLM 生成不存在的 UE API 调用（C++ 领域的幻觉重灾区）

**Orbit 借鉴**：这是"知识图谱作为 MCP"的典范案例。Orbit 的**代码图谱**（Tree-sitter 解析的代码结构）可以暴露为 MCP Resource——Agent 在写代码前先查询代码图谱，确认目标函数/类/方法真实存在。这与 Orbit 的 L4 防幻觉（类型检查）互补——L4 是事后校验，MCP 知识图谱是事前预防。

### 对 Orbit 的核心启示

UE MCP 生态的爆发验证了三条关键假设：

1. **MCP 是通用桥梁协议**：不只是代码编辑器←→AI，而是任意复杂 GUI 应用←→AI。UE Editor 的复杂度（数百个子系统、数万 API）远超 IDE，MCP 依然能承载。

2. **Tool 设计比 Tool 数量重要**：GenOrca 的 21 tool / 253 action 模式 vs PrismMCP 的 1710 独立命令——前者对 LLM context 更友好，后者覆盖面更广。Orbit 需要在两者间权衡。

3. **视觉反馈是下一代 Agent 验证的基础设施**：代码生成可以靠编译器验证，UI 生成靠什么？截图。Orbit 的 E2E 测试（Playwright）已经用截图做回归验证——这本身就是一种"视觉反馈闭环"的雏形。

---

## 综合建议：Orbit 行动清单（更新版）

按优先级排列。P0 = 立刻可做，P1 = 本迭代，P2 = 下迭代，P3 = Backlog。

### P0 —— 直接集成，零或极低适配成本

| # | 行动 | 来源 | 方案 | 预估 |
|---|------|------|------|------|
| 1 | **集成 AnySearch MCP** | 文章 2 | `knowledge/` 添加 AnySearch MCP connector，作为第四搜索后端 | 1h |
| 2 | **注册 AnySearch 免费额度** | 文章 2 | anysearch.com 注册，1000 次/天，验证 MCP 可用性 | 15min |
| 3 | **研究 UE MCP Toolset Registry 源码** | 文章 5 | 阅读 Epic 官方 MCP 插件 + GenOrca Domain Action 实现，提取可复用的工具发现/注册模式 | 2h |

### P1 —— 架构增强，本迭代可完成

| # | 行动 | 来源 | 方案 | 预估 |
|---|------|------|------|------|
| 4 | **Goal Mode 闭环升级** | 文章 1 | `goal/` + `goal_judge/` 加入规划阶段（自动拆里程碑）+ 每步验证 | 2-3d |
| 5 | **Shell AST 安全分析** | 文章 1 | 引入 tree-sitter-bash，在 `sandbox/` 和 `security/` 之间加 shell 命令 AST 分析层 | 1-2d |
| 6 | **成本可观测性 TUI** | 文章 3 | 新建 `observability/tui/` 或独立工具，用 OpenTab 的 store 契约模式读取 Orbit 轨迹数据 | 3-5d |
| 7 | **Subagent 成本归属** | 文章 3 | `compose/` 编排时注入 parent_id，`observability/` 支持递归成本汇总 | 1-2d |
| 8 | **Domain Action 工具模式** | 文章 5 | `tools/` 模块引入 action/params 路由模式，避免工具列表上下文膨胀 | 1-2d |
| 9 | **沙箱执行结构化错误反馈** | 文章 5 | `sandbox/` 执行失败时返回结构化错误（位置+类型+建议），支持 AI 修正→重试闭环 | 1d |
| 10 | **记忆向量语义搜索** | 文章 1 | `memory/` 引入 BGE 向量搜索 + BM25 → RRF 混合融合。补齐当前纯 BM25 关键词检索的短板（尤其中文 CJK） | 0.5d |
| 11 | **记忆自动提取** | 文章 1 | `memory/` 加 post-execution hook：执行完成 → 扫描轨迹 → 自动提取关键事件 → record_event() + auto-tag。解决当前需手动调用 record_event() 的问题 | 1d |

### P2 —— 增强优化，下迭代

| # | 行动 | 来源 | 方案 | 预估 |
|---|------|------|------|------|
| 12 | **重复工具调用熔断规则** | 文章 1 | `resource_guard/` 添加同签名工具调用次数计数器，≥4 次强制熔断 | 0.5d |
| 13 | **证据驱动验证层** | 文章 1+5 | L7 沙箱执行后加确定性验证步骤（文件存在/内容校验/退出码）；UI 测试加入 Visual Review Loop（截图对比） | 1-2d |
| 14 | **AnySearch 前置筛选逻辑** | 文章 2 | 借鉴同源衰减+信息密度仲裁，优化 `knowledge/` 的多源结果融合 | 1-2d |
| 15 | **CachedStore 缓存层** | 文章 3 | `observability/` 轨迹数据加 fingerprint 缓存 | 0.5d |
| 16 | **What-if 模型成本对比** | 文章 3 | `gateway/` 的 T1/T2/T3 路由加入 per-model 成本可视化 | 1d |
| 17 | **代码图谱 MCP 暴露** | 文章 5 | `graph/` 代码图谱暴露为 MCP Resource，Agent 写代码前查询验证 API 存在性 | 1d |
| 18 | **Toolset Registry 双层注册** | 文章 5 | `tools/` 支持编译型（内置）+ 脚本型（用户自定义 Python）双层工具注册 | 2d |

### P3 —— Backlog

| # | 行动 | 来源 | 方案 |
|---|------|------|------|
| 19 | Skill 自动发现 | 文章 1 | `compose/` 支持扫描用户目录自动发现 Markdown Skill |
| 20 | Web Twin 报告导出 | 文章 3 | `observability/` 支持 `--html` 生成自包含成本报告 |
| 21 | 事故归档规范 | 文章 1 | Orbit 自身开发流程加入 `docs/audit/` 事故归档 |
| 22 | MCP-to-Application 通用桥接框架 | 文章 5 | 抽象"AI ↔ MCP Bridge ↔ 目标应用"为通用模式，支持集成第三方 GUI |

---

## 关键提醒：集成风险控制

基于附录 B 的风险评估，任何外部集成必须遵循三条硬性规则：

1. **关键路径不能依赖单一外部服务**。AnySearch 必须配 fallback（本地搜索降级）
2. **开源优先，闭源作为可选增强**。核心功能不能绑在闭源产品上
3. **每个集成点加熔断**。外部服务超时/失败 → 自动降级，不阻断 Agent 主循环

---

## 关键外部资源

| 资源 | 链接 | 用途 |
|------|------|------|
| AnySearch 官网 | http://www.anysearch.com | Agent 搜索 API/MCP |
| AnySearch GitHub | https://github.com/anysearch-ai | 开源代码 |
| Zerox Agent GitHub | https://github.com/ZeroxZhang/zerox-agent | 单人 Agent 全栈参考实现 |
| OpenTab GitHub | https://github.com/hamidi-dev/opentab | 成本 TUI 参考实现 |
| OpenTab PyPI | `opentab-ai` | `uvx --from opentab-ai opentab --demo` |
| tree-sitter-bash | https://github.com/tree-sitter/tree-sitter-bash | Shell AST 解析库 |
| Epic 官方 MCP 文档 | https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor | UE 5.8 MCP 插件 |
| PrismMCP | https://github.com/Asara-Technologies/prism-mcp | 最大覆盖面 UE MCP（1710 命令） |
| GenOrca/unreal-mcp | https://github.com/GenOrca/unreal-mcp | Domain Action 模式参考（253 动作/21 域） |
| UE-MCP (db-lyon) | https://github.com/db-lyon/ue-mcp | YAML 工作流引擎参考 |
| ultimateunrealenginemcp | https://github.com/jeebus87/ultimateunrealenginemcp | Visual Review Loop 参考实现 |
| IvanMurzak/Unreal-MCP | https://github.com/IvanMurzak/Unreal-MCP | Blueprint/C++ 编译反馈闭环参考 |
| unreal-api-mcp (PyPI) | https://pypi.org/project/unreal-api-mcp/ | API 文档防幻觉 MCP Server（114K+ 记录） |

---

## 附录：Orbit 架构对照速查

| Orbit 模块 | 本文相关借鉴 |
|-----------|------------|
| `goal/` + `goal_judge/` | Zerox Goal Mode 闭环 |
| `memory/` | Zerox 五层记忆 + FTS5/RRF |
| `sandbox/` + `security/` | Zerox Shell AST 分析；UE MCP 结构化错误反馈闭环 |
| `resource_guard/` | Zerox 重复工具调用熔断 |
| `hallucination/` L1-L9 | Zerox 证据驱动验证；UE MCP Visual Review Loop 截图验证；unreal-api-mcp API 签名防幻觉 |
| `knowledge/` | AnySearch MCP 集成 + 前置筛选；UE MCP 代码图谱作为 MCP Resource |
| `observability/` | OpenTab Store 契约 + 成本 TUI |
| `compose/` | OpenTab Subagent 成本归属 |
| `gateway/` | OpenTab What-if 模型成本对比 |
| `compose/` SKILL.md | Zerox Skill 自动发现 |
| `tools/` | UE MCP Toolset Registry 双层注册 + Domain Action 模式 |
| `graph/` | 代码图谱暴露为 MCP Resource（事前幻觉预防） |
| `api/` | MCP Bridge 三层架构参考（AI ↔ Bridge ↔ Target App） |

---

## 附录 B：各项目局限性与风险评估

> 调研不能只看优点。以下对每个项目进行"对抗性审查"——
> 识别其脆弱点、技术债务、商业模式风险、生态锁定风险。
> 目的不是否定这些项目，而是 Orbit 在借鉴/集成时**知道哪里有坑**。

### B.1 Zerox Agent —— 单人项目的结构性风险

| 风险维度 | 详情 | 严重程度 |
|----------|------|---------|
| **Bus Factor = 1** | 单人开发，无团队。作者离职/生病/失去兴趣 → 项目死亡 | 🔴 致命 |
| **平台锁定** | 仅支持 macOS。无 Windows/Linux 计划。Apple 签章未完成 | 🔴 致命 |
| **代码质量** | 14.3 万行 TypeScript，35 天写完。无人审查。大概率存在隐蔽 bug 和架构债务 | 🟡 严重 |
| **自研内核** | 拒绝 LangChain 等社区框架，1570 行自研 Agent 循环。好处是可控，风险是缺少社区审查的安全补丁和边界 case 覆盖 | 🟡 严重 |
| **无测试框架** | 全文中未提及任何测试。35 天写 14 万行代码不可能有时间写测试 | 🟡 严重 |
| **记忆自动提取无验证** | "自动从执行轨迹提取"听起来好，但提取质量、去噪、去重均未验证。可能产生垃圾记忆污染检索 | 🟡 严重 |
| **商业模式缺失** | 开源但无收入模型。长期维护动力存疑 | 🟢 一般 |

**Orbit 借鉴时的注意事项**：
- Goal Mode 闭环、五层记忆、Shell AST 安全——这三个设计**思路**是对的，但**实现质量未知**
- 不要直接搬代码，只搬设计模式
- Zerox 的"自动记忆提取"是黑盒——Orbit 实现时需要加质量评估机制

### B.2 AnySearch —— 闭源 SaaS 的锁定风险

> **2026-07-13 补充：GitHub 仓库审计结果**

#### "开源"真相

GitHub `anysearch-ai/anysearch-mcp-server`（1519 ⭐）**只含 5 个非代码文件，repo 总大小 22 KB**：

```
.gitignore    384 bytes
LICENSE       11 KB   (Apache 2.0 空壳)
NOTICE         95 bytes
README.md     12 KB   (文档)
SECURITY.md    1 KB   (文档)
---
总大小：22 KB —— 0 行搜索引擎源码。
```

文章里写的"项目地址：https://github.com/anysearch-ai" 指向的就是这个空壳仓库。**AnySearch 是完全闭源的商业 SaaS 产品**。搜索引擎的核心（20+ 垂直数据源集成、自建索引、融合排序算法、意图路由引擎）一行代码都没有公开。

#### 社区逆向结果

社区项目 [luoqianyi/easy_anysearch_skill](https://github.com/luoqianyi/easy_anysearch_skill)（36 ⭐）已扒出完整 API 细节：

**API 端点**：`POST https://api.anysearch.com/v1/search`
**请求格式**：`{"query": "关键词", "max_results": 10}`
**认证**：不需要 API Key 即可匿名调用（有速率限制），注册后加 `Authorization: Bearer <key>` header
**响应格式**：
```json
{
  "code": 0,
  "data": {
    "results": [
      {"title": "标题", "url": "链接", "description": "摘要", "content": "正文（Markdown）"}
    ]
  }
}
```

**关键发现**：API 本身很简单——就是一个带搜索接口的 HTTP POST。返回值是已清洗的 Markdown 结构化内容。核心价值在服务端（数据源集成 + 排序算法），不在协议层。

#### 可逆工程分析

| 可逆的 | 不可逆的 |
|--------|---------|
| API 协议和响应格式 | 20+ 垂直数据源的实际集成代码 |
| MCP tool schema | 自建索引体系 |
| 意图路由的设计思路 | 融合搜索算法的具体参数 |
| 输出数据结构 | 数据源的商业合同和访问权限 |

**结论**：API 协议本身很简单——不需要"逆向"，社区已经扒干净了。但 AnySearch 的核心价值（垂直数据源 + 排序算法）是服务端闭源资产，无法逆向。

#### Orbit 自建替代方案

AnySearch 的架构思路（搜索前预处理）有价值，但可以用开源组件拼装：

| AnySearch 组件 | Orbit 替代方案 | 难度 |
|---------------|---------------|------|
| 通用网页搜索 | SearXNG（开源，可自托管）/ DuckDuckGo API | 低 |
| 代码搜索 | GitHub Search API + GitLab API | 低 |
| 学术搜索 | Semantic Scholar API / arXiv API | 低 |
| 金融/企业数据 | 公开工商 API + 财经数据源 | 中 |
| 意图路由 | LLM 判断查询类型 → 选数据源（~50 行 prompt） | 低 |
| 同源衰减算法 | 按域名分组，同域名结果降权（~30 行 Python） | 低 |
| 信息密度仲裁 | 正文长度 + 结构化程度评分（~40 行 Python） | 低 |
| Markdown 清洗 | `readability-lxml` 正文提取 + `html2text` | 低 |
| MCP/API/Skill 接口 | Orbit 已有的 MCP 基础设施 | ✅ 已有 |

**建议架构**：Orbit 自建 `knowledge/search/` 子模块，AnySearch 只作为可选后端之一（有 API Key 时优先用，无 Key 或不稳时自动降级到开源源）。

| 风险维度 | 详情 | 严重程度 |
|----------|------|---------|
| **闭源商业产品** | 不是开源项目。核心搜索架构、自建索引、融合算法全部闭源 | 🔴 致命 |
| **供应商锁定** | Agent 的核心能力（外部信息获取）依赖单一商业 API。AnySearch 涨价/停服/变更 API → Orbit 信息获取能力断裂 | 🔴 致命 |
| **免费层天花板** | 1000 次/天看似多，多 Agent 并行搜索时消耗极快（一次任务可能触发 5-10 次搜索） | 🟡 严重 |
| **数据源依赖** | 20+ 垂直数据源都是第三方的。数据源变更/下架/收费 → AnySearch 搜索质量下降 | 🟡 严重 |
| **冷启动问题** | 新领域/新问题类型可能无对应垂直数据源，回退到通用搜索时质量未知 | 🟡 严重 |
| **无自托管** | 不支持私有化部署。高敏项目（企业财务数据、安全审计）无法使用 | 🟡 严重 |
| **高并发瓶颈** | 300 QPS 时 CPU 85%，需横向扩展。大项目可能触及性能天花板 | 🟢 一般 |
| **成立仅 2 个月** | 产品太新，长期稳定性、SLA、数据源维护能力均未经验证 | 🟢 一般 |

**Orbit 集成策略（修正）**：
- ❌ **不要作为唯一外部信息源**——供应商锁定风险太大
- ✅ **作为 knowledge/ 的多个后端之一**——与 BGE 本地搜索、TF-IDF 降级平级
- ✅ **加 fallback 链**：AnySearch 超时/失败 → 自动降级到本地搜索，Agent 不受影响
- ✅ **缓存搜索结果**：相同查询不重复调用，减少 API 消耗

### B.3 OpenTab —— 单人工具的可持续性风险

| 风险维度 | 详情 | 严重程度 |
|----------|------|---------|
| **Bus Factor = 1** | 单人开发（hamidi-dev）。项目死亡风险同 Zerox | 🔴 致命 |
| **curses TUI 天花板** | 纯终端 UI，无法做现代 Web 仪表盘。跨平台兼容性差（Windows 需额外包） | 🟡 严重 |
| **只读限制** | 只能看已有的工具日志数据。不能添加新的数据采集点、不能做实时告警 | 🟡 严重 |
| **无实时监控** | 手动刷新。无法做"预算超限自动告警"、"session 成本异常检测" | 🟡 严重 |
| **单用户** | 无团队/组织视图。无法跨项目聚合 | 🟢 一般 |
| **依赖工具日志格式** | Claude Code / OpenCode 等工具更新日志格式 → OpenTab 解析器可能失效。需持续跟进适配 | 🟢 一般 |
| **无预测能力** | 只能展示历史数据，不能预测"这个月底会花多少钱" | 🟢 一般 |

**Orbit 借鉴时的注意事项**：
- Store 契约模式是好的——Orbit 可以**自己实现**类似抽象层，不依赖 OpenTab
- 不要直接把 OpenTab 作为 Orbit 的 observability 前端——它太局限了
- 学它的设计模式（unified store + cached fingerprint + 双 cost snapshot），用自己的技术栈实现

### B.4 UE MCP 生态 —— 碎片化与安全风险

| 风险维度 | 详情 | 严重程度 |
|----------|------|---------|
| **生态碎片化** | 6+ 个互不兼容的实现，工具命名/参数 schema/错误格式各不相同。AI Agent 需 per-plugin 配置 | 🔴 致命 |
| **Epic 官方插件不成熟** | 实验性、API 不稳定、功能不完整、HTTP+SSE only、无并发执行 | 🔴 致命 |
| **无认证机制** | Epic 官方和多个第三方插件默认无认证。任何本地进程可发送 MCP 请求 | 🔴 致命 |
| **命令注入漏洞** | ChiR24/Unreal_mcp 等曾存在命令注入和路径穿越漏洞，已修复但说明代码成熟度低 | 🔴 致命 |
| **HTTP 200 欺骗** | 错误返回 HTTP 200 + 内嵌错误文本。AI Agent 无法程序化区分成功/失败 | 🟡 严重 |
| **启动竞态** | MCP Server 在接受连接时 toolsets 未注册完毕。AI 连接过早只能看到 1/55 的工具 | 🟡 严重 |
| **Blueprint 编辑缺口** | 缺少 replace_call_function_node、list_nodes 等关键工具。AI 无法安全重构已有 Blueprint | 🟡 严重 |
| **"No AI" 许可证风险** | Marketplace 资产标注"No AI"后，MCP 驱动的 AI 操作可能违反许可。Epic 未澄清 | 🟡 严重 |
| **UE 版本锁定** | 每个插件只支持特定 UE 版本范围。UE 升级 → 插件可能失效 | 🟢 一般 |
| **缺少事务安全** | 无 snapshot/diff/rollback 工具。AI 的破坏性操作不可逆 | 🟢 一般 |

**Orbit 借鉴时的注意事项**：
- UE MCP 生态的最大价值是**架构验证**（MCP 可以桥接复杂 GUI 应用），不是拿来即用
- UE MCP 的安全问题（无认证、命令注入、HTTP 200 欺骗、启动竞态）是**Orbit 自己要避免的坑**——每一项都应该对照检查 Orbit 的 MCP 相关模块
- 碎片化问题的根因是**缺少工具命名/错误格式/传输协议的标准**——Orbit 在设计自己的 MCP 暴露层时应该制定内部标准

### B.5 综合风险评估矩阵

| 风险类型 | Zerox | AnySearch | OpenTab | UE MCP |
|----------|-------|-----------|---------|--------|
| 单人依赖 (Bus Factor) | 🔴 | 🟢 | 🔴 | 🟢 |
| 供应商锁定 | 🟢 | 🔴 | 🟢 | 🟡 (Epic) |
| 平台限制 | 🔴 (macOS only) | 🟢 | 🟡 (curses) | 🔴 (UE only) |
| 代码成熟度 | 🔴 (35天) | 🟡 (2月) | 🟢 | 🔴 (实验) |
| 安全漏洞 | 🟡 | 🟢 | 🟢 | 🔴 |
| 缺少测试 | 🔴 | 🟡 | 🟡 | 🔴 |
| 生态碎片化 | 🟢 | 🟢 | 🟢 | 🔴 |
| 商业模式风险 | 🔴 | 🔴 | 🟢 | 🟡 |
| 闭源/黑盒 | 🟢 (开源) | 🔴 (闭源) | 🟢 (开源) | 🟡 (部分) |

**结论**：四个项目中**没有一个可以直接作为 Orbit 的"关键依赖"**。都只能作为设计参考或非关键集成。AnySearch 的供应商锁定风险最高——必须加 fallback。UE MCP 的安全负债最重——Orbit 对照检查。
