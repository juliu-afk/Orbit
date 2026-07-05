# Inkeep 竞品/参考分析报告

> 日期：2026-07-03 | 来源：官方文档 + GitHub + 第三方评测 | 与 Orbit 对照
>
> 基础：https://github.com/inkeep/agents (Elastic 2.0) | 官方：https://inkeep.com | 文档：https://docs.inkeep.com

## 1. 一句话定位

Inkeep = 带 No-Code Visual Builder 的 AI Agent 构建**平台**（不是库/框架）。锚定客户支持 + GTM + 运营场景。Orbit 锚定软件开发自循环场景。两者都是 Agent 系统但目标用户和问题域不同。

## 2. 公司背景

| 维度 | 数据 |
|------|------|
| 成立 | 2023 |
| 融资 | $13M+ |
| 客户 | Anthropic, Solana, PostHog, Midjourney, Clerk, Clay |
| License | SDK 部分 Elastic 2.0 开源；托管平台专有 |
| 仓库 | `github.com/inkeep/agents`（990+ releases，2026-04 最新） |
| 竞品 | Kapa.ai, Intercom Fin, CrewAI(间接), LangGraph(间接) |

## 3. 架构

```
┌──────────────────────────────────────────────┐
│  agents-manage-ui (Visual Builder)            │
│  拖拽式 Agent 编排，非技术人员用               │
├──────────────────────────────────────────────┤
│  agents-sdk (@inkeep/agents-sdk)              │
│  TypeScript 声明式定义 Agent/Tool/MCP          │
├──────────────────────────────────────────────┤
│  agents-cli                                   │
│  inkeep push ⇄ pull 双向同步                  │
│  ← Inkeep 最独特的差异化能力                  │
├──────────────────────────────────────────────┤
│  agents-api (REST)                            │
│  Agent 执行 / 会话状态 / OTEL 追踪             │
│  底层：Vercel AI SDK + SQLite/Drizzle ORM      │
├──────────────────────────────────────────────┤
│  agents-ui (@inkeep/cxkit)                    │
│  React 聊天组件，嵌入产品前端的 Widget          │
└──────────────────────────────────────────────┘
```

## 4. 核心能力

### 4.1 双模式 + 双向同步（最大杀器）

| 模式 | 用户 | 能力 |
|------|------|------|
| Visual Builder (No-Code) | PM/运营/非技术人员 | 拖拽配 Agent、调 prompt、上线 |
| TypeScript SDK (Code) | 工程师 | 声明式定义 Agent、自定义 Tool、CI/CD |

**`inkeep push`**：代码 → 编译 → 同步到 Visual Builder。PM 在 UI 里立刻看到最新 Tool。

**`inkeep pull`**：PM 在 UI 调了 Agent → CLI 检测差异 → 生成/重构代码文件 → 提交 Git。

> 核心价值：Agent 系统中**非技术团队想调行为但改不了代码** + **工程师不想替 PM 调 prompt 参数**的结构性矛盾，Inkeep 是第一个真正解决的。

### 4.2 Agent 模型

**Sub-Agent 架构**：每个 Sub-Agent 是独立上下文单元——自己的 prompt + tool 列表 + model 配置。通过状态机 handoff，不是图遍历也不是顺序执行。

```typescript
const troubleshooter = subAgent({
  id: "troubleshooter",
  description: "诊断用户报告的问题",
  canUse: () => [stripeMcp, zendeskMcp],
  prompt: `你是故障排查专家...`,
});

const triageAgent = agent({
  id: "triage",
  defaultSubAgent: troubleshooter,
  subAgents: () => [troubleshooter, billingAgent, feedbackAgent],
});
```

**三层 Model 配置（2026）：**

| 槽位 | 用途 | 模型选择 |
|------|------|---------|
| `base` | 主力推理 | Claude Opus / GPT-5 等前沿模型 |
| `structuredOutput` | JSON 结构化输出 | Claude Haiku / GPT-4.1-mini（便宜） |
| `summarizer` | 批量摘要 | GPT-5.4-nano / Gemini 2.5 Flash-Lite（最便宜） |

效果：单次对话三种模型混跑，节省 40-60% token 成本。

### 4.3 知识 & RAG

- **Unified AI Search**：自动索引文档/帮助中心/Notion/Confluence/Git 仓库
- **新内容分钟级自动收录**
- **AI Content Writer**：检测知识空白 → 自动生成草稿 → 人类审核后入库（闭环）
- **内联引用**：每条回答带来源链接

### 4.4 Tool 体系

| 类型 | 说明 |
|------|------|
| **Function Tools** | 自定义 TS 函数，Node.js 沙箱隔离执行 |
| **MCP Tools** | 1-Click 对接 Stripe/HubSpot/Zendesk/Slack/Jira，OAuth 托管 (Nango) |
| **Skills** | `SKILL.md` (YAML 头 + Markdown 指令), `always-loaded` / `on-demand` 两种 |
| **Context Fetchers** | 会话启动前预取外部数据 → 注入 system prompt（被动，Agent 不能主动调） |

### 4.5 结构化输出

| 组件 | 作用 |
|------|------|
| **Data Components** | Agent 返回结构化 UI（表单/卡片/列表），渲染为 React 组件而非 Markdown |
| **Artifact Components** | 自动记录 Tool 调用来源+内容+元数据，分 preview(进上下文)/full(按需查)/oversized(阻止加载) 三级 |

> Artifact 三级分级存储是亮点——解决 Agent 上下文窗口管理的通用难题。

### 4.6 可观测性

- 底层：OpenTelemetry（SigNoz 本地/云）
- 自动打点：Agent Transfer → Tool → LLM Call → Artifact 全部同一 Trace
- Trace 直接嵌在 Visual Builder UI 里——PM 也能看到 Agent 决策路径
- Anthropic prompt caching 默认开启

## 5. 与同类框架对比

| 维度 | Inkeep | CrewAI | LangGraph | Orbit |
|------|--------|--------|-----------|-------|
| 类别 | SaaS 平台 | Python 框架 | Python 框架 | Python 自研框架 |
| Agent 模型 | Sub-Agent + 状态机 handoff | 角色-based team | 有向图状态机 | 调度器状态机 + Agent 工厂 |
| No-Code UI | ✅（核心竞争力） | ❌ | ❌ (LangSmith Studio 有限) | ❌（Vue3 驾驶舱仅监控） |
| 双向同步 | ✅ push/pull | ❌ | ❌ | ❌ |
| 图谱 | ❌ (RAG 平替) | ❌ | ❌ (Checkpoint 子图) | ✅ 六图谱 |
| 防幻觉体系 | ❌（靠 prompt + citation） | ❌ | ❌ | ✅ L1-L9 九层 |
| 熔断 | ❌ | ❌ | ❌ (checkpoint 回滚) | ✅ 毫秒级 |
| 沙箱 | Node.js / Vercel MicroVM | ❌ | ❌ | ✅ Docker |
| 可观测 | OTEL + UI 内嵌 | 有限 | LangSmith | OTEL + structlog |
| License | Elastic 2.0 / 专有 | MIT | MIT | MIT |
| 语言 | TypeScript | Python | Python | Python |
| 最佳场景 | 客服/GTM Agent 助手 | 快速原型 Agent 团队 | 生产级复杂状态机 | 软件开发自循环 |

## 6. Orbit 可借鉴的 5 个设计

### 6.1 Skill on-demand 加载

Inkeep 的 Skill 分 `always-loaded`（常驻 prompt）和 `on-demand`（Agent 通过 `load_skill` tool 主动拉取）。Orbit 的 Agent 角色定义同样面临上下文膨胀问题——所有领域知识预加载到 prompt 浪费 token。

**建议**：在 `src/orbit/agents/` 中实现 `load_knowledge` tool，让 Agent 按需从知识图谱拉取相关子图，而非全量注入。

### 6.2 Artifact 三级分级存储

preview（轻量进上下文）+ full（按需查询）+ oversized（拒绝加载+告警）。Inkeep 用此机制防止上下文溢出。

**建议**：Orbit 六图谱的查询结果做类似分级——子树摘要进 prompt，全图按需查询，超大结果集拒绝并提示细化查询。与现有熔断器（token 计数）互补——熔断管成本安全侧，分级管信息密度侧。

### 6.3 三层 Model 自动分配

Inkeep 按任务类型自动选模型（推理/结构化输出/摘要）。Orbit 的 LiteLLM 网关已支持多模型路由，但没有按任务类型自动分配的逻辑。

**建议**：在 `src/orbit/gateway/` 中实现 `TaskModelRouter`——根据调用上下文（调度器推理 vs 代码生成 vs 日志摘要）自动路由到不同模型，节省 token 成本。

### 6.4 No-Code 配置层（轻量版）

Inkeep 的双向同步是完整方案，Orbit 不需要照搬。但 Orbit 当前全是代码驱动——调度策略/Prompt 模板改一行就得重新构建 exe。

**建议**：在 Vue3 驾驶舱加一个轻量配置面板——YAML/JSON 编辑 + 表单映射，覆盖 Prompt 模板、模型选择、熔断阈值。不追求双向同步，只求运行时热更新。存 SQLite，不需要 CLI push/pull。

### 6.5 Trace 嵌入驾驶舱

Inkeep 的 Visual Builder 直接展示 Agent 决策 Trace。Orbit 的 OTEL 数据进了 structlog 日志，但驾驶舱没有可视化 Trace。

**建议**：在 Vue3 驾驶舱的 `ops/` 组件中加 Trace 面板——一次任务调度的完整链路（调度决策 → Agent 调用 → 工具执行 → 验证结果），用 DAG 图展示，点击节点看详情。OTEL 数据已在，只是缺前端消费。

## 7. 集成可行性结论

| 方案 | 可行性 | 理由 |
|------|--------|------|
| 集成 Inkeep SDK | ❌ 不可行 | TypeScript SDK，Orbit Python；Elastic 2.0 协议限制 |
| 对接 Inkeep MCP Server | ⚠️ 可行但价值有限 | MCP Server 做知识库 RAG 查询，Orbit 已有 `knowledge/` + CodeGraph SQLite |
| 借鉴设计模式自建 | ✅ 推荐 | 6.1-6.5 五点都不需要引入外部依赖，自建成本可控 |
| 作为 Orbit 的外部知识存储 | ⚠️ 过度设计 | Orbit 已用 SQLite 存知识图谱，引入 SaaS RAG 增加延迟和依赖 |

**总结**：不集成。借鉴设计，自建增强。

## 8. 与 OpenKnowledge 的关系

Inkeep 是公司，OpenKnowledge (`inkeep/open-knowledge`) 是其开源 AI Markdown 编辑器（GPL-3.0，Notion/Obsidian 替代品）。OpenKnowledge 与 Orbit 集成不可行：GPL-3.0 vs MIT 协议冲突，且功能与 Orbit 的 `knowledge/` 模块重叠。

## 9. 参考链接

- [Inkeep 官方](https://inkeep.com)
- [Inkeep Agents SDK (GitHub)](https://github.com/inkeep/agents)
- [Inkeep 文档](https://docs.inkeep.com)
- [Inkeep TypeScript SDK](https://docs.inkeep.com/typescript-sdk)
- [Inkeep MCP Server](https://docs.inkeep.com/cloud/mcp/overview)
- [Inkeep vs CrewAI vs LangGraph 对比](https://inkeep.com/blog/agent-frameworks-platforms-overview)
- [Inkeep 用 SigNoz 做可观测](https://signoz.io/blog/inkeep-ai-agent-monitoring/)
