# 阶段2 技术方案 —— Phase B 遗留项收尾

> 基于阶段1 PRD（5 条验收标准 + 5 个 US），本次技术方案覆盖 5 项，无偏离。

## 1. 影响范围总览

| # | 项 | 类型 | 新增文件 | 修改文件 |
|---|------|------|---------|---------|
| US1 | TraceViewer | 前端 | 1 组件 + 1 store | StatusBar + shell.ts + TerminalShell |
| US2 | ConfigView | 前端 | 3 组件 + 1 store | 同上 |
| US3 | 审计数据飞轮 | 后端 | `feedback.py` + API 1 端点 | `observability/__init__.py` |
| US4 | exe 代码签名 | 文档 | `docs/SOP-代码签名.md` | `build-desktop.sh`（可选参数） |
| US5 | 测试修复 | 测试 | — | `test_stream.py` 1 行 |

## 2. US1 — TraceViewer.vue

### 2.1 架构决策

TraceViewer 采用 el-drawer 浮层抽屉模式，复刻 DAGDrawer/ScheduleDrawer 结构。

```
StatusBar "Trace" 按钮 → shell.toggleTrace() → TraceDrawer v-model:show
```

### 2.2 组件树

```
TraceDrawer.vue (el-drawer, size=700px, rtl)
├── 顶部: 最近任务下拉列表 (el-select, 调 GET /trace/recent)
├── 中部: 时间瀑布图 (SVG/Canvas 手写, 非第三方库)
│   ├── 横轴: 时间 (ms)
│   ├── 竖轴: span 名称
│   └── 色块: span.kind → 颜色映射
├── 侧栏: 选中 span 详情 (duration, status, attributes)
└── 底部: 导出 OTEL JSON 按钮
```

### 2.3 数据流

```
TraceDrawer mount → apiGet('/api/v1/observability/trace/recent?limit=20')
  → 用户选择 task_id
  → apiGet(`/api/v1/observability/trace/${task_id}`)
  → { root_spans: TraceSpan[], total_duration_ms, span_count }
  → 展平为 span 列表 + 计算时间轴
  → 渲染瀑布图
```

### 2.4 TypeScript 类型

```typescript
interface TraceSpan {
  span_id: string
  parent_span_id: string | null
  name: string
  kind: string        // "scheduler" | "agent" | "tool" | "validator" | "checkpoint"
  start_time: number  // unix ms
  end_time: number
  duration_ms: number
  status: string      // "ok" | "error"
  attributes: Record<string, string>
}

interface TraceTree {
  task_id: string
  root_spans: TraceSpan[]
  total_duration_ms: number
  span_count: number
}
```

### 2.5 改动清单

| 文件 | 操作 | 内容 |
|------|------|------|
| `frontend/src/components/observability/TraceDrawer.vue` | **新增** | TraceViewer 组件 (~200行) |
| `frontend/src/stores/shell.ts` | 修改 | +`showTrace` + `toggleTrace()` |
| `frontend/src/components/layout/StatusBar.vue` | 修改 | +Trace 按钮 + emit |
| `frontend/src/views/TerminalShell.vue` | 修改 | +TraceDrawer import + 渲染 |

## 3. US2 — ConfigView + YamlEditor + VersionHistory

### 3.1 架构决策

ConfigView 是 el-drawer 内嵌 el-tabs 三标签页。复用 Monaco 编辑器（已有 MonacoPanel 懒加载）。

```
StatusBar "Config" 按钮 → shell.toggleConfig() → ConfigDrawer v-model:show
```

### 3.2 组件树

```
ConfigDrawer.vue (el-drawer, size=800px, rtl)
├── 顶部: 章节选择器 (el-select, ConfigSection enum)
│   └── 分支名 + 切换按钮
├── el-tabs
│   ├── Tab "Edit" → YamlEditor (MonacoPanel, language="yaml")
│   │   └── 保存按钮 → apiPut + 刷新
│   ├── Tab "History" → VersionHistory
│   │   ├── 列表 (el-table, commit hash/时间/作者/消息)
│   │   └── 点击行 → diff 面板 (MonacoDiffEditor, unified diff)
│   └── Tab "Branches" → BranchManager
│       ├── 分支列表 (当前高亮)
│       ├── 创建/切换按钮
│       └── 合并按钮 (显示冲突状态)
└── 底部: 回滚按钮 (仅在 History tab)
```

### 3.3 数据流

```
ConfigDrawer mount → apiGet('/api/v1/config/branches/list')
  → 用户选择 section
  → apiGet(`/api/v1/config/${section}`) → YAML string → Monaco 展示
  → 用户编辑 → apiPut(`/api/v1/config/${section}`, {content, author:"ui"})
  → apiGet(`/api/v1/config/${section}/history`) → el-table
  → 点击某条历史 → apiGet(`/api/v1/config/${section}/diff?from=xxx&to=yyy`)
```

### 3.4 TypeScript 类型

```typescript
interface GitCommit {
  hash: string; full_hash: string; message: string
  author: string; timestamp: string
}
interface GitBranch { name: string; is_current: boolean; last_commit: string }
interface MergeResult { success: boolean; conflict_files: string[]; message: string }
```

### 3.5 改动清单

| 文件 | 操作 | 内容 |
|------|------|------|
| `frontend/src/components/config/ConfigDrawer.vue` | **新增** | 主抽屉 (~80行) |
| `frontend/src/components/config/YamlEditor.vue` | **新增** | Monaco YAML 编辑 (~60行) |
| `frontend/src/components/config/VersionHistory.vue` | **新增** | 历史列表+diff (~100行) |
| `frontend/src/components/config/BranchManager.vue` | **新增** | 分支管理 (~120行) |
| `frontend/src/stores/shell.ts` | 修改 | +`showConfig` + `toggleConfig()` |
| `frontend/src/components/layout/StatusBar.vue` | 修改 | +Config 按钮 + emit |
| `frontend/src/views/TerminalShell.vue` | 修改 | +ConfigDrawer import + 渲染 |

## 4. US3 — 审计数据飞轮 FeedbackEngine

### 4.1 架构决策

FeedbackEngine 是纯分析层——**只建议不自动执行**。手动触发（API 调用），读取轨迹数据，输出分析报告 JSON。

不接入调度器、不修改 Prompt/参数——人工审查后再应用。

### 4.2 数据流

```
GET /api/v1/observability/feedback
  → FeedbackEngine.analyze()
  → TrajectoryCollector.get_completed(limit=100)
  → TrajectoryCollector.get_failed(limit=50)
  → 三类分析:
      1. 失败率分析: failed / (completed + failed) × 100
      2. 误判率分析: DRIFTED 步骤占比
      3. 效率分析: avg_turns / avg_tool_calls / avg_duration
  → 与基线对比 (上次分析结果存 feedback_results 表)
  → 生成建议 JSON
```

### 4.3 FeedbackEngine 接口

```python
class FeedbackEngine:
    def __init__(self, db_path: str)
    async def analyze() -> FeedbackReport
    async def get_last_report() -> FeedbackReport | None

class FeedbackReport(BaseModel):
    generated_at: datetime
    period: tuple[datetime, datetime]  # 分析时间范围
    metrics: FeedbackMetrics
    recommendations: list[Recommendation]

class FeedbackMetrics(BaseModel):
    total_trajectories: int
    success_rate: float
    avg_turns: float
    avg_tool_calls: float
    avg_duration_ms: float
    drift_rate: float        # DRIFTED steps / total steps
    repeat_rate: float       # REPEATED steps / total steps
    top_error_messages: list[str]

class Recommendation(BaseModel):
    category: str            # "prompt" | "threshold" | "scheduling" | "tool"
    severity: str            # "high" | "medium" | "low"
    confidence: float        # 0.0-1.0
    description: str
    evidence: str
```

### 4.4 API 端点

```
GET /api/v1/observability/feedback
  → { code: 0, data: FeedbackReport, message: "ok" }
  → 无数据时: { code: 0, data: null, message: "暂无足够数据进行分析（需≥5条已完成轨迹）" }
```

### 4.5 改动清单

| 文件 | 操作 | 内容 |
|------|------|------|
| `src/orbit/observability/feedback.py` | **新增** | FeedbackEngine + Pydantic models (~150行) |
| `src/orbit/observability/__init__.py` | 修改 | +FeedbackEngine 导出 |
| `src/orbit/api/routes/observability.py` | 修改 | +GET /feedback 端点 (~30行) |
| `tests/unit/test_feedback.py` | **新增** | 单元测试 (~40行) |

## 5. US4 — exe 代码签名（文档+脚本）

### 5.1 决策

不买证书——先写 SOP 文档 + build-desktop.sh 签名占位参数。用户后续自行购买证书后，填路径即可。

### 5.2 改动清单

| 文件 | 操作 | 内容 |
|------|------|------|
| `docs/SOP-代码签名.md` | **新增** | 证书购买指南 + 签名命令 + 验证步骤 |
| `scripts/build-desktop.sh` | 修改 | +可选签名步骤 (`--sign` 参数, 检查 `$CODE_SIGN_CERT` 环境变量) |

## 6. US5 — 测试修复

### 6.1 问题定位

`test_all_event_types_have_valid_values` (test_stream.py:166):
- `StreamEventType.REFLECTION = 'reflection'` 不在有效类型集合中
- 需要检查 `StreamEventType` 枚举定义

`test_task_failure_propagates`: **不存在**——已在前序迭代中移除，无需修复。

### 6.2 修复

在 `StreamEventType` 枚举的 valid_values 集合中补充 `'reflection'`。

| 文件 | 操作 | 内容 |
|------|------|------|
| `tests/unit/test_stream.py` | 修改 | 修复 valid_values 断言 (~1行) |

## 7. 边界 case 清单

| 场景 | 预期行为 |
|------|---------|
| Trace 无数据 | TraceDrawer: el-select 空 + "暂无 Trace 数据" 空态 |
| Trace >1000 spans | 瀑布图虚拟滚动，首屏 50 条 |
| 配置章节不存在 | YamlEditor 显示 "选择章节" placeholder |
| Git 仓库损坏 | ConfigDrawer 显示错误态 + "重新初始化" 按钮 |
| 合并冲突 | BranchManager 显示冲突文件列表 + 支持逐文件解决 |
| 反馈分析 <5 条轨迹 | 返回 `data: null` + 提示信息 |
| 配置保存网络错误 | el-message 错误提示，内容保留在编辑器不回滚 |
| 证书未配置 | build-desktop.sh 跳过签名，黄色警告 `⚠️ 跳过代码签名` |

## 8. 依赖

- **无新依赖**。Monaco 编辑器已集成（MonacoPanel.vue），Element Plus el-drawer/el-tabs/el-select/el-table 已安装。
- Trace 瀑布图手写 SVG，不引入 vis-timeline 等第三方库。
- FeedbackEngine 只依赖 `trajectory.py` 的 TrajectoryCollector，无新增外部依赖。

## 9. 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| Trace 数据量大导致 SVG 渲染卡顿 | 前端性能 | 虚拟滚动 + 首屏 50 条 + 懒加载 |
| Config Git 仓库并发写冲突 | 数据损坏 | ConfigStore 已有文件锁，前端加乐观锁提示 |
| 反馈分析耗时过长 | API 超时 | 只分析最近 100 条轨迹，预估 <500ms |
| Monaco YAML 模式未加载 | 编辑无高亮 | 确认 MonacoPanel 支持 language="yaml" |

## 10. 与 PRD 对照

| PRD 验收标准 | 技术方案覆盖 | 位置 |
|:--|------|------|
| AC1 瀑布图+span详情 | §2 TraceDrawer 组件 | TraceDrawer.vue |
| AC2 OTEL 导出按钮 | §2.3 底部导出按钮 | TraceDrawer.vue |
| AC3 YAML编辑+历史 | §3 ConfigDrawer + VersionHistory | ConfigDrawer.vue + YamlEditor.vue + VersionHistory.vue |
| AC4 Git 历史+diff | §3.3 VersionHistory 数据流 | VersionHistory.vue |
| AC5 分支管理 | §3 BranchManager 标签页 | BranchManager.vue |
| AC6 FeedbackEngine | §4.3 接口定义 | feedback.py |
| AC7 ≥3 类建议 | §4.3 Recommendation 模型 | feedback.py |
| AC8 GET /feedback | §4.4 API 端点 | observability.py |
| AC9 代码签名 | §5 SOP 文档 + 脚本参数 | SOP-代码签名.md |
| AC10 测试通过 | §6 修复 valid_values | test_stream.py |
