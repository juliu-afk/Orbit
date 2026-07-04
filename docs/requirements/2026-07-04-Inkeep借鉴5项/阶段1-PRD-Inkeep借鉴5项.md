# 阶段1 PRD — Inkeep 竞品分析借鉴（5 项）

> 日期：2026-07-04 | 来源：`docs/research/research-inkeep-analysis.md` §6
> 基线：不集成 Inkeep SDK。借鉴设计模式，自建增强。

## 1. 背景

Inkeep 是 TypeScript Agent 构建平台（SaaS），Orbit 是 Python 自研 Agent 框架。技术栈不兼容，不集成。但 Inkeep 的 5 项设计模式可直接提升 Orbit 的成本效率、上下文管理、可观测性。

## 2. 用户故事（P0/P1/P2）

### P0 — 立刻做（低成本、高收益）

**US-1: 三层模型路由**
> 作为调度器，我希望按任务类型自动选择模型（推理用 Opus/GLM-5.2，结构化输出用 Haiku/Flash，摘要用 nano），以便节省 40-60% token 成本且不降低任务质量。

- 现有基础：`gateway/routing.py` 已有策略路由 + `client.py` 已有 Tier 模型体系
- 缺口：路由按 `RoutingStrategy` 枚举选择，但调度器调用时只传 strategy flag，没有 task context。`orchestrator.py` 知道自己在做什么类型的任务，但没告诉 gateway。
- 不涉及 UI

**US-2: Artifact 三级分级存储**
> 作为防幻觉层，我希望图谱查询结果按 preview（轻量进上下文）/ full（按需查询）/ oversized（拒绝+告警）三级分级，以便防止上下文溢出且保持信息不丢失。

- 现有基础：`hallucination/l3_entropy.py` 已有 token 监控 + 熔断
- 缺口：熔断只管"超了没"，不管"怎么裁"。六图谱查询结果无分级，全量进上下文
- 不涉及 UI

### P1 — 短期做（1-2 周）

**US-3: Skill 按需加载**
> 作为 Agent，我希望通过 `load_knowledge` tool 按需从知识图谱拉取相关子图，而非全量预加载到 prompt，以便减少上下文膨胀。

- 现有基础：`knowledge/engine.py` 已有 exact/semantic/hybrid 查询
- 缺口：查询由外部（调度器）驱动，Agent 无主动拉取能力。知识全量预注入或完全不注入
- 不涉及 UI

### P2 — 中期（需要前端工作）

**US-4: Trace 嵌入驾驶舱**
> 作为运维者，我希望在 Vue3 驾驶舱的 Ops 面板中看到完整任务 Trace（调度决策 → Agent 调用 → 工具执行 → 验证结果），用 DAG 图展示，点击节点看详情。

- 现有基础：`observability/` 有 OTEL collector + audit logger + metrics。前端 `DagCanvas.vue` 已有 DAG 渲染（vis-network）
- 缺口：observability 层无结构化 trace 数据模型（调度器→Agent→工具→验证链路）。前端 DAG 只展示任务节点状态，无 trace 详情
- 涉及前端

**US-5: No-Code 配置面板**
> 作为运维者，我希望在驾驶舱中通过 YAML/表单编辑 Prompt 模板、模型选择、熔断阈值，运行时热更新，无需重新构建 exe。

- 现有基础：`OpsPanel.vue` 已有备份/版本/SOP 展示
- 缺口：无配置编辑 UI。所有配置硬编码或环境变量，改一行需重启
- 涉及前端

## 3. 验收标准

### US-1: 三层模型路由

**方案选择**：四种候选方案对比——

| 方案 | 机制 | 优点 | 缺点 | 采用 |
|------|------|------|------|------|
| A. Task-Type 硬编码 | reasoning→Pro, structured→Flash, summary→nano | 简单可预测 | 粒度粗 | **Phase 1** |
| B. 能力匹配 | 模型声明能力，任务声明需求，自动匹配 | 加模型不改路由 | 能力评分主观 | ❌ 过度设计 |
| C. 成本预算制 | 每任务设 token 预算，预算内选最优 | 总成本可控 | 预算估不准 | ❌ |
| D. Agent 声明 Tier | Agent 传 tier:1/2/3，gateway 映射 tier→model | Agent 最了解需求 | 难统一管理 | Phase 2 |

**Phase 1 采用 A，映射表写成 YAML 可配置（US-5 配置面板管）。Phase 2 引入 Agent 显式声明 Tier。**

| # | 验收标准 |
|---|---------|
| S1.1 | `TaskModelRouter` 接收 task_type（reasoning/structured_output/summarization），返回对应模型 |
| S1.2 | 调度器 `orchestrator.py` 调用 LLMClient 时传入 task_type |
| S1.3 | reasoning → 最强（GLM-5.2 / DS V4 Pro），structured_output → 便宜（DS V4 Flash），summarization → 最便宜（GLM-4.7 Flash）|
| S1.4 | 映射表从 YAML 配置文件读取（非硬编码），US-5 配置面板可编辑 |
| S1.5 | 模型不可用时自动降级至 fallback（现有 circuit_breaker 逻辑不变）|
| S1.6 | 单元测试覆盖三种 task_type 路由 + 降级场景 + 自定义映射 |

### US-2: 三级分级存储

**阈值策略**：初始值 `preview ≤ 2KB / full ≤ 64KB / oversized > 64KB`。运行时动态调整——

```
- preview 命中率 < 80%（大部分用例需要调 full）→ 升 preview 阈值
- oversized 触发率 > 10%（大量查询被拒）→ 升 oversized 阈值
- 上下文窗口利用率 > 90% → 降阈值
```

阈值存 SQLite，US-5 配置面板可手动覆盖。不写死。

| # | 验收标准 |
|---|---------|
| S2.1 | 图谱查询结果附带 `tier` 字段：preview（≤2KB 摘要）/ full（完整结果）/ oversized（拒绝加载）|
| S2.2 | preview 自动进入 Agent 上下文，full 通过 tool 按需查询，oversized 返回错误+建议细化查询 |
| S2.3 | 三级阈值可配置，初始值 preview≤2KB / full≤64KB / oversized>64KB |
| S2.4 | 动态调整逻辑：统计命中率+触发率 → 自动调整阈值（存 SQLite，可手动覆盖）|
| S2.5 | 与现有 L3 熔断器互补——熔断管超限，分级管信息密度 |
| S2.6 | 单元测试覆盖三种 tier 分支 + 动态调整 + oversized 告警路径 |

### US-3: 按需加载
| # | 验收标准 |
|---|---------|
| S3.1 | Agent 拥有 `load_knowledge` tool，参数 domain + concept，返回结构化知识片段 |
| S3.2 | `load_knowledge` 内部调用 `KnowledgeEngine.query()` |
| S3.3 | 未找到匹配知识时返回明确"未找到"信号（而非空字符串）|
| S3.4 | 单元测试覆盖 tool 注册 + 调用 + 未找到路径 |

### US-4: Trace 驾驶舱

**Trace 数据是后端存储（SQLite），前端只消费展示。** 三层保留策略：

| 周期 | 存储 | 粒度 |
|------|------|------|
| 0-7 天（默认） | SQLite | 完整 span（每个 tool call 独立 span）|
| 8-30 天 | SQLite | 聚合摘要（只保留 task 级，drop 子 span）|
| >30 天 | 可选导出为 OTEL JSON 文件 | 用户手动触发导出 |

保留天数可通过 US-5 配置面板调整。"超过 7 天"不是永远丢失——8-30 天有 task 级摘要，30 天后可导出归档。

| # | 验收标准 |
|---|---------|
| S4.1 | `observability/` 新增 `TraceSpan` 数据模型：span_id, parent_span_id, component, action, input_summary, output_summary, duration_ms, status |
| S4.2 | 调度器/Agent/工具执行点埋 span（至少覆盖 orchestrator→task_runner→sandbox 链路）|
| S4.3 | API 端点 `GET /observability/trace/{task_id}` 返回完整 trace tree |
| S4.4 | 三层保留：7 天完整 span + 30 天 task 摘要 + 可导出 OTEL JSON |
| S4.5 | 前端 OpsPanel 新增 "Trace 查看器" Tab——DAG 图展示 trace 链路，点击节点查看 span 详情 |
| S4.6 | E2E 测试：创建任务→查看 trace→验证节点完整 |

### US-5: 配置面板

**需要版本管理+回滚**。`config_history` 表存线性历史——回滚时读旧版本→写为新版本（不删历史）。不追求 Git 级分支合并。

| # | 验收标准 |
|---|---------|
| S5.1 | 驾驶舱新增 "配置" 页面/路由 |
| S5.2 | YAML 编辑器（CodeMirror 或 Monaco）嵌入，编辑 Prompt 模板/模型选择/熔断阈值 |
| S5.3 | 保存后通过 API `PUT /api/v1/config` 持久化到 SQLite |
| S5.4 | 后端读取配置热更新（不重启）|
| S5.5 | 格式错误时返回校验错误（HTTP 400 + 行列号），不静默失败 |
| S5.6 | `config_history` 表：config_id, key, value, version, updated_at, updated_by |
| S5.7 | 回滚操作：选择历史版本 → 预览 diff → 确认 → 写入为最新版本 |
| S5.8 | 并发编辑：乐观锁（时间戳校验），冲突时提示用户刷新

## 4. 成功指标

- **US-1**：单次复杂任务 LLM 成本降低 ≥30%（reasoning + structured_output + summarization 分离后 vs 全部用 Pro 模型）
- **US-2**：超大图谱查询（>1000 节点）时上下文 token 用量 ≤ 全量注入的 20%
- **US-3**：Agent prompt 中预加载知识 token 减少 ≥50%
- **US-4**：任务排障时间（从问题发现到定位根因）降低 ≥40%
- **US-5**：Prompt 模板调整从"改代码+构建exe+部署"（≥15分钟）降为"UI编辑+保存"（≤30秒）

## 5. Non-Goals

- ❌ 不集成 Inkeep SDK / MCP Server / OpenKnowledge
- ❌ 不实现 Inkeep 的 Sub-Agent 模型（Orbit 已有 `agents/` 工厂）
- ❌ 不实现 Inkeep 的双向同步（code ⇄ UI push/pull）——成本过高，Orbit 不需要
- ❌ 不改变调度器状态机核心逻辑
- ❌ 不修改防幻觉 L1-L8 判定规则（US-2 是互补层，不影响现有层）

## 6. 边缘情况

| 场景 | 预期行为 |
|------|---------|
| US-1: 所有模型都不可用 | circuit_breaker 熔断后返回错误，任务挂起人工介入 |
| US-1: task_type 未知 | 回退到 default_model（DS V4 Pro） |
| US-2: 图谱查询结果恰好等于阈值 | preview 阈值 `<` 2KB（不含等于），preview=2KB 进 full 级 |
| US-2: oversized 结果 | 返回 `{tier: "oversized", error: "result_too_large", hint: "请细化查询条件"}` |
| US-3: 知识库为空 | `load_knowledge` 返回 "knowledge base is empty" |
| US-3: 并发 Agent 同时查询 | `KnowledgeEngine` 读操作无锁，支持并发 |
| US-4: trace 数据量过大 | 超过 7 天的 trace 自动清理（SQLite TTL） |
| US-5: 配置格式错误 | HTTP 400 + 具体错误行/列，配置不更新 |
| US-5: 并发编辑 | last-write-wins，保存时时间戳校验（乐观锁） |

## 7. 待确认问题（已闭合）

1. **US-1 模型映射表** → **已决策**：Phase 1 用 Task-Type 硬编码（方案 A），映射表 YAML 可配置。Phase 2 引入 Agent 显式声明 Tier（方案 D）。
2. **US-2 三级阈值** → **已决策**：初始值 preview≤2KB / full≤64KB / oversized>64KB。运行时统计命中率+触发率→动态调整。存 SQLite，US-5 可手动覆盖。
3. **US-5 配置面板** → **已决策**：需要版本管理+回滚。Phase 1 用 SQLite 线性历史（`config_history` 表），Phase 2 切 Git 后端（配置即 YAML 文件 + git 仓库，天然支持 branch/merge/conflict resolution）。架构预留：配置存 YAML 文件而非 SQLite blob。
4. **US-4 Trace 保留期** → **已决策**：三层保留策略——7天完整span + 30天task摘要 + 可导出OTEL JSON。保留天数通过US-5可配置。"超过7天"不是永久丢失。

---

> **阶段门禁**：PRD 完成。等待用户确认后进入阶段 2（技术方案）。
