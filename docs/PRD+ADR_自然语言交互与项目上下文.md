# PRD+ADR · 自然语言交互与项目上下文管理

用户只需说一句"支付超时了，修一下" → 系统自动完成上下文识别、需求澄清、PRD生成

---

## Step 0.3增强：项目上下文澄清能力

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | 用户不会按API契约格式提交任务，只会说"支付超时了，修一下"。系统需要从自然语言中提取项目上下文，通过多轮交互澄清意图，最终生成可执行的PRD。当前Step 0.3仅处理需求本身的模糊性，未覆盖项目归属、Issue关联等上下文信息。 |
| **用户故事** | 作为用户，我输入"支付超时了，修一下"，系统自动识别我要处理哪个项目、关联哪个Issue、确认需求理解，然后开始生成方案。整个过程就像跟一位资深程序员对话。 |
| **需求描述** | ① 项目注册表管理项目元数据（项目名、Issue追踪配置、文档来源）。② 文档图谱将项目文档结构化存储，支持语义检索。③ Issue追踪系统通过MCP协议集成（GitHub/Jira/Linear/TAPD）。④ Step 0.3需求澄清增加项目上下文识别能力。⑤ 上下文自动匹配策略：会话历史→关键词→语义检索→用户选择。⑥ 交互界面（驾驶舱/小程序）展示项目上下文卡片。⑦ 代码变更自动关联到Issue，完成闭环。 |
| **范围 (Do/Don't)** | **Do：**项目注册表CRUD、文档图谱schema（pgvector语义索引）、Issue MCP适配层、上下文自动匹配引擎、Step 0.3增强（项目/Issue维度）、交互界面卡片。**Don't：**不实现Issue系统本身的替代（只是集成）；不自动修改项目文档内容。 |
| **数据契约** | **项目注册表：**{project_id, project_name, repo_url, issue_tracker_type, issue_tracker_config, doc_sources, knowledge_bases} |
| | **文档节点：**{doc_id, project_id, doc_path, doc_type, title, content, summary, embeddings(vector 1536)} |
| | **上下文解析结果：**{project, issue, source("session"/"keyword_match"/"semantic_match"), requires_confirmation, candidates} |
| **异常定义** | ① 上下文自动匹配失败 → 展示最近使用项目列表，要求用户选择。② Issue系统不可达 → 降级跳过Issue关联，记录WARNING。③ 文档图谱检索超时(>3s) → 降级跳过文档关联，仅通知用户。 |
| **成功标准→验收** | **SC1:** 项目自动匹配 → **AC1:** 输入"支付超时"，系统30s内返回匹配的项目列表或推荐。 |
| | **SC2:** Issue自动关联 → **AC2:** 系统查询Issue追踪系统，返回相关Issue列表。 |
| | **SC3:** 需求澄清 → **AC3:** 3轮交互内完成项目确认和Issue关联。 |
| | **SC4:** 文档检索 → **AC4:** 需求确认后，系统从文档图谱中检索相关文档供Agent参考。 |
| | **SC5:** 闭环交付 → **AC5:** 代码合并后，Issue状态自动更新，变更关联可追溯。 |
| **待定决策** | **Q:** 项目注册表是否需要支持多租户？ → **决议：** Phase 0 单用户模式，Phase 1增加团队/组织维度。 |
| | **Q:** 文档同步频率？ → **决议：** 首次全量导入，增量每小时拉取，Webhook实时触发优先。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **技术栈版本** | FastAPI WebSocket (已有), SQLAlchemy 2.0 + pgvector 0.7, MCP Protocol (Step 5.2), 无新增第三方依赖 |
| **架构位置** | `/src/api/routes/chat.py`（WebSocket入口）、`/src/scheduler/context_resolver.py`（上下文解析）、`/src/integrations/issue_tracker_mcp.py`（Issue MCP适配）、`/src/infrastructure/models/project_registry.py`（项目注册表ORM）、`/src/infrastructure/models/doc_graph.py`（文档图谱ORM） |
| **实施细节** | **1. 用户交互流程（6步）：** 意图识别→项目上下文澄清→Issue关联→需求确认→进入开发流程→交付与同步。 |
| | **2. 上下文自动匹配策略（6级优先级）：** 会话历史(最高)→关键词匹配→Issue语义检索→文档语义检索→代码库检索→默认回退(最低)。 |
| | **3. Issue追踪MCP适配：** 统一接口 fetch_issue / search_issues / create_issue / update_issue_status，各系统(GitHub/Jira/Linear/TAPD)独立实现MCP Server。 |
| | **4. 文档图谱Schema：** doc_nodes(PostgreSQL+pgvector) + doc_edges(文档间引用) + Neo4j跨图谱引用(DocNode)-[:REFERENCES]->(CodeNode)。 |
| | **5. 项目注册表：** project_registry表 + user_project_preferences表(记录用户最近使用)。 |
| **风险与缓解** | 风险：上下文自动匹配准确率低导致多轮交互。缓解：渐进式匹配策略，会话历史优先（准确率高）；匹配失败时清晰展示候选项目。 |
| | 风险：Issue系统API限流。缓解：本地缓存Issue列表（Redis TTL=5min），减少实时查询。 |
| | 风险：多Issue系统集成复杂度。缓解：MCP协议统一抽象，新增系统只需实现4个标准方法。 |
| **需求错位** | 若未来需要支持直接在对话中操作Issue（如"关闭ISSUE-123"），需扩展Issue MCP工具集。当前仅支持查询和关联。 |
| **技术约束** | pgvector需PostgreSQL 12+；MCP Server需单独进程运行（与V14.1现有MCP架构一致）。 |
| **环境配置** | ISSUE_TRACKER_PROVIDERS（JSON格式，含各系统API token/URL）；DOC_SYNC_INTERVAL（默认3600s）。 |
| **依赖链** | PostgreSQL 12+（pgvector扩展）→ doc_nodes向量索引；MCP Protocol (Step 5.2) → Issue适配层；ContextResolver → Step 0.3 ClarityChecker（增强注入）；DocGraph → 元图谱（Step 8）的文档↔代码交叉引用。 |

---

## 与现有Step的映射

| Step | 原有内容 | 自然语言交互的补充 |
|------|---------|------------------|
| Step 0.1 项目章程 | 定义度量指标和范围 | 项目注册表中增加项目上下文维度 |
| Step 0.3 需求澄清 | 结构化追问澄清模糊需求 | 增加项目上下文澄清能力（项目选择、Issue关联、自动匹配） |
| Step 1.1 API契约 | RESTful API契约 | 支持自然语言交互入口（WebSocket文本输入+SSE流式输出） |
| Step 3.x 图谱系统 | 代码/数据库/配置/知识/推理链图谱 | 文档图谱（DocGraph）作为第七个知识源 |
| Step 5.1 调度器 | 状态机驱动Agent执行 | PLANNING阶段自动检索关联Issue和文档 |
| Step 6.1 驾驶舱 | 实时任务监控 | 展示项目上下文（当前Issue、关联文档、变更影响面） |
| 微信小程序接入 | Skill提交任务+状态监控 | 自然语言交互界面（项目选择卡片、Issue关联卡片） |

---

## ADR：Issue追踪集成策略

| 维度 | 决策 |
|------|------|
| **决策** | 通过MCP协议统一接入Issue追踪系统，每个系统实现一个MCP Server。统一接口：fetch_issue、search_issues、create_issue、update_issue_status。项目注册表中存储各系统的配置（API token、project_key等）。密钥通过SecretManager加密存储。 |
| **备选方案** | A. 直接集成（每个系统独立SDK调用） B. MCP协议统一抽象 ✅ |
| **理由** | ① MCP协议标准化，与V14.1现有架构无缝集成；② 新增Issue系统只需实现MCP Server，不影响核心代码；③ 密钥集中管理，保障安全性。 |
| **权衡** | MCP Server性能开销（额外进程）vs 代码解耦收益 → 收益大于成本。 |

---

## 支持的Issue系统

| 系统 | 集成方式 | 能力 |
|------|---------|------|
| GitHub Issues | REST API + GraphQL | 查询/创建/更新/关联Commits |
| GitLab Issues | REST API | 查询/创建/更新 |
| Jira | REST API | 查询/创建/更新/关联 |
| Linear | GraphQL API | 查询/创建/更新 |
| TAPD | REST API | 查询/创建/更新 |

---

## 上下文自动匹配策略

| 匹配策略 | 实现方式 | 优先级 |
|---------|---------|--------|
| 会话历史 | 查询当前会话/驾驶舱中最近操作的项目 | 最高（命中即用） |
| 关键词匹配 | 需求文本提取关键词 → 匹配项目名称/描述 | 高 |
| Issue语义检索 | 需求文本向量化 → Issue库语义检索 | 高 |
| 文档语义检索 | 需求文本向量化 → 文档图谱语义检索 | 中 |
| 代码库检索 | 需求文本向量化 → 代码图谱语义检索 | 中 |
| 默认回退 | 展示用户最近使用的项目列表 | 低（兜底） |

---

## 文档同步策略

| 来源 | 同步方式 | 频率 |
|------|---------|------|
| Git仓库文档 | Git Hook / 定时拉取 | Webhook触发 / 每小时 |
| Confluence/Notion | MCP协议拉取 | 按需 / 每小时 |
| Google Docs | Google API同步 | 按需 |

---

## 总结

- **用户交互：** 自然语言输入 → 自动项目识别 → Issue关联 → 需求澄清
- **项目注册表：** 管理项目元数据、Issue追踪配置、文档来源
- **文档图谱：** 第七个知识源，pgvector语义索引 + Neo4j跨图谱引用
- **Issue追踪集成：** MCP协议统一抽象，支持GitHub/Jira/Linear/TAPD
- **上下文自动匹配：** 会话历史→关键词→语义检索→用户选择的渐进式策略
- **Step 0.3增强：** 新增项目上下文澄清维度（项目选择、Issue关联）
- **交互界面：** 驾驶舱和微信小程序展示项目上下文卡片
- **总工作量：** 约5-7天，建议与Step 0.3需求澄清模块同步推进
