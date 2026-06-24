# 阶段1-PRD：需求澄清 Agent 接入（chat 端点 → ClarifierAgent → 开发 Agent）

> 基于现有代码契约编写，所有接口引用均来自真实代码，无猜测。
> 设计依据：`docs/PRD+ADR_自然语言交互与项目上下文.md`（6步交互流程）+ `docs/PRD+ADR_5阶段.md`（Agent角色）

---

## 核心架构约束（不可违反）

```
用户 ↔ chat端点 ↔ ClarifierAgent ↔ (LLMClient网关 ↔ litellm ↔ 真实LLM)
                                       ↑
                          Agent内部依赖注入，chat端点/前端不可见
```

| 规则 | 说明 |
|------|------|
| **chat 端点只认 Agent** | `api/routes/chat.py` 只 `await agent.execute()`，不直接 import/调用 `LLMClient` |
| **Agent 内部调网关** | `ClarifierAgent(llm=LLMClient实例)`，LLM 对 chat 端点和前端是黑盒 |
| **前端只连 Agent** | Orbit 前端只通过 `ws://host/api/v1/chat` 交互，感知不到 LLM 存在 |
| **Agent 无状态** | 遵循现有 `BaseAgent` 约束（`agents/base.py`），状态由外部管理（对话历史在 SessionRegistry） |

---

## 背景与现状（对齐基线）

### 当前实现的断点
1. **chat 端点**（`api/routes/chat.py`）：只做关键词匹配（`ContextMatcher`），返回项目候选。无 LLM、无多轮对话、无 Agent。
2. **LLM 网关**（`gateway/client.py`）：已实现，`LLMClient.generate(LLMRequest, task_id)` 可用，含熔断器+主备降级+成本追踪。**但无人调用它连进 chat 流程**。
3. **Agent 体系**（`agents/`）：5 个角色（architect/developer/reviewer/qa/config_manager）+ `AgentFactory`。**无 clarifier 角色**。`execute()` 是单次调用，无对话状态。
4. **前端**（`ChatPanel.vue` + `chat.ts` store）：WS 连接断了（`chatStore.setWs()` 从未被调用，且连到了错误的 `/ws/dashboard` 端点）。
5. **需求澄清引擎**（`scheduler/clarifier.py`）：是正则规则引擎（`ClarificationEngine`），扫 PRD 文本查矛盾/缺失字段，**不是对话式 Agent**。

### PRD 目标流程（`自然语言交互与项目上下文.md` 6步）
```
①意图识别/项目匹配 → ②需求澄清对话(多轮) → ③Issue关联 → ④需求确认 → ⑤进入开发 → ⑥交付同步
```
本次交付：**① + ② + ④ + ⑤的启动**。③Issue关联、⑥交付同步不在本次范围（PRD 标注 Phase 1+，依赖 MCP Server）。

---

## 用户故事

作为用户，我在对话框输入"支付超时了，修一下"，系统：
1. 自动匹配到项目（已有 `ContextMatcher`）
2. **ClarifierAgent 主动追问**："你说的'支付超时'是指超时阈值不够，还是回调失败导致状态卡住？涉及微信还是支付宝通道？有没有复现路径？"
3. 我逐轮回答，Agent 每轮基于上下文继续追问或收敛
4. 当信息充分，Agent 输出**结构化 PRD** + 询问"需求是否确认无误？"
5. 我确认后，系统**自动创建任务转给开发 Agent**（ArchitectAgent → DeveloperAgent）
6. 整个过程就像跟一位资深程序员对话，通过 Agent 消除需求歧义

---

## 需求描述

### ① ClarifierAgent 新角色（后端，新建 `agents/clarifier.py`）
- 继承 `BaseAgent`，`role = AgentRole.CLARIFIER`（新增枚举值）
- `execute(AgentInput) -> AgentOutput`：
  - 输入 `AgentInput.task` = 用户本轮消息；`AgentInput.context` = 对话历史 + 项目信息 + 澄清状态
  - 内部调用 `self.llm.generate(LLMRequest(...))`（即已实现的 `LLMClient`）
  - system_prompt 设计为"资深需求工程师"人设，强制结构化输出
  - 输出 `AgentOutput.result`：
    ```json
    {
      "reply": "Agent 的追问/回复文本",
      "clarification_status": "clarifying" | "ready",
      "structured_prd": null | { "goal": "", "scope": "", "acceptance_criteria": [], ... },
      "missing_fields": ["scope", "acceptance_criteria"]  // 当 status=clarifying
    }
    ```
- 在 `AgentFactory._registry` 注册

### ② 对话状态管理（后端，扩展 `chat.py`）
- 当前 chat 端点无状态（每条消息独立匹配）。需引入**会话级对话状态**：
  - 复用 `SessionRegistry`（已持久化 `chat_messages` 表），每轮把 Agent 回复以 `role="agent"` 存入
  - `ClarifierAgent.execute()` 的 `context` 从 `SessionRegistry.get_messages()` 构建（最近 N 轮历史）
- 项目匹配结果（`ContextMatcher`）作为首轮 context 注入 Agent

### ③ 修复 chat 端点 Agent 接入（后端，改造 `api/routes/chat.py`）
- 首轮：先跑 `ContextMatcher`（保留现有匹配）→ 注入 context → 调 `ClarifierAgent`
- 后续轮：直接调 `ClarifierAgent`（带历史 context）
- 澄清完成（`clarification_status == "ready"`）：返回结构化 PRD，等用户确认
- 用户确认（新消息类型 `type: "confirm"`）：**自动创建 Task 转开发流程**

### ④ 澄清→开发交接（后端，新增交接逻辑）
- 用户确认 PRD 后，chat 端点：
  1. 调 `POST /api/v1/tasks`（现有 `tasks.py`）创建任务，`prd` = Agent 生成的结构化 PRD 序列化文本
  2. 触发 `Scheduler.run_task()`（现有 `orchestrator.py`）→ 进入 IDLE→PARSING→PLANNING→CODING 状态机
  3. 返回 `task_id` 给前端，前端可跳转/订阅任务进度

### ⑤ 前端连接修复 + 对话渲染（前端，改造 3 文件）
- `chat.ts`：修复 WS 连接（连到 `/api/v1/chat` 而非 `/ws/dashboard`），新增 `confirm PRD` 动作
- `ChatPanel.vue`：渲染 Agent 的 `reply`（而非旧的"匹配到N个项目"），显示澄清状态/结构化PRD卡片
- `DashboardView.vue`：注入 chat WS，消息分发增加 `chat`/`clarify` 类型处理

---

## 范围 (Do/Don't)

**Do：**
- ClarifierAgent 新角色（system prompt + execute + 注册）
- chat 端点接入 ClarifierAgent（项目匹配 + 多轮澄清 + 确认转开发）
- 对话历史通过 SessionRegistry 持久化
- 澄清通过 → 自动创建 Task → 触发 Scheduler
- 前端连接修复 + Agent 回复渲染 + PRD 确认卡片
- ClarifierAgent 的 system prompt 精心设计（需求工程师人设、结构化输出约束）

**Don't：**
- 不做 Issue 关联（③，依赖 MCP Server，Phase 1+）
- 不做交付同步（⑥，依赖 Git 集成）
- 不做流式输出（SSE，V2）
- 不做语义检索/向量匹配（`ContextMatcher` 保持关键词匹配，语义检索 PRD 另列）
- 不改变现有 5 个 Agent 的代码（只新增 CLARIFIER）
- 不引入新第三方依赖（litellm/redis/httpx 已在 pyproject.toml）

---

## 数据契约

### WS 请求（C→S，`/api/v1/chat`）
```json
// 用户消息
{ "type": "chat", "text": "支付超时了修一下", "session_id": "abc123...", "project_name": "Code-Insight-Financial" }
// 用户确认 PRD（全盘确认）
{ "type": "confirm", "session_id": "abc123...", "project_name": "Code-Insight-Financial" }
// 用户确认 PRD（部分修改）
{ "type": "confirm", "session_id": "abc123...", "project_name": "Code-Insight-Financial",
  "modified_prd": { "goal": "...", "scope": "...", "acceptance_criteria": ["..."] } }
```

### WS 响应（S→C）— 统一 `{code, data, message}` 适配前端
```json
// 澄清中
{
  "code": 0,
  "data": {
    "type": "clarify",
    "reply": "你说的支付超时是指...",
    "clarification_status": "clarifying",
    "candidates": [...],       // 首轮带项目匹配结果
    "missing_fields": ["scope"]
  },
  "message": "ok"
}
// 澄清中——Agent 给验收候选（方案1）
{
  "code": 0,
  "data": {
    "type": "clarify",
    "reply": "目标已明确。验收标准我给了几个候选，你选一下（可多选，或点其它自己填）：",
    "clarification_status": "clarifying",
    "structured_prd": {
      "goal": "修复微信支付回调丢失导致订单状态卡住",
      "scope": "新增补偿任务，不改回调本身",
      "acceptance_criteria": [],
      "acceptance_options": ["5分钟未回调触发查单","查到已支付→更新状态","未支付→等30分钟关单"]
    },
    "missing_fields": ["acceptance_criteria"]
  },
  "message": "ok"
}

// 澄清完成，待确认
{
  "code": 0,
  "data": {
    "type": "clarify",
    "reply": "需求已明确，请确认：",
    "clarification_status": "ready",
    "structured_prd": {
      "goal": "修复微信支付回调丢失导致订单状态卡住",
      "scope": "新增补偿任务，不改回调本身",
      "acceptance_criteria": ["5分钟未回调触发查单","查到已支付→更新状态","未支付→等30分钟关单"]
    }
  },
  "message": "ok"
}
// 确认后转开发
{
  "code": 0,
  "data": {
    "type": "task_created",
    "task_id": "abc123...",
    "state": "IDLE",
    "message": "已创建任务，进入开发流程"
  },
  "message": "ok"
}
```

### ClarifierAgent System Prompt（核心设计）

#### 澄清维度（决定 Agent 问什么）

**🔴 必问维度（三项齐备才允许 ready，硬门槛）**

| 维度 | 代号 | 要确定到什么程度 | 依据 |
|------|------|------------------|------|
| 目标 | `goal` | 一句话说清"要解决什么问题" | `ClarificationEngine.COMPLETENESS_CHECKS`[0]、ArchitectAgent 输入要求 |
| 范围 | `scope` | 做哪些/不做哪些，改哪个模块 | `ClarificationEngine.COMPLETENESS_CHECKS`[1]、DeveloperAgent 需知道改哪里 |
| 验收标准 | `acceptance_criteria` | 可观测的完成判定条件 | `ClarificationEngine.COMPLETENESS_CHECKS`[2]、QA Agent 判定依据 |

**🟡 按需问维度（出现线索才追问，不作为 ready 门槛）**

| 维度 | 触发线索 |
|------|----------|
| 边界条件 `edge_cases` | 涉及数据/状态/并发（如空数据、重复请求） |
| 非功能约束 `constraints` | 用户提到性能/安全/兼容（如 QPS、旧版本） |
| 技术选型 `tech_preference` | 用户指定技术或项目已绑定栈 |
| 复现条件 `reproduce` | bug 修复类需求 |
| 影响面 `impact` | 改动可能波及现有功能 |

#### 验收标准澄清策略（方案1 + 原位输入）

当用户无法自述验收标准时，Agent **不追问"你的验收标准是什么"**，而是：
1. 基于已明确的 goal 主动生成 **2-3 个候选验收条件**
2. 前端在同一界面渲染为可点选项（多选）
3. **末尾固定一个"其它"选项**，点击后**原位变为输入框**（不弹窗、不跳转），用户直接在选项列表里自由输入自定义验收条件
4. 用户选中的候选 + 自定义输入，合并为最终 `acceptance_criteria` 列表

#### 完成判定（LLM 判断 + 6 层校验链双保险）

```
两阶段校验：

阶段一：每次 Agent 调 LLM 输出时
  V4 熵监控（现有 hallucination/l3_entropy.py）
    · LLMClient.generate() 加流式分支，传 stream=True + logprobs
    · token + logprobs 喂给 L3EntropyMonitor
    · 熵超阈值（DeepSeek 0.75 / Qwen 0.70，来自 core/config.py）→ HighEntropyError
    · ClarifierAgent 捕获 → 打回重问（不让高熵输出到达用户）
  V5 结构契约（Pydantic 模型校验，项目已有 Pydantic v2）
    · 定义 StructuredPRD Pydantic 模型
    · Agent 输出直接 StructuredPRD.model_validate_json()
    · 不符合 schema（字段缺失/类型错误）→ 拦截，打回 Agent 重新输出

阶段二：Agent 自评 clarification_status == "ready" 时
  V1 字段完整性（纯 Python，硬门槛）：
    · goal 非空、非占位词（"待定"/"TBD"/"..."等）、字符数 >= 8
    · scope 非空、非占位、字符数 >= 8，且含"做"或"不做"的边界描述
    · acceptance_criteria 是 list、len >= 1，每条非空且字符数 >= 5
  V2 一致性（纯 Python 规则）：
    · goal 核心名词在 scope 或 acceptance_criteria 至少出现一次（语义呼应）
    · 每条 acceptance_criteria 含可观测动词（返回/更新/触发/显示/拒绝/锁定等）
    · scope 内部"做X"与"不做Y"不构成字面矛盾
  V3 矛盾检测（纯 Python，借鉴 ClarificationEngine.CONTRADICTION_PAIRS 思路）：
    · goal ↔ acceptance_criteria 方向冲突（"降延迟" vs "全量扫描"）
    · scope ↔ constraints 冲突（"离线优先" vs "实时同步"）

阶段三：用户终审
  V6 用户终审（含部分修改）：
    · V1-V5 全过后展示 PRD 给用户
    · 用户可全盘确认 / 全盘拒绝 / 部分修改
    · 部分修改：每条 goal/scope/acceptance_criteria 可单独编辑（原位输入框）
    · 用户修改后发 type=confirm + 修改后的 structured_prd
    · 后端用用户版本覆盖，重过 V1-V3（V4/V5 不重过，非 LLM 新生成）
    · V1-V3 通过 → 真正建 Task

  全部通过 → 建任务转开发
  任一层失败 → 打回 Agent，context 注入 {校验失败的层 + 具体原因}
```

**校验函数位置**：
- V1-V3：`agents/clarifier.py` 内 `validate_prd()` 返回 `ValidationResult(passed, failed_layer, reasons)`
- V4：复用现有 `hallucination/l3_entropy.py` 的 `L3EntropyMonitor`
- V5：`agents/clarifier.py` 内 `StructuredPRD` Pydantic 模型
- V4 接入需改 `gateway/client.py` 加流式分支（stream=True + logprobs）

**不硬套 L6**：现有 `hallucination/l6_contract.py` 是 OpenAPI spec ↔ FastAPI 代码 AST 比对，校验对象是代码不是 JSON，不可复用于 structured_prd 校验。V5 用 Pydantic 模型校验替代。

#### System Prompt 全文

```
你是 Orbit 系统的需求澄清 Agent（ClarifierAgent），角色定位：资深需求工程师 + 技术架构师。

职责：通过多轮对话，把用户模糊的自然语言需求收敛为无歧义、可执行的结构化 PRD。

【澄清维度】
必问（三项齐备才能 ready）：
  1. goal — 要解决的核心问题，一句话
  2. scope — 做哪些/不做哪些，改哪里
  3. acceptance_criteria — 怎么验证做完了
按需（对话出现相关线索才追问）：
  · 数据/状态/并发 → 边界条件
  · 性能/安全/兼容 → 非功能约束
  · 指定技术 → 技术选型确认
  · bug类需求 → 复现条件
  · 涉及现有功能 → 影响面

【用户画像与领域适配（关键规则）】
你服务的用户可能不是程序员（如律师做法律软件、会计做财务软件）。必须：
1. 首轮从 project.tags / project.description 识别用户领域（法律/财务/医疗/...），
   判断用户是否为非技术背景。
2. 永远用用户能听懂的领域语言提问，不抛技术黑话：
   · 错误："用 Kafka 还是 RabbitMQ 做消息队列？"
   · 正确："法院传票和合同模板，两种文书系统都要能自动填充吗？"
3. 技术决策不甩给用户——Agent 基于项目栈自行推荐 2-3 个技术方案 + 利弊说明，
   让用户选"目标"而非选"技术"。纯技术细节（序列化协议/缓存策略）由 Agent 定，不问用户。
4. 领域术语桥接：用户说"留置权""坏账计提"等领域术语时，
   你负责翻译成软件需求描述（如"满足条件X时锁定资产记录"），并在 reply 中复述确认。
5. context 注入的 project 信息含 tags/description/doc_sources，据此判断领域。
【工作原则】
1. 每轮只问 1-2 个最关键的问题，避免轰炸用户
2. 按优先级推进：goal > scope > acceptance_criteria > 按需维度
3. 基于已确认信息推进，绝不重复已答过的问题
4. 当用户说不清 acceptance_criteria 时：基于 goal 主动生成 2-3 个候选验收条件让用户选，
   并提供"其它"选项允许用户自由输入，而非追问"你的验收标准是什么"
5. 当 goal + scope + acceptance_criteria 三者齐备 → 输出 structured_prd 并标记 ready

【输出格式】严格 JSON，不要输出 JSON 以外的内容：
{
  "reply": "你这一轮对用户说的话（追问/给候选/确认）",
  "clarification_status": "clarifying" | "ready",
  "structured_prd": {
    "goal": "已明确的目标，clarifying 时可填当前已知部分",
    "scope": "已明确的范围",
    "acceptance_criteria": ["条件1", "条件2"],
    "edge_cases": [],
    "constraints": [],
    "acceptance_options": ["候选验收条件1","候选验收条件2","候选验收条件3"]  // 仅当需要用户选验收标准时填，否则空数组
  },
  "missing_fields": ["goal","scope"]  // 当前还缺的必问维度
}

【上下文】本轮输入会带：
- project: 项目信息（首轮来自 ContextMatcher 匹配）
- history: 最近 10 轮对话（user/agent 交替）
- confirmed: 之前已确认的需求点
```

---

## 成功标准 → 验收

| SC | AC |
|----|-----|
| **SC1: Agent 接入** | AC1: chat 端点收到消息后，调用 `ClarifierAgent.execute()`，Agent 内部通过 `LLMClient.generate()` 调 LLM。代码中 chat.py 无 `LLMClient` 直接引用。 |
| **SC2: 多轮澄清** | AC2: 连续输入 3 轮，Agent 每轮基于历史 context 追问不同问题，不重复。对话历史持久化到 `chat_messages` 表。 |
| **SC3: 结构化收敛** | AC3: 信息充分后（模拟或真实），Agent 输出 `clarification_status=ready` + 非空 `structured_prd`（含 goal/scope/acceptance_criteria）。 |
| **SC4: 确认转开发** | AC4: 用户发 `type=confirm`，系统创建 Task（`/api/v1/tasks`），返回 task_id，Scheduler 进入 IDLE 状态。 |
| **SC5: 前端打通** | AC5: exe 中对话框发送消息有 Agent 回复（非空），澄清完成显示 PRD 卡片，确认后显示"任务已创建"。 |
| **SC6: LLM 隔离** | AC6: `rg "LLMClient" api/routes/chat.py` 无结果（chat 端点不直接引用网关）。 |

---

## 待定决策

| Q | 决议 |
|---|------|
| ClarifierAgent 调 LLM 失败（熔断/key未配）怎么办？ | **降级**：返回固定模板回复"暂时无法分析，请稍后重试"，不阻断对话。符合 `gateway/client.py` 现有降级机制。 |
| 澄清完成判定由谁做？ | **LLM判断 + 轻量校验双保险**：Agent 每轮输出 structured_prd 并自评 ready；ready 时用轻量校验函数检查 goal/scope/acceptance_criteria 三项非空且无明显矛盾，不通过则打回继续问。轻量校验不依赖现有 ClarificationEngine（那是扫原始文本的正则），而是针对 Agent 输出的结构化 JSON 做字段存在性+非空检查。 |
| 对话历史截断多少轮？ | **最近 10 轮**（20条消息）。防止 token 膨胀，`LLMRequest.max_tokens=2048`。 |
| 多项目候选时 Agent 怎么处理？ | 首轮 `ContextMatcher` 给候选，Agent 在首轮追问中顺带确认项目归属。 |
| 非技术用户（律师/财务等）怎么澄清？ | **领域适配**：Agent 从 `ProjectRegistry` 的 tags/description 识别用户领域，用领域语言提问，技术决策由 Agent 推荐方案+利弊让用户选目标而非选技术，领域术语由 Agent 翻译成软件需求并复述确认。 |
| 验收标准候选的"其它"怎么交互？ | **原位输入**：选项界面末尾固定"其它"项，点击后在原位变为输入框，不弹窗不跳转。 |
| 校验要多严格？ | **6 层校验链**：V4熵监控（复用l3_entropy）+ V5结构契约（Pydantic）+ V1字段完整性 + V2一致性 + V3矛盾检测 + V6用户终审。V4/V5 每次 LLM 输出触发，V1-V3 在 ready 时触发，V6 人类终审。任一失败打回。V4 需改 gateway/client.py 加流式分支。 |
| 用户终审能改 PRD 吗？ | **V6 支持部分修改**：每条 goal/scope/acceptance_criteria 可单独编辑（原位输入框），不全盘推翻。修改后重过 V1-V3（非 LLM 生成，不重过 V4/V5）。 |
| 验收标准用户提不出来怎么办？ | **方案1 + 其它选项**：Agent 主动生成 2-3 个候选验收条件（`acceptance_options`），前端渲染为可点选卡片，末尾固定一个"其它"选项，点击展开小窗口允许用户自由输入。可多选 + 自定义合并为最终 acceptance_criteria。 |
| 结构化 PRD 序列化成 task 的 prd 字段格式？ | JSON 序列化为可读文本（`json.dumps(ensure_ascii=False, indent=2)`），满足 `TaskCreateRequest.prd` 的 10-5000 字符约束。 |
| mock 模式（无 LLM）怎么测试？ | `ClarifierAgent(llm=None)` 时返回模板回复（参照现有 DeveloperAgent 的 mock 模式），保证 CI 可跑。 |

---

## 影响范围（文件清单）

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/orbit/agents/base.py` | 改 | `AgentRole` 加 `CLARIFIER` 枚举 |
| `src/orbit/agents/clarifier.py` | 新建 | ClarifierAgent 类 + system prompt |
| `src/orbit/agents/factory.py` | 改 | `_registry` 注册 ClarifierAgent |
| `src/orbit/api/routes/chat.py` | 改 | 接入 Agent，加 confirm 逻辑，转开发 |
| `src/orbit/gateway/client.py` | 改 | 加流式分支（stream=True + logprobs）供 V4 熵监控接入 |
| `frontend/src/stores/chat.ts` | 改 | 修复 WS 连接 + confirm 动作 |
| `frontend/src/components/chat/ChatPanel.vue` | 改 | 渲染 Agent 回复 + PRD 卡片 |
| `frontend/src/views/DashboardView.vue` | 改 | chat WS 注入 + 消息分发 |

**共 8 个文件（2 新建/6 改）。超过 3 文件，按 AGENTS.md 已先出 PRD 待确认。**

---

## 依赖链

```
ClarifierAgent → BaseAgent(llm注入) → LLMClient(gateway/) → litellm → 真实LLM
     ↓
chat.py 注入 ClarifierAgent + SessionRegistry(历史) + ContextMatcher(首轮匹配)
     ↓
确认后 → POST /tasks → Scheduler.run_task() → ArchitectAgent → DeveloperAgent
```

无新依赖。litellm>=1.84.0 / redis>=5.0.1 / httpx>=0.27.0 已在 `pyproject.toml`。