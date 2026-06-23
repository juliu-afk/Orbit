# PRD+ADR_F3：运维工具面板

## Step F3：运维工具——备份/恢复 + 版本历史 + SOP 查看

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | 后端已交付备份管理器（PR #28）、版本注册表（PR #29）、DR 恢复脚本（PR #30），但前端缺少运维操作界面。运维人员需要在不登录服务器的情况下执行备份/恢复操作、查看版本发布历史、查阅灾难恢复 SOP。 |
| **用户故事** | 作为运维工程师，我在驾驶舱"运维"标签页可以：一键创建数据库快照并查看 SHA256 校验值；浏览版本发布历史（部署/回滚/金丝雀事件）；查看灾难恢复 SOP 手册的 4 个场景步骤。 |
| **需求描述** | ① **备份面板**——显示最近 5 个快照列表（名称/大小/时间/SHA256 前 8 位），"创建快照"按钮触发 backup API，进度反馈。② **版本历史时间线**——纵向时间轴展示发布事件（deploy/rollback/canary_start/canary_end），每条显示版本号/触发方式(manual/auto)/时间。③ **SOP 查看器**——Markdown 渲染 `docs/SOP-灾难恢复手册.md`，4 场景折叠面板，演练检查清单可编辑。④ **当前版本徽章**——顶部显示 `当前版本: v0.15.0`（从 versioning API 获取）。 |
| **范围 (Do/Don't)** | **Do：**快照列表+创建/版本时间线/SOP 渲染/版本徽章。<br>**Don't：**不实现在线恢复（那是危险操作，保留 CLI）；不实现迁移脚本执行。 |
| **数据契约** | **快照列表** `GET /api/v1/observability/health`（暂时复用，后续加独立端点）<br>**版本历史** VersionRegistry.list_releases() → REST endpoint（需新增 `GET /api/v1/versioning/releases`）<br>**当前版本** VersionRegistry.current_version() → REST endpoint（需新增 `GET /api/v1/versioning/current`） |
| **异常定义** | ① 备份 API 不可用 → "创建快照"按钮禁用，tooltip 说明原因。② 版本历史为空 → 展示空态插画 "尚无发布记录"。③ SOP 文件不存在 → 降级展示纯文本路径。 |
| **成功标准→验收** | **SC1:** 快照列表展示 → **AC1:** 页面加载后 2s 内展示最近快照（含大小和哈希）。<br>**SC2:** 版本时间线 → **AC2:** 展示最近 20 条发布事件，按时间倒序。<br>**SC3:** SOP 可读 → **AC3:** 4 个场景全部可展开/折叠。 |
| **待定决策** | **Q:** 是否需要独立的运维页面？→ **决议：** 作为 Dashboard 的第三个标签页（监控/聊天/运维），不新开路由。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **技术栈** | Vue 3.4 + Pinia；Markdown 渲染用 `marked`（已在项目，从 ECharts 同源）；不新增 npm 依赖。 |
| **决策** | 新增 `ops` Pinia Store 管理备份/版本/SOP 数据；OpsPanel 作为 Dashboard 第三个标签页。 |
| **架构位置** | `frontend/src/stores/ops.ts`（新增）、`frontend/src/components/ops/BackupPanel.vue`（新增）、`frontend/src/components/ops/VersionTimeline.vue`（新增）、`frontend/src/components/ops/SopViewer.vue`（新增）、`frontend/src/views/DashboardView.vue`（扩展——新增标签页）。 |
| **实施细节** | **BackupPanel：**调用备份列表 API → 渲染快照表格 → "创建快照"按钮 POST 触发 → loading 状态。**VersionTimeline：**CSS 纵向时间轴 + 事件卡片（deploy=绿色/rollback=红色/canary=蓝色）。**SopViewer：**fetch SOP.md → marked 渲染 HTML → 按 `## 场景` 分割为折叠面板。 |
| **风险** | SOP.md 文件较大（164 行）。缓解：首次加载后缓存到 localStorage，版本更新时刷新。 |
| **依赖链** | 依赖后端 PR #28（备份）+ PR #29（版本注册表）+ 需新增 2 个 REST 端点。 |

## 组件树

```
DashboardView (扩展——新增"运维"标签页)
└── OpsPanel (新增)
    ├── VersionBadge (新增)  # 当前版本徽章
    ├── BackupPanel (新增)   # 快照列表+创建按钮
    ├── VersionTimeline (新增)  # 发布事件时间轴
    └── SopViewer (新增)     # SOP 手册渲染
```

## 测试策略

| 层 | 用例 | 覆盖 |
|----|------|------|
| Store | 3 | ops store 初始化/快照加载/版本列表加载 |
| 组件 | 4 | BackupPanel 空态/VersionTimeline 事件颜色/SopViewer 折叠/VersionBadge 版本号 |
| E2E | 1 | 运维标签页 3 面板均加载成功 |
| **合计** | **8** | |
