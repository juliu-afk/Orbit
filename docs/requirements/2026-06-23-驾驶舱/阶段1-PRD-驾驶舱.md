# 阶段1 PRD — Orbit 驾驶舱（Step 6.1）

> 基线：`docs/PRD+ADR_6阶段.md` Step 6.1（PRD+ADR 已定稿）。
> 本文档在其基础上补充边缘情况、UI 状态矩阵、数据流细节，作为阶段2技术方案的输入约束。

## 1. 背景与问题

当前 Orbit 系统仅通过 CLI 和 REST API 交互。运维/PM 无法直观了解任务执行状态、Agent 协作拓扑、Token 消耗和防幻觉告警。需要 Web 驾驶舱提供实时可视化。

**当前系统状态（基线）**：
- 后端：FastAPI + REST（`/api/v1/tasks`），**无 WebSocket 基础设施**
- 调度器：`Scheduler` + `TaskGraph`（DAG 节点 `GraphNode`，状态 `NodeStatus`）
- 防幻觉：8 层验证，`ValidationResult` / `HallucinationError` 数据模型已就绪
- 网关：`LLMClient` + `CircuitBreaker`，Token 计数有 `LLMResponse.usage`
- 前端：**不存在**，`/frontend/` 目录需从零创建

## 2. 用户故事（P0/P1/P2）

### P0（MVP 必须交付）
| # | 作为 | 我希望 | 以便 |
|---|---|---|---|
| US1 | 技术负责人 | 打开 Dashboard 看到当前运行任务的 DAG 拓扑图 | 快速判断任务执行到哪个步骤、哪个节点卡住 |
| US2 | 运维 | 看到实时 Token 消耗折线图 | 监控成本，发现异常飙升 |
| US3 | 技术负责人 | 看到最新防幻觉告警列表 | 第一时间发现幻觉事件并介入 |
| US4 | 任何用户 | 断线后自动重连 | 不因网络抖动丢失监控视图 |

### P1（重要但可延后）
| # | 作为 | 我希望 | 以便 |
|---|---|---|---|
| US5 | 技术负责人 | 点击 DAG 节点弹出详情 Modal | 查看该步骤的输入/输出/耗时/错误日志 |
| US6 | 运维 | 看到任务列表（历史+当前） | 切换查看不同任务的 DAG |

### P2（V2）
| # | 作为 | 我希望 | 以便 |
|---|---|---|---|
| US7 | PM | 创建/取消任务 | 不离开驾驶舱就能发起新任务 |
| US8 | 运维 | 导出 Token 消耗报表 | 成本核算 |

## 3. 功能需求

### 3.1 WebSocket 数据通道

**后端新增**：FastAPI 挂载 `socketio.AsyncServer`，端点 `/ws/dashboard`（Socket.IO namespace `/dashboard`）。

**推送事件类型**（PRD+ADR 代码块-1 定义）：

| 事件名 | 方向 | Payload | 触发条件 |
|---|---|---|---|
| `task:update` | S→C | `{task_id, state, progress, dag: [{node_id, agent_role, status, duration_ms}], timestamp}` | 调度器状态变更 |
| `token:update` | S→C | `{task_id, prompt_tokens, completion_tokens, total_tokens, timestamp}` | LLM 调用完成 |
| `alert:new` | S→C | `{task_id, level: "entropy"/"z3"/"config_drift"/"runtime", message, severity: "warning"/"critical", timestamp}` | 防幻觉层触发异常 |
| `dashboard:subscribe` | C→S | `{task_id}` | 客户端订阅特定任务 |

**断线重连**（PRD+ADR Q1 决议：Socket.IO 自带）：
- 指数退避：1s → 2s → 4s → 8s → 16s（最多 5 次）
- 5 次失败后显示"连接已断开"遮罩层 + 手动重连按钮
- 重连成功后自动重新订阅当前 task_id

### 3.2 DAG 拓扑图

- **渲染库**：`vis-network` 9.x（PRD+ADR 已决议）
- **布局**：`hierarchical`，方向 `LR`（左→右），`physics: false`
- **节点**：圆形，颜色映射 `NodeStatus`
  - `pending` → 灰色 `#909399`
  - `running` → 黄色 `#E6A23C`（加脉冲动画 CSS）
  - `success` → 绿色 `#67C23A`
  - `failed` → 红色 `#F56C6C`
  - `skipped` → 虚线边框灰色
- **边**：箭头 `from→to`，颜色跟随源节点状态
- **大图策略**（PRD+ADR 风险1缓解）：节点 >50 时自动折叠已完成叶子节点，仅保留失败/运行中 + 1 层上游
- **交互**：点击节点 → Modal（US5，P1），展示 `{agent_role, status, input, output, error, retry_count, duration_ms}`

### 3.3 Token 消耗折线图

- **渲染库**：ECharts 5.5（PRD+ADR 已决议）
- **双 Y 轴**：左轴 `prompt_tokens` / `completion_tokens`（堆叠面积图），右轴 `total_tokens`（折线）
- **X 轴**：时间戳（距首次推送到当前）
- **数据窗口**：最近 100 个数据点（PRD+ADR 风险2缓解），超过则 shift 丢弃最早点
- **空态**：无任务时显示"暂无 Token 数据"占位
- **Tooltip**：悬停显示精确数值 + 时间

### 3.4 告警列表

- **渲染库**：Element Plus `el-table`
- **列**：时间 / 级别（tag 颜色：`warning` 橙色 / `critical` 红色）/ 类型（entropy/Z3/config_drift/runtime）/ 消息摘要
- **容量**：最近 20 条（PRD+ADR 定义）
- **空态**：无告警时显示"✅ 无告警"
- **自动滚动**：新告警插入顶部，高亮 2s 后恢复正常

### 3.5 全局状态栏

- 页面顶部固定栏
- 显示：WebSocket 连接状态（🟢已连接 / 🔴已断开）/ 当前查看任务 ID（截断显示前8字符）/ 最后更新时间
- 连接状态断线时闪烁红色脉冲

## 4. 边缘情况矩阵

| 场景 | 前端行为 | 后端责任 |
|---|---|---|
| **首次加载无任务** | DAG 区显示"暂无运行任务"，Token 图显示占位，告警列表显示"无告警" | 返回空状态，不报错 |
| **WS 连接超时（>5s）** | 显示"连接中..."加载态，5s 后提示"连接超时，正在重试" | Socket.IO connect_timeout=5000 |
| **WS 断线** | 自动重连（指数退避×5），失败后显示遮罩+手动重连按钮 | 无需额外处理（Socket.IO 自带） |
| **后端推送数据字段缺失** | 显示 `---` 占位符，不崩溃（PRD+ADR 异常定义） | 后端保证必填字段不为 null |
| **DAG 空图（任务刚创建，无节点）** | DAG 区显示"任务已创建，等待调度..." | 推送 `dag: []` |
| **DAG 超大（>50 节点）** | 自动折叠已完成叶子节点 | 后端不做限制，前端做折叠 |
| **Token 图长时间无更新（>30s）** | 最后数据点不变，不自动清空 | 无任务时停止推送，不发送空包 |
| **浏览器窗口缩放到 1280×720** | 三列布局变为单列堆叠（响应式，PRD+ADR 需求⑤） | 不涉及 |
| **多个浏览器 Tab 同时打开** | 每个 Tab 独立 Socket.IO 连接，各自订阅 | 后端广播到所有订阅者（房间模式） |
| **后端重启** | WS 断线→自动重连→恢复订阅 | Socket.IO 重连后客户端重新 emit `dashboard:subscribe` |

## 5. UI 布局

### 5.1 桌面端（1920×1080）

```
┌─────────────────────────────────────────────────────────┐
│ 🟢 已连接 │ 任务: a1b2c3d4... │ 最后更新: 14:32:05     │ ← 全局状态栏 (h=36px)
├──────────────────────┬──────────────────────────────────┤
│                      │  Token 消耗                      │
│   DAG 拓扑图         │  ┌───────────────────────────┐   │
│   (vis-network)      │  │  📈 ECharts 折线图        │   │
│                      │  │  双Y轴: prompt/completion  │   │
│   占 60% 宽度         │  │                            │   │
│   占 55% 高度         │  └───────────────────────────┘   │
│                      │  占 40% 宽度, 55% 高度            │
│                      ├──────────────────────────────────┤
│                      │  告警列表 (el-table)              │
│                      │  时间 │ 级别 │ 类型 │ 消息        │
│                      │  占 40% 宽度, 45% 高度            │
├──────────────────────┴──────────────────────────────────┤
│  任务列表（P1）: [任务ID] [状态] [进度] [创建时间]       │ ← 底部栏, 可折叠
└─────────────────────────────────────────────────────────┘
```

### 5.2 响应式断点（1280×720）

单列堆叠：全局状态栏 → DAG 图（100% 宽）→ Token 图（100% 宽）→ 告警列表（100% 宽）。滚动查看。

### 5.3 加载态

- **首次连接**：全屏居中 Spin + "正在连接 Orbit 调度器..."
- **DAG 加载中**：vis-network 区域显示 Skeleton 占位
- **Token 图加载中**：ECharts 区域显示 Skeleton 占位

### 5.4 错误态

- **连接失败**：遮罩层 "⚠️ 无法连接到 Orbit 服务" + "检查后端是否启动" + 手动重连按钮
- **DAG 渲染异常**：ErrorBoundary 捕获，显示 "DAG 渲染失败" + 错误信息 + 重试按钮

## 6. 数据流

```
调度器 Scheduler.state_transition()
  → 发布事件到 asyncio.Queue (event_bus)
  → WebSocket 广播器消费 Queue
  → socketio.AsyncServer.emit("task:update", data, room=task_id)

LLMClient.generate()
  → 返回 LLMResponse(usage=...)
  → 调度器提取 usage → emit("token:update", ...)

防幻觉层各 L.validate()
  → 返回 ValidationResult(passed=False)
  → 调度器收集 → emit("alert:new", ...)
```

**关键设计决策**：
- 不改造调度器内部状态机，而是注入 `EventBus`（asyncio.Queue），调度器状态变更时 `put_nowait` 事件
- WebSocket 广播器独立协程，消费 EventBus → emit 到 Socket.IO
- 调度器不感知 WebSocket，不引入反向依赖

## 7. 非功能需求

| 维度 | 目标 | 度量方式 |
|---|---|---|
| 首屏加载 | <2s | Lighthouse Performance >90 |
| WS 推送延迟 | <5s（从状态变更到前端渲染） | 手动触发任务 + 观察 |
| 内存 | Token 图保留 ≤100 点，ECharts dispose 旧实例 | Chrome DevTools Memory |
| 浏览器兼容 | Chrome/Firefox/Edge 最近 2 主版本 | 手动冒烟 |

## 8. 验收标准

| # | 标准 | 来源 | 验证方式 |
|---|---|---|---|
| AC1 | 首屏加载 <2s，Lighthouse Performance >90 | SC1 | Lighthouse 审计 |
| AC2 | DAG 节点颜色与 `NodeStatus` 一致，黄色=运行中，绿色=成功 | SC3 | 创建任务，截图对比 |
| AC3 | Token 折线图实时更新（有新数据点时图线延伸） | 隐式 | 手动创建任务，观察图表 |
| AC4 | 模拟高熵事件，告警列表 2s 内出现新条目 | SC4 | 触发 L3 阈值，计时 |
| AC5 | WS 断线后 1s 内开始重连，5 次内恢复 | 边缘情况 | 杀后端，重启，观察 |
| AC6 | 1280×720 分辨率下布局转为单列，无横向滚动条 | 需求⑤ | 浏览器 DevTools 模拟 |
| AC7 | 数据字段缺失时显示 `---`，页面不崩溃 | 异常定义 | Mock WS 推送空字段 |
| AC8 | 无任务时显示空态占位，不空白 | 边缘情况 | 首次加载截图 |

## 9. Non-Goals（明确不做）

- 任务创建/取消（V2 P2）
- 用户认证/登录（生产由反向代理 Basic Auth）
- 移动端适配
- 3D 拓扑图
- 暗色模式
- 多语言/国际化
- 数据导出（CSV/Excel）

## 10. 待确认问题

| # | 问题 | 当前假设 | 需确认 |
|---|---|---|---|
| Q1 | 前端项目是否复用现有 Python monorepo 还是独立 repo？ | `d:/Orbit/frontend/` 独立目录，Vite 脚手架 | 用户确认 |
| Q2 | Element Plus vs Ant Design Vue？ | PRD+ADR 指定 Element Plus 2.7 | 确认不换 |
| Q3 | vis-network vs @antv/g6？ | PRD+ADR 指定 vis-network 9.1 | 确认不换 |
| Q4 | 后端事件总线用 asyncio.Queue 还是 Redis Pub/Sub？ | asyncio.Queue（MVP 单进程足够） | 确认 |

---

> **阶段1基线确认后进入阶段2**：技术方案将覆盖前端组件树、Pinia Store 设计、WebSocket 后端实现、EventBus 机制、API 设计。
