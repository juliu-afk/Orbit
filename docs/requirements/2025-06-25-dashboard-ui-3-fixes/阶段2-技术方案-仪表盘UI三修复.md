# Orbit Dashboard UI 三修复

## 背景

用户反馈三个 UI 问题：
1. 页面有外部滚动条，需消除——聊天框和右侧监控面板内部各自滚动
2. 聊天发送按钮边框与输入框边框颜色/风格不一致
3. 缺少代码 diff 展示区——不在仪表盘常驻，代码生成完成后弹出

---

## 修复 1：消除外部滚动条

**文件**：`frontend/src/views/DashboardView.vue`

**改法**：`.workspace` 加 `overflow: hidden`（第 239 行）

```css
.workspace {
  display: flex;
  height: calc(100vh - 40px);
  overflow: hidden;  /* ← 新增 */
}
```

**理由**：`.workspace` 固定高度但无 overflow，子内容溢出 → 文档级滚动。两子元素已自带 `overflow-y: auto`（`.chat-panel__messages` 第 223 行、`.aside-col` 第 257 行），父容器裁剪后各自内部滚动正常工作——`overflow` 非继承属性。

---

## 修复 2：发送按钮边框统一

**文件**：`frontend/src/components/chat/ChatPanel.vue`

**问题**：输入框用 `box-shadow` 模拟边框、按钮用真实 `border` → 渲染位置不一致。Element Plus 按钮在 append 插槽内带默认亮色主题样式，与深色输入框不协调。

**改法**（替换第 281-299 行 CSS）：

```css
/* 输入框——用真实 border 替代 box-shadow */
.chat-panel__input :deep(.el-input__wrapper) {
  background: #0f0f1a;
  border: 1px solid #2a2a4a;
  border-right: none;
  box-shadow: none;
}
.chat-panel__input :deep(.el-input__wrapper:hover) {
  border-color: #3a3a5a;
}
.chat-panel__input :deep(.el-input__wrapper.is-focus) {
  border-color: #4caf50;
}
.chat-panel__input :deep(.el-input__inner) {
  color: #c0c0c0;
}

/* 发送按钮容器——与输入框 border 衔接 */
.chat-panel__input :deep(.el-input-group__append) {
  background: #1a1a2e;
  border: 1px solid #2a2a4a;
  border-left: none;
}

/* 发送按钮本身——覆盖 Element Plus 默认亮色样式 */
.chat-panel__input :deep(.el-input-group__append .el-button) {
  background: transparent;
  border: none;
  color: #4caf50;
  font-size: 13px;
  padding: 0 12px;
  height: 100%;
  margin: 0;
}
.chat-panel__input :deep(.el-input-group__append .el-button:hover) {
  background: rgba(76, 175, 80, 0.08);
  color: #66bb6a;
}
.chat-panel__input :deep(.el-input-group__append .el-button:disabled) {
  color: #555;
  background: transparent;
}
```

**关键**：输入框 `border-right: none` + append `border-left: none` → 视觉上一条连续边框。

---

## 修复 3：代码 Diff 弹出展示

### 3A. 后端 —— 扩展 WebSocket 事件载荷

**文件**：`src/orbit/events/schemas.py` 第 29-41 行

```python
class TaskUpdatePayload(BaseModel):
    task_id: str
    state: str
    progress: float
    dag: list[dict[str, Any]]
    timestamp: str
    output: str | None = None  # ← 新增：CODING/DONE 状态的代码产物
```

**文件**：`src/orbit/scheduler/orchestrator.py`

`_publish_task_update` 加 `context` 参数（第 98-121 行）：
- 签名加 `context: dict[str, Any] | None = None`
- 当 `state in ("CODING", "DONE") and context` 时提取 `context["artifacts"]["CODING"]`
- 传入 `TaskUpdatePayload(output=output)`

两处调用点传 context：
- 第 181 行 `run_task` 内：`self._publish_task_update(..., context=context)`
- 第 432 行 `_continue_from` 内：同上

### 3B. 前端 —— 类型扩展

**文件**：`frontend/src/types/dashboard.ts`

新增接口：
```typescript
export interface TaskUpdatePayload {
  task_id: string; state: string; progress: number;
  dag: Array<Record<string, unknown>>; timestamp: string;
  output?: string;
}
```

### 3C. 前端 —— taskStore 扩展

**文件**：`frontend/src/stores/task.ts`

新增状态：
- `codeOutput: ref<string | null>(null)` — 最新代码产物
- `hasCodeOutput: ref(false)` — 自动弹窗触发器

`handleTaskUpdate` 中提取：
```typescript
if (payload.output && typeof payload.output === 'string') {
  codeOutput.value = payload.output
  hasCodeOutput.value = true
}
```

新增方法：`consumeCodeOutput()` 关闭时清零 flag，`clearCodeOutput()` 重置时清数据。

### 3D. 前端 —— CodeDiffPanel 组件（新文件）

**文件**：`frontend/src/components/chat/CodeDiffPanel.vue`

纯展示组件，props 接收 `code: string`，emit `close` 事件。
- 深色 `<pre><code>` 块，等宽字体，可滚动
- 标题栏 + 关闭按钮
- 配色与现 HealthPanel/TokenChart 一致（`#0f0f1a` 背景，`#2a2a4a` 边框）

### 3E. 前端 —— DashboardView 集成

**文件**：`frontend/src/views/DashboardView.vue`

```vue
<!-- 新增：代码输出抽屉 -->
<el-drawer v-model="showCodeDiff" title="Generated Code"
  direction="rtl" size="520px">
  <CodeDiffPanel v-if="taskStore.codeOutput"
    :code="taskStore.codeOutput" @close="handleCloseCodeDiff" />
</el-drawer>
```

```typescript
const showCodeDiff = ref(false)

// 代码输出就绪 → 自动弹窗
watch(() => taskStore.hasCodeOutput, (show) => { if (show) showCodeDiff.value = true })

function handleCloseCodeDiff() {
  showCodeDiff.value = false
  taskStore.consumeCodeOutput()
}
```

---

## 影响范围

| 文件 | 操作 | 改动量 |
|------|------|--------|
| `frontend/src/views/DashboardView.vue` | 修改 | CSS +1行，模板 +10行，script +8行 |
| `frontend/src/components/chat/ChatPanel.vue` | 修改 | CSS 块替换，~30行 |
| `frontend/src/components/chat/CodeDiffPanel.vue` | **新建** | ~60行 |
| `frontend/src/stores/task.ts` | 修改 | +15行 |
| `frontend/src/types/dashboard.ts` | 修改 | +5行 |
| `src/orbit/events/schemas.py` | 修改 | +1行 |
| `src/orbit/scheduler/orchestrator.py` | 修改 | ~10行 |

无新依赖，无数据库变更。

## 验证

1. `cd frontend && CI=true pnpm build` — TS 编译 + Vite 构建通过
2. `cd backend && pytest tests/unit/ tests/integration/ -q` — 507 全绿
3. 启动 exe → 打开仪表盘 → 确认页面无外部滚动条
4. 聊天框输入 → 确认发送按钮边框与输入框一致
5. 触发代码生成任务 → CODING/DONE 状态时自动弹出右侧抽屉展示代码
