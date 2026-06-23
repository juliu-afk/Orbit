# PRD+ADR_F2：自然语言聊天交互

## Step F2：NL 聊天——文本输入 + 项目上下文卡片

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | 后端已交付 NL 聊天 API（WebSocket `/api/v1/chat`，PR #32）和项目注册表（PR #31），用户可通过 WebSocket 输入自然语言文本并获得项目匹配结果。但前端缺少聊天交互界面，用户无法方便地使用此功能。 |
| **用户故事** | 作为用户，我在驾驶舱底部输入"支付超时了修一下"，系统自动匹配到我正在工作的项目并展示上下文卡片——项目名、匹配原因、置信度——然后我可以一键确认进入开发流程。 |
| **需求描述** | ① **聊天输入框**：底部固定文本输入框，placeholder "描述你的需求..."，支持 Enter 发送。② **匹配结果卡片**：收到服务端响应后展示候选项目列表——每个卡片显示项目名/匹配分数(进度条)/匹配原因/关键词高亮。③ **会话历史**：当前会话中的项目自动进入 session_projects，后续输入优先匹配。④ **确认/切换**：用户点击卡片确认项目，或下拉选择其他候选。⑤ **空态/错误**：无匹配时展示"未找到匹配项目，请重新描述"；WebSocket 断开时展示重连提示。 |
| **范围 (Do/Don't)** | **Do：**文本输入/结果卡片/会话历史/确认交互。<br>**Don't：**不实现多轮对话（Phase 2）；不实现语音输入；不替代驾驶舱主流程。 |
| **数据契约** | **WS 发送:** `{ text: str, session_projects?: [str] }` <br>**WS 接收:** `{ code: 0, data: { query, keywords, candidates: [{ project, score, reason, matched_keywords }], source, requires_confirmation } }` |
| **异常定义** | ① WS 断开 → 输入框变灰，展示"连接断开，正在重连..."。② 空输入 → 按钮禁用，placeholder 抖动提示。③ 后端返回 error → toast 提示，不展示卡片。 |
| **成功标准→验收** | **SC1:** 文本输入→匹配展示 → **AC1:** 输入文本后 2s 内展示匹配结果卡片（≥1 候选）。<br>**SC2:** 会话历史 → **AC2:** 连续 3 条输入均携带之前确认的项目名。<br>**SC3:** 降级体验 → **AC3:** WS 断开后 HTTP fallback 仍可用（如有）。 |
| **待定决策** | **Q:** 聊天面板位置？ → **决议：** Dashboard 右侧栏，可折叠，不影响主视图。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **技术栈** | Vue 3.4 + Pinia + 已有 `useWebSocket` composable；不新增 npm 依赖。 |
| **决策** | 新增 `chat` Pinia Store 管理聊天状态（消息历史/候选列表/会话项目）；ChatPanel 组件独立于 Dashboard，可折叠。 |
| **架构位置** | `frontend/src/stores/chat.ts`（新增）、`frontend/src/components/chat/ChatPanel.vue`（新增）、`frontend/src/components/chat/CandidateCard.vue`（新增）、`frontend/src/views/DashboardView.vue`（扩展——右侧栏）。 |
| **实施细节** | **Chat Store：**`useChatStore` 持有 `messages/ref`、`candidates/ref`、`sessionProjects/ref`。`send(text)` → WS 发送 JSON → 接收响应 → 更新 candidates。`confirm(projectName)` → 追加到 sessionProjects。**ChatPanel：**底部输入框 + 消息列表滚动区 + 顶部候选卡片横滑。**CandidateCard：**项目名(大字)+ 分数进度条 + 匹配原因标签 + 关键词高亮 + 确认按钮。 |
| **风险** | 长文本导致卡片溢出。缓解：描述截断 80 字 + tooltip 全文。 |
| **依赖链** | 依赖后端 PR #31（项目注册表）+ PR #32（上下文匹配+聊天 WS）。 |

## 组件树

```
DashboardView (扩展)
└── ChatPanel (新增，右侧栏可折叠)
    ├── CandidateCard ×N (新增)
    ├── MessageList (新增)
    └── ChatInput (新增)
```

## 测试策略

| 层 | 用例 | 覆盖 |
|----|------|------|
| Store | 4 | send/响应更新/confirm 追加/空输入校验 |
| 组件 | 4 | ChatPanel 渲染/CandidateCard 分数颜色/空态/断开提示 |
| E2E | 2 | 输入→展示→确认 全流程 / WS 断开降级 |
| **合计** | **10** | |
