# 阶段1 PRD —— Phase B 遗留项收尾

> 基于 2026-07-06 审计：19 项遗留中 5 项不过时，本次收尾。

## 1. 背景

2026-07-06 对 Orbit 全量开发产物审计，发现 19 项标注"待做/Phase B/后续 PR"的遗留。逐条评估后，5 项不过时且后端 API 已就绪，纯前端填空或小工作量。

**已排除的 14 项**：MCP 双向适配（已实现）、沙箱 BYOI（收益低）、时序图谱（V2 scope out）、Token 硬门禁（架构已解决）、HPA（桌面 exe 不适用）、DagNodeModal（UI 范式已变）、上下文 P1/P2（ContextPrebuilder 替代）、知识库 P0/P1/P2（自建方案替代）、覆盖率 95%（Charter 80% 已达标）、跨客户隔离（等 FDE 规划）。

## 2. 用户故事

| # | 优先级 | 故事 |
|---|:--:|------|
| US1 | P0 | 作为运维，我希望在驾驶舱看到 Trace 链路追踪视图，看到每个任务的时间瀑布和 span 详情 |
| US2 | P0 | 作为运维，我希望在驾驶舱管理配置——编辑 YAML、查看历史版本、对比差异、合并分支 |
| US3 | P1 | 作为系统，我希望周期分析执行轨迹，自动输出改进建议（失败率/误判率/效率），反馈到调度参数 |
| US4 | P1 | 作为用户，我希望双击 Orbit.exe 时不弹出 Windows SmartScreen 警告 |
| US5 | P2 | 作为开发者，我希望 2 条预存失败的测试通过，消除 CI 噪音 |

## 3. 验收标准

| # | 标准 | 对应 US |
|---|------|:--:|
| AC1 | TraceViewer 展示最近任务列表，点击展开时间瀑布图，span 可展开看详情 | US1 |
| AC2 | TraceViewer 支持导出 OTEL JSON 按钮 | US1 |
| AC3 | ConfigView 展示配置章节列表，点击进入 YamlEditor 编辑，保存触发 Git commit | US2 |
| AC4 | VersionHistory 展示 Git 历史记录（commit hash/时间/作者/消息），点击查看 diff | US2 |
| AC5 | ConfigView 支持分支列表查看、切换、创建、合并 | US2 |
| AC6 | `observability/feedback.py` 实现 FeedbackEngine，周期分析轨迹数据 | US3 |
| AC7 | FeedbackEngine 输出 ≥3 类改进建议 JSON，含 confidence 评分 | US3 |
| AC8 | `GET /api/v1/observability/feedback` 端点返回最新分析结果 | US3 |
| AC9 | `scripts/build-desktop.sh` 支持 EV 代码签名参数，文档记录购买和配置步骤 | US4 |
| AC10 | `test_task_failure_propagates` 和 `test_generate_stream` 通过 | US5 |

## 4. Non-Goals

- 不做 Trace 搜索/过滤（V2）
- 不做配置 YAML 语法校验（Monaco 内置）
- 不做反馈自动执行（只建议，不自动改参数）——人工审查后再应用
- 不做代码签名自动化 CI（证书在本地，CI 不可用）
- 不修非本次范围内的测试

## 5. 影响范围

| 系统 | 影响 |
|------|------|
| 前端 | 新增 4 组件（TraceViewer, ConfigView, YamlEditor, VersionHistory），修改 StatusBar/路由 |
| 后端 | 新增 `observability/feedback.py` + `GET /observability/feedback`，零改动已有模块 |
| 测试 | 修复 2 条预存失败，新增 2 条 feedback 测试 |
| 构建 | `build-desktop.sh` 新增签名步骤，文档新增签名 SOP |
| 防幻觉层 | 不受影响 |
| 调度器 | 不受影响 |
| 图谱 | 不受影响 |

## 6. 边缘情况

| 场景 | 预期行为 |
|------|---------|
| 无 Trace 数据 | TraceViewer 显示空态"暂无 Trace 数据" |
| Trace 数据超大（>1000 spans） | 懒加载 + 虚拟滚动，首屏 50 条 |
| 配置章节不存在 | YamlEditor 显示 404 提示 |
| Git 仓库损坏 | ConfigView 显示错误态 + 重新初始化按钮 |
| 合并冲突 | 显示冲突文件 + inline diff + 选择 ours/theirs/manual |
| 反馈分析时轨迹表为空 | 返回 `{ "data": null, "message": "暂无足够数据进行分析" }` |
| 证书未配置时构建 | build-desktop.sh 跳过签名步骤，输出黄色警告 |

## 7. 成功指标

| 指标 | 当前 | 目标 |
|------|:--:|:--:|
| 遗留项数量 | 19 | 14（5 项收尾完成） |
| 前端 Trace/Config 覆盖 | 0 页面 | 2 页面可用 |
| 审计反馈闭环 | 无 | 可输出分析报告 |
| SmartScreen 警告 | 每次弹出 | 签名后不弹出 |
| 预存测试失败 | 2 条 | 0 条 |

## 8. 待确认问题（已确认）

1. **代码签名证书**：→ **跳过**。OV/EV 需企业注册，个人项目不适用。商用阶段再买。
2. **TraceViewer 布局**：→ **StatusBar 浮层抽屉**，复刻 DAG/Schedule 模式。
3. **ConfigView 权限**：→ **MVP 不做权限**，所有用户可编辑。
