# PRD+ADR_F4：资源调度视图

## Step F4：资源调度——ResourceGuard 状态 + 调度队列 + 工具状态

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | 后端已交付 ResourceGuard 熔断器（PR #27）、资源调度器（PR #33）、工具注册中心（PR #33），但前端缺少资源使用情况的可视化。运维人员需要看到当前资源消耗（Token预算/沙箱池/LLM调用速率）、调度队列积压、工具调用统计。 |
| **用户故事** | 作为运维工程师，我在驾驶舱"资源"标签页可以看到：当前有多少任务在排队（按优先级分桶）、Token 预算消耗进度条、沙箱池可用实例数、工具调用统计（Top 5 工具按调用次数），以便判断是否需要扩容或手动干预。 |
| **需求描述** | ① **资源配额仪表**：4 个圆形仪表盘——并发任务数(5max)/LLM调用速率(60/min max)/Token预算(100k max)/沙箱实例(3 max)。② **调度队列柱状图**：4 列（CRITICAL/HIGH/NORMAL/LOW），每列高度=排队任务数，CRITICAL 列有红色脉冲动画。③ **工具调用排行**：Top 5 工具卡片，显示名称/调用次数/最近调用时间/限流状态。④ **Token 预算进度条**（已有 TokenChart 扩展）：当前活跃任务 Token 消耗进度，超 80% 黄色预警，超 100% 红色。 |
| **范围 (Do/Don't)** | **Do：**配额仪表/队列柱状图/工具排行/Token 进度。<br>**Don't：**不实现在线调整配额（那是配置文件的职责）；不实现任务迁移/手动调度。 |
| **数据契约** | **队列状态** `ResourceScheduler.get_queue_status()` → REST endpoint（需新增 `GET /api/v1/scheduler/queue-status`）<br>**工具统计** `ToolRegistry.get_invocations()` → REST endpoint（需新增 `GET /api/v1/tools/stats`） |
| **异常定义** | ① 资源 API 不可用 → 仪表显示最后已知值 + "(数据过期)"。② 队列全空 → 柱状图全 0，顶部文字 "✅ 无排队任务"。③ 工具从未被调用 → Top 5 为空，展示 "尚无工具调用记录"。 |
| **成功标准→验收** | **SC1:** 配额仪表准确 → **AC1:** 4 个仪表数值与后端 `/scheduler/queue-status` 一致（抽样 5 次）。<br>**SC2:** 队列实时更新 → **AC2:** 后端队列变化后 5s 内前端柱状图更新。<br>**SC3:** 工具排行展示 → **AC3:** Top 5 工具按调用次数降序排列。 |
| **待定决策** | **Q:** 是否需要实时推送？→ **决议：** HTTP 轮询 10s 间隔（资源数据变化频率低，WS 过度设计）。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **技术栈** | Vue 3.4 + Pinia + ECharts 5；不新增 npm 依赖。 |
| **决策** | 新增 `resources` Pinia Store 管理资源/队列/工具数据；ResourcePanel 作为 Dashboard 第四个标签页。 |
| **架构位置** | `frontend/src/stores/resources.ts`（新增）、`frontend/src/components/resources/QuotaGauge.vue`（新增）、`frontend/src/components/resources/QueueChart.vue`（新增）、`frontend/src/components/resources/ToolRanking.vue`（新增）、`frontend/src/views/DashboardView.vue`（扩展——新增标签页）。 |
| **风险** | 4 个标签页 + ECharts 实例过多导致内存增长。缓解：标签页切换时销毁非活跃图表，切回时重建。 |
| **依赖链** | 依赖后端 PR #27（ResourceGuard）+ PR #33（ResourceScheduler + ToolRegistry）+ 需新增 2 个 REST 端点。 |

## 组件树

```
DashboardView (扩展——新增"资源"标签页)
└── ResourcePanel (新增)
    ├── QuotaGauge ×4 (新增)  # 并发/LLM/Token/沙箱
    ├── QueueChart (新增)     # CRITICAL/HIGH/NORMAL/LOW
    ├── TokenProgressBar (扩展 TokenChart)
    └── ToolRanking (新增)    # Top 5 工具
```

## 测试策略

| 层 | 用例 | 覆盖 |
|----|------|------|
| Store | 3 | resources store 初始化/队列加载/工具统计加载 |
| 组件 | 3 | QuotaGauge 颜色映射/QueueChart 柱状渲染/ToolRanking 排序 |
| E2E | 1 | 资源标签页 4 面板加载 |
| **合计** | **7** | |
