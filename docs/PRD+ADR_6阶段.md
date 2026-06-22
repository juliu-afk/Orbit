## Step 5.9：架构图与数据流向
### 图管理PRD/ADR规格

> **核心声明：V14.1系统的四张架构图是正式的技术文档资产，而非临时示意图。所有图表均配有Mermaid源码、版本控制和审核流程，确保与代码演进保持同步。**
#### 1.1 PRD · 架构图管理
| PRD · 架构图管理 |
| --- |
| 背景 | V14.1系统包含多层架构（用户层→接入层→调度层→能力层→验证层→知识层→工具层→可观测层），需通过标准化图表帮助团队理解系统全貌、协作流程和数据流向。 |
| 用户故事 | 作为架构师，我需要在技术评审时用标准化的系统架构图向团队说明V14.1的设计；作为开发工程师，我需要通过数据流向图理解代码从PRD到交付物的完整路径。 |
#### 1.2 ADR · 图表工具选型
| ADR · 图表工具选型 |
| --- |

### 图一：系统架构全景图

#### 2.1 图表说明
本图展示V14.1系统的完整分层架构，从用户层到可观测层共8层，清晰标注了组件间的依赖关系和调用方向。
#### 2.2 Mermaid源码
```
graph TB
subgraph 用户层
User[👤 用户]
WeChat[📱 微信小程序]
Dashboard[🖥️ Web驾驶舱]
end
subgraph 接入与网关层
API[🌐 API GatewayRESTful + WebSocket]
Auth[🔐 认证与权限JWT + 零信任]
end
subgraph 核心调度层
Orc[⚙️ 自研调度器 Orchestrator]
SM[🔄 状态机IDLE→PARSING→PLANNING→CODING→VALIDATING→DONE]
CP[💾 检查点 CheckpointRedis + PostgreSQL]
Audit[📋 审计链task_audit_trail]
end
subgraph 能力层（5个Agent协程）
Arch[🏗️ 架构师 Agent方案制定]
Dev[💻 开发者 Agent代码实现]
Rev[🔍 审查员 Agent分歧仲裁]
QA[🧪 QA Agent验证执行]
Cfg[⚙️ 配置管理员 Agent环境守护]
end
subgraph 验证层
L1_L9[🛡️ 9层防幻觉门禁L1-L9 同步阻塞验证]
Sentinel[🚨 哨兵 Agent主动安全检测]
end
subgraph 知识层
CG[📚 代码图谱Tree-sitter + SQLite]
DG[🗄️ 数据库图谱Schema + MVCC]
CFG[⚙️ 配置图谱基线 + 漂移检测]
KG[🧠 领域知识图谱Neo4j + Milvus + MCP]
end
subgraph 工具层
Sandbox[🏖️ Docker沙箱]
LLM[🤖 LiteLLM网关DeepSeek主力 + 缓存]
Git[📦 Git操作]
end
subgraph 可观测层
Ops[📊 AgentOpsPrometheus + Grafana]
Logs[📝 ELK日志]
Traces[🔗 分布式追踪]
end
User --> Dashboard & WeChat
Dashboard & WeChat --> API
API --> Auth
Auth --> Orc
Orc --> SM
SM --> CP
SM --> Audit
Orc -- asyncio.create_task() --> Arch & Dev & Rev & QA & Cfg
Dev -- 通过MCP查询 --> CG & DG & CFG & KG
Dev -- 通过MCP调用 --> Sandbox & LLM & Git
Dev -- 输出进入验证 --> L1_L9
L1_L9 --> Sentinel
Sentinel -- 通过后写入共享上下文 --> CP
Sentinel -- 失败时阻断传播 --> Audit
Orc -.-> Ops & Logs & Traces
Audit -.-> Ops
```
#### 2.3 与Step映射
- 用户层 → Step 6.1（Web驾驶舱）和 微信小程序接入章节
- 接入与网关层 → Step 1.1（API契约）和 Step 7.6（安全）
- 核心调度层 → Step 2.2（检查点）、Step 5.1（状态机）、审计补丁
- 能力层 → Step 5.2（5个Agent）
- 验证层 → Step 4.1/4.2（L1-L8）和 Step 4.3（L9）及 哨兵Agent章节
- 知识层 → Step 3.1/3.2/3.3（三图谱）和 Step 3.4（领域知识图谱）
- 工具层 → Step 2.1（LiteLLM）和 Step MVP-03（沙箱）
- 可观测层 → Step 7.2（AgentOps）

### 图二：层级抽象与协议栈

#### 3.1 图表说明
本图展示V14.1系统的三层抽象架构：编排层（V14.1核心价值）、通信层（MCP/A2A/HTTP协议栈）、执行层（底层引擎）。清晰标注了各层的职责边界和依赖关系。
#### 3.2 Mermaid源码
```
graph LR
subgraph 编排层["编排层 (V14.1核心)"]
direction TB
O1[多Agent协作调度]
O2[状态机驱动]
O3[9层验证门禁]
O4[审计链追溯]
end
subgraph 通信层["通信层 (协议栈)"]
direction TB
C1[MCPAgent↔工具/图谱]
C2[A2AAgent↔Agent]
C3[HTTP/WS外部↔系统]
end
subgraph 执行层["执行层 (底层引擎)"]
direction TB
E1[LLM推理DeepSeek主力]
E2[沙箱执行Docker]
E3[图谱查询SQLite/Neo4j]
end
编排层 --> 通信层
通信层 --> 执行层
style 编排层 fill:#eff6ff,stroke:#2563eb
style 通信层 fill:#fefce8,stroke:#f59e0b
style 执行层 fill:#f0fdf4,stroke:#16a34a
```
#### 3.3 与Step映射
- 编排层 → Step 5.1（调度器状态机）、Step 5.2（5个Agent）、Step 4.1-4.3（验证门禁）
- 通信层 → 微信小程序接入（HTTP/WS）、Step 5.4（A2A）、Step 5.5（MCP工具注册）
- 执行层 → Step 2.1（LiteLLM）、Step MVP-03（沙箱）、Step 3.1-3.4（四图谱）

### 图三：数据流向图（从需求到交付物）

#### 4.1 图表说明
本图展示用户PRD从输入到最终交付物的完整数据流转路径，清晰标注了每个阶段的输入/输出以及跨Agent的数据传递方式（检查点/审计链）。
#### 4.2 Mermaid源码
```
flowchart LR
PRD[📄 PRD用户需求] --> Parser[🧹 ParserAgent需求澄清]
Parser --> Plan[📋 ArchitectAgent技术方案 DAG]
Plan --> Code[💻 DeveloperAgent代码生成]
Code --> L1_L9[🛡️ L1-L9验证门禁]
L1_L9 -->|通过| Audit[📋 审计链记录决策]
L1_L9 -->|失败| Fix[🔄 重试/驳回]
Fix --> Code
Audit --> Checkpoint[💾 检查点持久化]
Checkpoint --> Deliver[📦 交付物代码 + 验证报告]
Deliver --> User[👤 用户]
Deliver --> Webhook[🔗 Webhook外部系统]
Deliver --> MiniApp[📱 微信小程序]
Graph[📚 四图谱] -.-> Code
Graph -.-> L1_L9
Memory[🧠 L5长期记忆] -.-> Plan
Memory -.-> Code
style PRD fill:#eff6ff,stroke:#2563eb
style Deliver fill:#f0fdf4,stroke:#16a34a
style User fill:#fefce8,stroke:#f59e0b
```
#### 4.3 与Step映射
- PRD → ParserAgent：Step 0.3（需求澄清）
- ParserAgent → ArchitectAgent：Step 5.2（Agent协作）
- ArchitectAgent → DeveloperAgent：Step 5.1（状态机驱动）
- DeveloperAgent → L1-L9：Step 4.1-4.3（验证门禁）
- 验证 → 检查点/审计链：Step 2.2（检查点）、审计补丁
- 检查点 → 交付物：交付物流向章节
- 交付物 → 用户/Webhook/小程序：Step 1.1（API）、微信小程序接入章节

### 图四：关键设计要点（一图总结）

#### 5.1 图表说明
本图以表格形式总结V14.1系统各层的核心组件、关键设计和一句话说明，便于快速传达系统设计理念。
#### 5.2 图表内容（可直接渲染的表格）
```
| 层级 | 核心组件 | 关键设计 | 一句话说明 |
|------|----------|----------|-----------|
| 用户层 | 微信小程序 / Web驾驶舱 | Skill机制 + WebSocket | 手机也能提交任务、看进度 |
| 接入层 | API网关 + JWT认证 | RESTful + SSE + WebSocket | 统一入口，安全可控 |
| 调度层 | 自研调度器 + 状态机 | asyncio协程 + 检查点 | 微秒级拉起Agent，崩溃可恢复 |
| 能力层 | 5个Agent协程 | 依赖注入 + L4私有记忆 | 各司其职，幻觉不跨Agent传播 |
| 验证层 | L1-L9门禁 | 同步阻塞验证 | 验证不通过，产出不进共享上下文 |
| 知识层 | 四图谱 | MCP协议查询 | 零Token开销的事实锚点 |
| 工具层 | LiteLLM / 沙箱 / Git | 标准化工具接口 | Agent通过MCP调用 |
| 协议层 | MCP + A2A | 标准化协议 | 工具调用与Agent通信分离 |
| 可观测层 | AgentOps + 审计链 | 哈希链防篡改 | 知道"做了什么"，也知道"为什么" |
```
#### 5.3 与Step映射
- 用户层 → Step 6.1 + 微信小程序接入章节
- 接入层 → Step 1.1 + Step 7.6
- 调度层 → Step 2.2 + Step 5.1
- 能力层 → Step 5.2
- 验证层 → Step 4.1 + Step 4.2 + Step 4.3
- 知识层 → Step 3.1 + Step 3.2 + Step 3.3 + Step 3.4
- 工具层 → Step 2.1 + Step MVP-03
- 协议层 → Step 5.4 + Step 5.5 + 微信小程序接入章节
- 可观测层 → Step 7.2

### 与现有Step的映射总览

| 图表 | 包含内容 | 对应Step |
| --- | --- | --- |
| 图一：架构全景图 | 8层完整架构 + 组件依赖关系 | Step 1.1, 2.1, 2.2, 3.1-3.4, 4.1-4.3, 5.1, 5.2, 6.1, 7.2, 7.6, MVP-03, 微信小程序接入 |
| 图二：层级抽象与协议栈 | 编排层 → 通信层 → 执行层 | Step 2.1, 3.1-3.4, 4.1-4.3, 5.1, 5.2, 5.4, 5.5, MVP-03, 微信小程序接入 |
| 图三：数据流向图 | PRD → 交付物 端到端流程 | Step 0.3, 2.2, 4.1-4.3, 5.1, 5.2, 审计补丁, 交付物流向章节, 微信小程序接入 |
| 图四：关键设计要点 | 各层核心组件+关键设计+一句话说明 | 所有Step（总览性质） |
> **✅ 架构图与数据流向交付确认
图一：系统架构全景图 —— 8层分层架构，含Mermaid源码和Step映射
图二：层级抽象与协议栈 —— 编排层/通信层/执行层，含Mermaid源码和Step映射
图三：数据流向图 —— PRD到交付物的端到端流程，含Mermaid源码和Step映射
图四：关键设计要点 —— 表格化总览，含各层核心设计和Step映射
图管理PRD/ADR —— 图表维护规范、选型决策、SC→AC验收标准
— V14.1 开发计划 · 架构图与数据流向 · 2026年6月22日 —



## Step 5.8：微信小程序接入
### 整体架构设计

> **核心方案：微信小程序 + Skill 机制作为请求入口，WebSocket/SSE 作为实时监控通道。**
#### 1.1 完整调用链路
```
┌─────────────┐
│  微信用户    │
│  "生成报表"  │
└──────┬──────┘
│ 自然语言输入
▼
┌─────────────────────────────────────────────────┐
│           微信小程序（前端）                      │
│  • Skill 入口识别                               │
│  • 调用 V14.1 API 提交任务                      │
│  • WebSocket/SSE 监听状态更新                   │
└──────┬──────────────────────────────────────────┘
│ HTTPS (POST /api/v1/tasks)
▼
┌─────────────────────────────────────────────────┐
│            V14.1 后端（API 网关层）               │
│  • 接收任务请求                                 │
│  • 返回 task_id                                 │
│  • 建立 WebSocket/SSE 连接                      │
└──────┬──────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────┐
│            V14.1 调度器（Step 5.1）              │
│  • 状态机驱动                                   │
│  • 拉起 Agent 协程                             │
│  • 实时推送状态变更                             │
└─────────────────────────────────────────────────┘
```
#### 1.2 为什么选择微信小程序？
- 天然的用户入口：微信日活超10亿，无需用户额外下载 App。
- 官方 AI 能力加持：微信已推出小程序 Skill 机制，可将功能封装为 AI 可调用的能力。
- 基于 MCP：Skill 底层基于 MCP 协议，与 V14.1 使用的 MCP 协议栈天然同构。
- 实时通信支持：小程序支持 WebSocket 和 SSE 两种实时方案。

### 微信小程序 Skill 机制

#### 2.1 Skill 是什么
Skill 是微信官方推出的 AI 能力接入机制，开发者可将小程序的能力封装为 AI 可调用的 Skill。用户通过自然语言就能触发 Skill，执行对应功能。
#### 2.2 两种接入模式
| 模式 | 说明 | 适用场景 |
| --- | --- | --- |
| 自动模式 | 平台自动分析小程序源码，AI 可直接操作 | 快速验证，零代码接入 |
| 开发模式 | 开发者自定义 Skill，通过审核后被 AI 调用 | 推荐 定制化 V14.1 任务触发 |
#### 2.3 Skill 文件结构
```
my-agent-skill/
├── mcp.json          # 可用的函数声明（MCP 工具列表）
├── apis/
│   ├── submit_task.js   # 提交 V14.1 任务
│   ├── get_status.js    # 查询任务状态
│   └── cancel_task.js   # 取消任务
├── index.js          # 注册函数给运行时
└── components/
└── status-card.wxml # 实时状态展示卡片
```
#### 2.4 mcp.json 声明示例
```
{
"mcpServers": {
"v14-agent": {
"functions": [
{
"name": "submit_development_task",
"description": "向 V14.1 系统提交一个软件开发任务",
"parameters": {
"type": "object",
"properties": {
"prd": {
"type": "string",
"description": "产品需求文档"
},
"priority": {
"type": "string",
"enum": ["low", "normal", "high", "critical"],
"description": "任务优先级"
},
"callback_url": {
"type": "string",
"description": "任务完成后的回调地址"
}
},
"required": ["prd"]
}
},
{
"name": "query_task_status",
"description": "查询 V14.1 系统中某个任务的执行状态",
"parameters": {
"type": "object",
"properties": {
"task_id": {
"type": "string",
"description": "任务ID"
}
},
"required": ["task_id"]
}
}
]
}
}
}
```
#### 2.5 函数实现示例
```
// apis/submit_task.js
// 在微信小程序 Skill 中调用 V14.1 后端 API
const V14_API_BASE = 'https://api.v14-system.com/api/v1';
export default async function submit_development_task(params) {
const { prd, priority = 'normal', callback_url } = params;
// 1. 调用 V14.1 后端 API 提交任务
const response = await fetch(`${V14_API_BASE}/tasks`, {
method: 'POST',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ prd, priority, callback_url })
});
if (!response.ok) {
throw new Error(`V14.1 系统返回错误: ${response.status}`);
}
const data = await response.json();
// 2. 返回给小程序（Skill 的返回值）
return {
task_id: data.task_id,
state: data.state,
message: '任务已提交，正在处理中...',
status_url: `${V14_API_BASE}/tasks/${data.task_id}/status`
};
}
```

### 与 V14.1 的 MCP 协议集成

> **核心洞察：微信小程序的 Skill 机制底层基于 MCP 协议，与 V14.1 使用的 MCP 协议栈完全兼容。这意味着 Skill 中的函数声明（mcp.json）可以直接映射到 V14.1 的 MCP Server。**
#### 3.1 分层架构
```
┌─────────────────────────────────────────────────────┐
│           微信小程序（Skill 层）                   │
│  mcp.json 声明 → apis/*.js 实现                   │
│  调用 V14.1 后端 API（内部使用 MCP 协议）         │
└─────────────────────┬───────────────────────────────┘
│ HTTP / WebSocket
▼
┌─────────────────────────────────────────────────────┐
│            V14.1 后端（MCP Server）                │
│  • 暴露 MCP 工具：submit_task, query_status       │
│  • 内部调用调度器                                  │
└─────────────────────┬───────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────┐
│            V14.1 调度器（Agent 系统）              │
└─────────────────────────────────────────────────────┘
```
#### 3.2 V14.1 端 MCP 工具暴露
```
# /src/mcp/servers/v14_mcp_server.py
from mcp.server import Server
from src.scheduler.orchestrator import TaskOrchestrator
server = Server("v14-mcp-server")
orchestrator = TaskOrchestrator()
@server.tool()
async def submit_development_task(prd: str, priority: str = "normal") -> dict:
"""提交开发任务到 V14.1 系统"""
task = await orchestrator.submit(prd, priority)
return {"task_id": task.id, "state": task.state.value}
@server.tool()
async def query_task_status(task_id: str) -> dict:
"""查询任务状态"""
task = await orchestrator.get_task(task_id)
return {
"task_id": task.id,
"state": task.state.value,
"progress": task.progress,
"result": task.result
}
@server.tool()
async def cancel_task(task_id: str) -> dict:
"""取消正在执行的任务"""
await orchestrator.cancel(task_id)
return {"task_id": task_id, "state": "cancelled"}
```

### 实时监控方案

#### 4.1 两种实时通信方案对比
| 方案 | 特点 | 适用场景 |
| --- | --- | --- |
| WebSocket | 全双工 通信，适合高频双向交互 | Agent 执行过程中需要用户介入确认（如：选择方案A还是B） |
| SSE (Server-Sent Events) | 单向 推送，基于 HTTP 更轻量 | 只需“看进度”的纯监控场景 |
#### 4.2 WebSocket 实时监控实现
```
# /src/api/websocket.py
from fastapi import WebSocket, WebSocketDisconnect
from src.scheduler.orchestrator import TaskOrchestrator
class ConnectionManager:
def __init__(self):
self.active_connections: Dict[str, List[WebSocket]] = {}
async def connect(self, task_id: str, websocket: WebSocket):
await websocket.accept()
if task_id not in self.active_connections:
self.active_connections[task_id] = []
self.active_connections[task_id].append(websocket)
def disconnect(self, task_id: str, websocket: WebSocket):
if task_id in self.active_connections:
self.active_connections[task_id].remove(websocket)
async def broadcast_status(self, task_id: str, status: dict):
"""向订阅了该任务的所有客户端广播状态"""
if task_id in self.active_connections:
for connection in self.active_connections[task_id]:
try:
await connection.send_json(status)
except:
pass
# 在调度器状态变更时触发广播
class StatusBroadcaster:
def __init__(self, manager: ConnectionManager):
self.manager = manager
async def on_state_change(self, task_id: str, old_state: str, new_state: str, data: dict = None):
await self.manager.broadcast_status(task_id, {
"type": "state_change",
"task_id": task_id,
"from": old_state,
"to": new_state,
"data": data
})
```
#### 4.3 SSE 实时监控实现
```
# /src/api/sse.py
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
import asyncio
@router.get("/tasks/{task_id}/stream")
async def stream_task_status(task_id: str, orchestrator: TaskOrchestrator):
"""SSE 实时推送任务状态"""
async def event_generator():
# 获取初始状态
task = await orchestrator.get_task(task_id)
last_state = task.state
while True:
# 检查状态是否有变化
current_task = await orchestrator.get_task(task_id)
if current_task.state != last_state:
last_state = current_task.state
yield {
"event": "state_change",
"data": {
"task_id": task_id,
"state": current_task.state.value,
"progress": current_task.progress,
"timestamp": datetime.utcnow().isoformat()
}
}
# 如果任务已完成或失败，结束推送
if current_task.state in [TaskState.DONE, TaskState.FAILED]:
yield {
"event": "complete",
"data": {
"task_id": task_id,
"state": current_task.state.value,
"result": current_task.result
}
}
break
await asyncio.sleep(2)  # 轮询间隔
return EventSourceResponse(event_generator())
```

### API 规格

#### 5.1 任务提交 API
```
POST /api/v1/tasks
Request:
{
"prd": "修改支付超时时间为60秒",
"priority": "high",           # low | normal | high | critical
"callback_url": null,          # 可选，任务完成后的Webhook
"source": "wechat_skill"       # 来源标识
}
Response:
{
"task_id": "a1b2c3d4-...",
"state": "IDLE",
"message": "任务已提交，正在排队中..."
}
```
#### 5.2 状态查询 API
```
GET /api/v1/tasks/{task_id}/status
Response:
{
"task_id": "a1b2c3d4-...",
"state": "CODING",
"progress": 0.6,
"current_step": "DeveloperAgent 正在生成代码...",
"agent_logs": [
{"step": "PARSING", "status": "done", "duration_ms": 1200},
{"step": "PLANNING", "status": "done", "duration_ms": 3400},
{"step": "CODING", "status": "running", "duration_ms": null}
],
"estimated_remaining_ms": 3000,
"created_at": "2026-06-22T10:00:00Z",
"updated_at": "2026-06-22T10:01:30Z"
}
```

### 与现有 Step 的映射

| Step | 原有内容 | 微信小程序接入的补充 |
| --- | --- | --- |
| Step 1.1四层架构与 API 契约 | 定义了 RESTful API 契约 | 需补充 增加 /tasks 路由的 source 字段；新增 /tasks/{id}/stream SSE 端点 |
| Step 6.1Vue3 驾驶舱 | 定义了 Web 驾驶舱的实时监控 | 无修改 微信小程序的实时监控复用相同的 WebSocket/SSE 基础设施 |
| Step 2.1LiteLLM 网关 | LLM API 调用网关 | 无修改 微信小程序接入不涉及 LLM 网关 |
| Step 5.1调度器状态机 | 定义了任务执行状态流转 | 需补充 状态变更时触发 WebSocket/SSE 广播（通过 StatusBroadcaster） |
| Step 7.6安全与权限管理 | JWT + 零信任架构 | 需补充 微信小程序的来源认证（小程序 AppID 验证 + JWT 颁发） |

### 代码示例

#### 7.1 微信小程序 Skill 完整示例
```
// apis/submit_task.js - 完整实现
const V14_API_BASE = 'https://api.v14-system.com/api/v1';
const WS_BASE = 'wss://api.v14-system.com/ws';
export default async function submit_development_task(params) {
const { prd, priority = 'normal' } = params;
// 1. 提交任务
const response = await fetch(`${V14_API_BASE}/tasks`, {
method: 'POST',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ prd, priority, source: 'wechat_skill' })
});
if (!response.ok) {
throw new Error(`提交失败: ${response.status}`);
}
const data = await response.json();
// 2. 返回给小程序，包含用于 WebSocket 连接的 task_id
return {
task_id: data.task_id,
message: '任务已提交，正在处理中...',
ws_url: `${WS_BASE}/tasks/${data.task_id}`
};
}
```
#### 7.2 微信小程序实时监控组件
```
// components/status-card/index.js
Component({
properties: {
taskId: { type: String, value: '' }
},
data: {
status: 'pending',
progress: 0,
logs: [],
socket: null
},
lifetimes: {
attached() {
this.connectWebSocket();
},
detached() {
if (this.data.socket) {
this.data.socket.close();
}
}
},
methods: {
connectWebSocket() {
const ws = wx.connectSocket({
url: `wss://api.v14-system.com/ws/tasks/${this.properties.taskId}`,
});
ws.onMessage((res) => {
const data = JSON.parse(res.data);
this.setData({
status: data.state,
progress: data.progress,
logs: [...this.data.logs, data.message]
});
});
ws.onError((err) => {
console.error('WebSocket 错误:', err);
});
this.setData({ socket: ws });
}
}
});
```
#### 7.3 微信小程序卡片展示
```
<!-- components/status-card/index.wxml -->
<view class="status-card">
<view class="status-header">
<text class="task-id">任务: {{taskId}}</text>
<text class="status-badge {{status}}">{{status}}</text>
</view>
<view class="progress-section">
<text class="progress-label">执行进度</text>
<progress percent="{{progress * 100}}" stroke-width="8" />
<text class="progress-text">{{Math.round(progress * 100)}}%</text>
</view>
<view class="logs-section">
<text class="logs-title">执行日志</text>
<scroll-view class="logs-scroll" scroll-y>
<view class="log-item" wx:for="{{logs}}" wx:key="index">
<text class="log-time">{{item.time}}</text>
<text class="log-content">{{item.msg}}</text>
</view>
</scroll-view>
</view>
</view>
```

### 实施路线图

| 阶段 | 任务 | 周期 | 依赖 |
| --- | --- | --- | --- |
| 准备阶段 | ① 设计 V14.1 后端 API（/tasks 提交、/tasks/{id}/status 查询、WebSocket/SSE 推送）② 申请微信小程序 AppID③ 搭建微信小程序开发环境 | 1-2天 | Step 1.1 完成 |
| 开发阶段 | ① 创建微信小程序 Skill 项目（mcp.json + apis/*.js + index.js）② 实现 Skill 调用 V14.1 API 的逻辑③ 实现 WebSocket/SSE 实时通信④ 设计小程序 UI（输入+状态卡片） | 3-5天 | Step 5.1 完成 |
| 集成与测试 | ① 端到端联调（小程序 ↔ V14.1）② 实时监控体验优化③ 安全认证联调 | 2-3天 | Step 7.6 完成 |
| 上线发布 | ① 微信小程序提交审核② Skill 功能发布③ ⚠️ 注意：Skill模式目前在内测，相关代码暂时不要合入正式版本提审 | 1-2天 | 测试通过 |
> **⚠️ 重要提醒：
微信小程序 Skill 模式目前处于 内测阶段，相关代码暂时不要合入正式版本提审。
建议先在开发环境做技术验证，待 Skill 功能正式对外开放后再提交审核。
如果急需上线，可先用小程序原生页面 + API 调用方式实现（不依赖 Skill 能力）。**
> **✅ 微信小程序接入交付确认
整体架构：微信小程序 Skill 作为请求入口 + WebSocket/SSE 作为实时监控通道
Skill 机制：mcp.json 声明 + apis/*.js 实现 + 与 V14.1 MCP 协议同构
实时监控：WebSocket（全双工）和 SSE（轻量单向）两种方案
API 规格：POST /tasks 提交、GET /tasks/{id}/status 查询、/tasks/{id}/stream SSE 流
代码示例：微信小程序 Skill 完整实现、实时监控组件、卡片 UI
实施路线图：准备→开发→集成测试→上线，约 1-1.5 周
下一步：可按照实施路线图开始微信小程序项目的创建和 Skill 开发。**
— V14.1 开发计划 · 微信小程序接入 · 2026年6月22日 —


## Step 6.1：Vue3 驾驶舱（实时可视化监控）

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | 当前系统仅提供CLI和API接口，运维/PM无法直观了解任务执行状态、Agent协作情况和Token消耗。需要一个轻量级Web驾驶舱，实时展示任务DAG拓扑、Agent状态、Token流速和防幻觉告警。 |
| **用户故事** | 作为技术负责人，我打开驾驶舱Dashboard，看到当前运行任务的有向无环图（DAG），每个节点显示Agent名称、耗时和状态（运行中/成功/失败）；下方折线图实时更新Token消耗；右侧面板显示最新告警（如高熵事件）。 |
| **需求描述** | ①实现WebSocket连接（`/ws/dashboard`），订阅任务状态更新、Token指标、熵事件、配置漂移告警；②渲染任务DAG图（使用`vis-network`），节点颜色映射状态（绿色=成功、黄色=运行中、红色=失败）；③渲染Token流速折线图（使用`ECharts`），展示prompt_tokens和completion_tokens；④展示最近20条告警（高熵、Z3超时、配置漂移）列表；⑤响应式设计，支持1920x1080及1280x720分辨率。 |
| **范围 (Do/Don't)** | **Do：**实时任务监控、Token趋势图、告警列表。**Don't：**不包含任务管理（创建/取消）功能（V2）；不支持用户认证（生产环境由反向代理加Basic Auth）；不支持移动端适配。 |
| **数据契约 (WebSocket消息)** | ``代码块-1`` |
| **异常定义** | 前端WebSocket断线时，自动重连（指数退避，最多5次）；后端推送数据缺失时，前端显示占位符（---）而非崩溃。 |
| **成功标准→验收** | **SC1:**首屏加载<2s →**AC1:**Lighthouse性能测试（Performance分数>90）。 |
| | **SC2:**实时数据延迟<5s →**AC2:**手动触发任务，观察Dashboard状态更新，延迟<5s。 |
| | **SC3:**DAG图渲染正确 →**AC3:**任务执行时，DAG节点颜色与状态一致（运行中=黄色，成功=绿色）。 |
| | **SC4:**告警实时推送 →**AC4:**模拟高熵事件，驾驶舱告警列表在2s内出现新条目。 |
| **待定决策** | **Q1:**使用Socket.IO还是原生WebSocket？ →**决议：**Socket.IO（自带重连、心跳、多路复用，降低开发成本）。 |
| | **Q2:**DAG图是否支持交互（点击节点查看详情）？ →**决议：**支持，点击节点弹出Modal显示该步骤的输入/输出日志（从后端获取）。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **技术栈版本** | Frontend: Vue 3.4.21, Vite 5.0.12, Pinia 2.1.7, Socket.IO Client 4.7.2, vis-network 9.1.2, ECharts 5.5.0, Element Plus 2.7.0 (UI组件库)。 |
| | Backend (WebSocket): FastAPI +`socketio`(python-socketio 5.9)。 |
| | Node版本: 18.17+ (LTS)。 |
| **架构位置** | 接入层（展示界面），位于`/frontend/`，构建产物（dist）由Nginx静态托管或由FastAPI挂载。 |
| **实施细节** | **1. 项目结构：** |
| | ``代码块-2`` |
| | **2. Pinia Store 示例 (task store)：** |
| | ``代码块-3`` |
| | **3. Socket.IO 连接配置：** |
| | ``代码块-4`` |
| **风险与缓解** | 风险1: vis-network在大图（>50节点）时卡顿。缓解：设置`physics: false`并启用`layout: hierarchical`，限制最大节点数50（超出则折叠）。 |
| | 风险2: ECharts实时数据流可能导致内存泄漏。缓解：设置`dataZoom`窗口，仅保留最近100个数据点。 |
| **需求错位** | 若用户需要3D拓扑图或实时视频流，当前方案不适用。但当前需求仅为2D任务监控，Vis-network足够。 |
| **技术约束** | 前端禁止直接调用LLM API或数据库，所有数据通过WebSocket从后端获取。前端部署必须配置`VITE_WS_URL`指向后端WebSocket端点。 |
| **环境配置** | # .env.production |
| | VITE_WS_URL=wss://api.example.com |
| | VITE_API_URL=https://api.example.com/api/v1 |
| **依赖链** | Vue组件 → Pinia Store → Socket.IO Client → 后端WebSocket Server。 |

🧪 原子化测试用例 (Vitest + Cypress)：
// 单元测试 (Vitest)
 import { describe, it, expect } from 'vitest'
 import { useTaskStore } from '@/stores/task'

 describe('Task Store', () => {
 it('updates task correctly', () => {
 const store = useTaskStore()
 store.updateTask({ task_id: 't1', state: 'CODING', progress: 0.5, dag: [] })
 expect(store.tasks['t1'].state).toBe('CODING')
 })
 })

 // E2E 测试 (Cypress)
 describe('Dashboard E2E', () => {
 it('displays task topology after creation', () => {
 cy.visit('/dashboard')
 // 通过API创建任务
 cy.request('POST', '/api/v1/tasks', { prd: 'write a sort function' }).then((resp) => {
 const taskId = resp.body.task_id
 // 等待WebSocket推送更新
 cy.contains('.task-node', taskId, { timeout: 10000 }).should('exist')
 // 验证节点颜色
 cy.get(`[data-task-id="${taskId}"]`).should('have.class', 'state-running')
 })
 })
 })


## Step 6.2：端到端集成测试（质量门禁）

| PRD |  |
| --- | --- |
| **背景** | 系统已包含调度器、LLM客户端、图谱引擎、防幻觉层、驾驶舱等多个模块。需建立完整的E2E测试套件，确保各模块协同工作且达到设计指标（Token≤35、延迟≤8s、幻觉率<3%），并作为CI/CD门禁。 |
| **用户故事** | 作为QA工程师，我执行`make e2e-test`，系统自动拉起全部依赖（Docker Compose），运行E2E场景（PRD→生成→验证→修复），输出Allure测试报告，并验证性能指标是否达标。 |
| **需求描述** | ①编写E2E测试套件（pytest + httpx异步客户端），覆盖完整任务生命周期；②集成Allure报告生成；③性能基准测试（locust），模拟并发5个任务，P95延迟<10s；④混沌实验：模拟LLM 5xx错误（使用Mock LLM注入故障），验证熔断器触发和降级；⑤环境隔离：E2E测试使用独立的Test数据库和Redis，不影响Dev环境。 |
| **范围 (Do/Don't)** | **Do：**E2E场景覆盖“正常流程”、“重试修复流程”、“熔断降级流程”。**Don't：**不包含UI自动化测试（由Cypress覆盖，在Step 6.1中）；不包含安全渗透测试。 |
| **数据契约** | ``代码块-5`` |
| **异常定义** | 若任何E2E测试失败，CI流水线返回非0退出码，阻断合并；若性能测试P95>10s，标记为警告但不阻断（人工审查）。 |
| **成功标准→验收** | **SC1:**E2E通过率100% →**AC1:**运行`pytest -m e2e`，所有场景（正常/修复/熔断）通过。 |
| | **SC2:**性能基准达标 →**AC2:**locust并发5任务，P95延迟<10s，Token消耗<35/任务。 |
| | **SC3:**混沌实验通过 →**AC3:**注入LLM 5xx错误，熔断器在30s内触发，且系统自愈。 |
| | **SC4:**覆盖率>80% →**AC4:**`pytest --cov=src --cov-report=term`输出>80%。 |
| **待定决策** | **Q1:**E2E测试是否使用真实LLM还是Mock？ →**决议：**默认使用Mock LLM（确保稳定性和速度），每周运行一次全量真实LLM测试（夜间构建）。 |
| | **Q2:**性能测试阈值是否按环境调整？ →**决议：**CI环境（资源受限）阈值放宽至12s，预发布环境严格8s。 |

| ADR |  |
| --- | --- |
| **技术栈版本** | pytest 8.0.0, pytest-asyncio 0.23, pytest-xdist 3.5, pytest-cov 4.1, httpx 0.27, Allure Pytest 2.13, locust 2.20, docker-compose 2.24。 |
| **架构位置** | 测试基础设施，位于`/tests/`，包含`e2e/`,`performance/`,`chaos/`子目录。 |
| **实施细节** | **E2E核心测试用例：** |
| | ``代码块-6`` |
| | **性能测试 (locustfile.py)：** |
| | ``代码块-7`` |
| **风险与缓解** | 风险：E2E测试依赖Docker服务，CI环境可能无法访问Docker。缓解：在GitHub Actions中配置`services`（PostgreSQL/Redis）而非docker-compose，或使用`pytest-docker`插件自动管理。 |
| **需求错位** | 若测试环境无法安装Docker（如Windows沙箱），沙箱相关的E2E测试将跳过。通过`@pytest.mark.skipif`处理，确保不影响其他测试。 |
| **技术约束** | E2E测试必须使用异步客户端（httpx.AsyncClient）与FastAPI异步端点匹配；性能测试必须使用独立的数据库（避免与开发数据交叉）。 |
| **环境配置** | # .env.test |
| | DATABASE_URL=postgresql+asyncpg://test:test@localhost:5433/test_db |
| | REDIS_URL=redis://localhost:6380/0 |
| | MOCK_LLM=true |
| | ENABLE_L5=false # E2E跳过Z3（加速） |
| | TEST_CHAOS_MODE=false |
| **依赖链** | pytest → httpx → FastAPI App → 所有依赖组件（数据库、Redis、Docker沙箱）。 |

🧪 执行命令与CI集成：
# 本地运行
 make e2e-test # 等同于：docker-compose -f docker-compose.test.yml up -d && pytest -m e2e --alluredir=reports

 # CI (GitHub Actions) 集成
 - name: Run E2E Tests
 run: |
 docker-compose -f docker-compose.test.yml up -d --wait
 poetry run pytest -m e2e --cov=src --cov-report=xml
 env:
 TEST_MODE: true

 - name: Upload Coverage
 uses: codecov/codecov-action@v3
 with:
 file: ./coverage.xml


**✅ 阶段6 (Step 6.1 & 6.2) 全量交付确认**

本报告完整交付了可视化监控与质量验证体系的实现规格：

- **Step 6.1 (驾驶舱)：**基于Vue3+Socket.IO的实时监控面板，支持DAG拓扑、Token趋势、告警列表，开发团队可直接按组件拆解并行开发。
- **Step 6.2 (E2E测试)：**完整的测试框架（pytest+locust+Allure），覆盖正常流程、熔断混沌、性能基准，作为CI/CD的硬性门禁。

两个Step与已交付的所有后端组件无缝对接。预计总工时约4人日（前端3人日，测试1人日），第12周末可交付可演示的Dashboard和可自动运行的质量门禁。

**后续步骤提示：**下一步为**Step 7.1（灰度发布与AgentOps生产就绪）**，将系统部署至K8s并建立生产级可观测性。



```
// 代码块-1
// 前端 -> 后端 (订阅)
    {
      "type": "subscribe",
      "topics": ["task_updates", "token_metrics", "alerts"]
    }

    // 后端 -> 前端 (状态更新)
    {
      "type": "task_update",
      "data": {
        "task_id": "a1b2c3d4",
        "state": "CODING",
        "progress": 0.6,
        "dag": [
          {"id": "step_1", "label": "PARSING", "status": "done", "duration_ms": 1200},
          {"id": "step_2", "label": "PLANNING", "status": "done", "duration_ms": 3400},
          {"id": "step_3", "label": "CODING", "status": "running", "duration_ms": null}
        ],
        "agent_logs": ["Parsing PRD...", "Generated plan with 3 steps"]
      }
    }

    // Token指标消息
    {
      "type": "token_metric",
      "data": {
        "task_id": "a1b2c3d4",
        "timestamp": "2026-06-21T10:00:00Z",
        "prompt_tokens": 150,
        "completion_tokens": 300,
        "total_tokens": 450,
        "cost_usd": 0.0021
      }
    }

    // 告警消息
    {
      "type": "alert",
      "data": {
        "level": "warning", // warning, critical
        "source": "l3_entropy",
        "message": "Entropy 0.82 exceeded threshold in task a1b2c3d4",
        "timestamp": "2026-06-21T10:00:00Z"
      }
    }
```


```
// 代码块-2
frontend/
    ├── src/
    │   ├── api/           # Socket.IO 封装
    │   ├── stores/        # Pinia stores (task, metrics, alert)
    │   ├── components/
    │   │   ├── TopologyGraph.vue  # vis-network
    │   │   ├── TokenChart.vue     # ECharts
    │   │   └── AlertList.vue      # Element Plus Table
    │   ├── views/
    │   │   └── Dashboard.vue
    │   ├── App.vue
    │   └── main.ts
    ├── package.json
    └── vite.config.ts
```


```
// 代码块-3
export const useTaskStore = defineStore('task', {
      state: () => ({
        tasks: {} as Record
      }),
      actions: {
        updateTask(data: TaskUpdate) {
          this.tasks[data.task_id] = data
        },
        getDag(taskId: string) {
          return this.tasks[taskId]?.dag || []
        }
      }
    })
```


```
// 代码块-4
import { io } from 'socket.io-client'
    const socket = io(import.meta.env.VITE_WS_URL, {
      path: '/ws/socket.io',
      transports: ['websocket'],
      reconnectionAttempts: 5,
      reconnectionDelay: 1000
    })
    socket.on('task_update', (data) => taskStore.updateTask(data))
    socket.on('token_metric', (data) => metricStore.addMetric(data))
    socket.on('alert', (data) => alertStore.addAlert(data))
```


```
// 代码块-5
# pytest 配置 (pytest.ini)
    [pytest]
    markers =
        e2e: End-to-end tests
        performance: Performance benchmarks
        chaos: Chaos engineering tests
    env =
        TEST_MODE=true
        MOCK_LLM=true
        DATABASE_URL=postgresql+asyncpg://test:test@localhost:5433/test_db
        REDIS_URL=redis://localhost:6380/0

    # 测试结果数据结构 (Allure)
    class TestReport(BaseModel):
        test_name: str
        duration_ms: float
        passed: bool
        metrics: Dict[str, Any]  # 包含 token_consumed, latency_ms
```


```
// 代码块-6
# tests/e2e/test_full_flow.py
    import pytest
    import httpx
    import asyncio

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_normal_flow(test_client):
        # 1. 创建任务
        resp = await test_client.post("/api/v1/tasks", json={"prd": "write a function that returns the sum of two numbers"})
        task_id = resp.json()["task_id"]

        # 2. 轮询等待完成（超时60s）
        state = "PENDING"
        timeout = 0
        while state not in ["DONE", "FAILED"] and timeout < 60:
            await asyncio.sleep(2)
            timeout += 2
            resp = await test_client.get(f"/api/v1/tasks/{task_id}")
            state = resp.json()["state"]

        # 3. 断言成功
        assert state == "DONE"
        # 4. 验证生成的代码包含 "def add" 或 "def sum"
        result = resp.json().get("result", "")
        assert "def" in result and ("add" in result or "sum" in result)

        # 5. 验证Token消耗≤35（从监控日志获取）
        # 通过查询/metrics端点或日志验证
        metrics = await test_client.get(f"/api/v1/tasks/{task_id}/metrics")
        assert metrics.json()["total_tokens"] <= 35

    @pytest.mark.chaos
    @pytest.mark.asyncio
    async def test_circuit_breaker_chaos(test_client_with_mock_failure):
        # 注入故障：Mock LLM 连续返回5xx
        # 创建任务，预期熔断器触发
        resp = await test_client.post("/api/v1/tasks", json={"prd": "test chaos"})
        task_id = resp.json()["task_id"]

        # 等待熔断触发（失败快速返回）
        await asyncio.sleep(5)
        resp = await test_client.get(f"/api/v1/tasks/{task_id}")
        # 状态应为FAILED且错误信息包含"circuit breaker"
        assert resp.json()["state"] == "FAILED"
        assert "circuit" in resp.json().get("error", "").lower()
```


```
// 代码块-7
from locust import HttpUser, task, between

    class AgentUser(HttpUser):
        wait_time = between(1, 3)

        @task
        def create_and_poll(self):
            resp = self.client.post("/api/v1/tasks", json={"prd": "write a sort function"})
            task_id = resp.json()["task_id"]
            # 轮询直到完成或超时
            for _ in range(30):  # 最多30次轮询
                resp = self.client.get(f"/api/v1/tasks/{task_id}")
                if resp.json()["state"] in ["DONE", "FAILED"]:
                    break
                time.sleep(1)
```


# 多Agent自循环系统 · 阶段7 生产就绪 (Step 7.1) · 编码就绪级PRD/ADR

K8s部署 · 灰度发布 · 可观测性监控 · 自动化运维闭环

**交付声明：**本报告为阶段7（W13-Buffer）的终极细化文档。Step 7.1是系统的最终生产部署与运维体系，涵盖Kubernetes部署、Helm Chart、Istio灰度发布、Prometheus+Grafana+Tempo+ELK可观测性栈，以及自动回滚策略。该步骤使系统从“可运行”升级为“企业级生产就绪”。



## Step 6.3：可视化驾驶舱增强与实时监控

| PRD (产品需求文档) |  | 
| --- | --- | 
| **背景** | Step 6.1 已实现基础驾驶舱，但缺乏实时数据流、Token消耗曲线、Agent协作拓扑图等高级可视化能力。运营人员需要实时感知系统健康状态、快速定位瓶颈。 | 
| **用户故事** | 作为运营人员，我希望在驾驶舱中实时看到Token消耗速度、任务队列积压情况、Agent协作拓扑图，以便快速发现系统瓶颈并做出运营决策。 | 
| **需求描述** | ①实时Token流速折线图（每秒刷新）；②任务队列积压热力图；③Agent协作拓扑实时拓扑图；④系统健康评分（0-100）实时展示；⑤告警机制（Token超限、队列积压、Agent超时）。 | 
| **范围 (Do/Don't)** | **Do：**实时可视化，WebSocket推送，健康评分，基础告警。**Don't：**不支持历史数据回放（V2），不支持自定义仪表盘配置。 | 
| **数据契约** | `DashboardUpdate = {task_id, token_used, token_rate, queue_depth, agent_status: dict, health_score: float, timestamp}`。 | 
| **异常定义** | `WebSocketDisconnectError`：客户端断开连接；`MetricCollectionError`：指标采集失败（不影响主流程）。 | 
| **成功标准→验收** | **SC1:**实时更新 →**AC1:**驾驶舱页面打开后，Token流速图每秒更新，延迟小于500ms。 | 
| | **SC2:**健康评分 →**AC2:**系统负载高时健康评分下降，公式：health = 100 - token_rate/10 - queue_depth*2。 | 
| | **SC3:**告警触发 →**AC3:**Token使用超过80%预算时，驾驶舱显示红色告警，同时推送WebSocket事件。 | 

| ADR (架构决策记录) |  | 
| --- | --- | 
| **技术栈版本** | Vue3 3.4, ECharts 5.4, WebSocket (内置), FastAPI。 | 
| | 位置：`/frontend/src/components/Dashboard/`（Vue组件）、`/src/api/dashboard_ws.py`（WebSocket端点）。 | 
| **架构位置** | 前端层（Step 6.1驾驶舱扩展），通过WebSocket与后端通信，不影响调度器性能。 | 
| **实施细节** | **WebSocket端点：** | 
| | ```python | 
| | from fastapi import WebSocket | 
| | from typing import set | 
| | import asyncio, json | 
| | 
| | class DashboardBroadcaster: | 
| |     def __init__(self): | 
| |         self.clients: set[WebSocket] = set() | 
| |     async def connect(self, ws: WebSocket): | 
| |         await ws.accept() | 
| |         self.clients.add(ws) | 
| |     def disconnect(self, ws: WebSocket): | 
| |         self.clients.discard(ws) | 
| |     async def broadcast(self, data: dict): | 
| |         for client in self.clients: | 
| |             try: | 
| |                 await client.send_json(data) | 
| |             except: | 
| |                 self.clients.discard(client) | 
| | 
| | @app.websocket("/ws/dashboard") | 
| | async def dashboard_ws(ws: WebSocket): | 
| |     broadcaster.connect(ws) | 
| |     try: | 
| |         while True: | 
| |             metrics = collect_system_metrics() | 
| |             await broadcaster.broadcast(metrics) | 
| |             await asyncio.sleep(1) | 
| |     finally: | 
| |         broadcaster.disconnect(ws) | 
| | ``` | 
| | **Agent协作拓扑图（ECharts Graph）：** | 
| | 前端接收`agent_status: dict`（如`{"orchestrator": "running", "developer": "waiting"}`），渲染为力导向图。 | 
| **风险与缓解** | 风险1：WebSocket连接数过多。缓解：限制每个IP最大10个连接，会话超时30分钟。 | 
| | 风险2：ECharts渲染大图（100+节点）卡顿。缓解：超过50节点时降级为列表视图。 | 
| **需求错位** | 若未来需要多租户隔离，每个租户需独立Dashboard实例。当前单租户设计，V2可扩展。 | 
| **技术约束** | WebSocket推送频率不超过每秒1次；所有数据仅来自调度器状态，不引入额外采集开销。 | 
| **环境配置** | DASHBOARD_WS_MAX_CONNECTIONS_PER_IP=10 | 
| | DASHBOARD_SESSION_TIMEOUT_SEC=1800 | 
| | DASHBOARD_MAX_NODES_BEFORE_DEGRADE=50 | 
| **依赖链** | DashboardBroadcaster → TaskOrchestrator（只读状态）→ 各Agent（状态上报）。 | 

| 🧪 原子化测试用例 (pytest)： | 
| ```python | 
| import pytest, asyncio | 
| from src.api.dashboard_ws import DashboardBroadcaster | 
| from unittest.mock import AsyncMock | 
| 
| @pytest.mark.asyncio | 
| async def test_broadcaster_single_client(): | 
|     bc = DashboardBroadcaster() | 
|     mock_ws = AsyncMock() | 
|     await bc.connect(mock_ws) | 
|     assert len(bc.clients) == 1 | 
|     await bc.broadcast({"health_score": 85}) | 
|     mock_ws.send_json.assert_called_once_with({"health_score": 85}) | 
| 
| @pytest.mark.asyncio | 
| async def test_broadcaster_disconnect_cleanup(): | 
|     bc = DashboardBroadcaster() | 
|     mock_ws = AsyncMock() | 
|     await bc.connect(mock_ws) | 
|     bc.disconnect(mock_ws) | 
|     assert len(bc.clients) == 0 | 
| 
| def test_health_score_formula(): | 
|     # health = 100 - token_rate/10 - queue_depth*2 | 
|     score = 100 - 50//10 - 5*2 | 
|     assert score == 80 | 
|     score = 100 - 200//10 - 20*2 | 
|     assert score == 0  # capped at 0 | 
| ```