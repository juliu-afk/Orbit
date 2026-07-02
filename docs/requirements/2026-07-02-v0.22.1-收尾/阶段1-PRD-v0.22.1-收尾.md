# 阶段 1：PRD — v0.22.1 Step 10 收尾

> **日期**: 2026-07-02 | **状态**: 待确认 | **前序**: [Step 10 PRD](../2026-07-01-Orbit-UI-Redesign/阶段1-PRD-Orbit-UI-Redesign.md)

## 背景

Step 10 (PR #161) 合并后有三项遗留，均在前序 PRD 覆盖范围内但实现遗漏。

## 用户故事

| ID | 故事 | 优先级 |
|----|------|--------|
| US-1 | 左侧文件树实际可用——能看到项目文件，点文件打开 Monaco 审查 | P0 |
| US-2 | Monaco 代码审查面板底部有 Problems/Outline/Tests/Terminal/Conflicts 标签页 | P0 |
| US-3 | Slash 命令列表从后端动态获取，不在前端硬编码 | P1 |
| US-4 | Agent LLM 面板的 Agent 列表从 `/api/v1/agents` 动态获取 | P1 |

## 技术方案要点

### 1. 文件树接入 TerminalShell

- TerminalShell `onMounted` 中 `GET /api/v1/files/tree` → `buildTree()` → `fileTree ref<FileNode[]>`
- 左侧面板：`<FileTreePanel :tree-data="fileTree" :selected-file="shell.selectedFile" @select-file="onSelectFile" />`
- `onSelectFile` → `editorStore.openFile(path)` + `shell.openFileReview(path)` → Monaco 面板从右侧滑出

### 2. MonacoPanel 底栏 tab

MonacoPanel 底部加 `el-tabs`，5 个 tab：

| Tab | 组件 | 数据源 |
|-----|------|--------|
| Problems | ProblemPanel | `useDiagnosticsStore().diagnostics` |
| Outline | OutlinePanel | 自取 API（组件内部） |
| Tests | TestPanel | 自取 API（组件内部） |
| Terminal | TerminalPanel | 自取 API（组件内部） |
| Conflicts | MergeConflictPanel | 自取 API（组件内部） |

布局：MonacoPanel 内部改为 flex-col → 上半 MonacoDiffEditor (flex-1) + 下半 el-tabs (200px shrink-0)

注：ReviewCommentPanel 不在此轮接入——需要 review session 上下文，后续 MonacoPanel 升级时再加。

### 3. Slash 命令动态化

- 后端无 `/api/v1/commands` 端点 → 在 `src/orbit/api/routes/` 新增，返回命令列表
- 或者更简单——前端 `InputBox.vue` 改用 `apiGet('/api/v1/commands')` 取列表，fallback 到硬编码
- 若后端端点不存在，先以 fallback 方式实现：尝试 fetch → 失败则用硬编码默认值

### 4. Agent 列表动态化

- `AgentInfoPanel.vue` 通过 `GET /api/v1/agents` 获取 agent 列表
- 若端点不存在，fallback 到硬编码默认值

## 改动范围

| 文件 | 操作 |
|------|------|
| `TerminalShell.vue` | 引入 FileTreePanel + fileTree 数据获取 |
| `MonacoPanel.vue` | 底部 + el-tabs + 5 个 tab 组件 |
| `InputBox.vue` | CMDS → apiGet fallback 模式 |
| `AgentInfoPanel.vue` | Agent 列表 → apiGet fallback 模式 |
| `shell.ts` | 无改动（已有 openFileReview/selectedFile） |

## 验收标准

| # | 标准 |
|---|------|
| AC-1 | 左侧文件树展示项目文件，点击文件 → Monaco 面板从右侧滑出 |
| AC-2 | Monaco 面板底部有 5 个 tab，切换正常 |
| AC-3 | Slash 命令优先从后端读取，失败则 fallback 硬编码 |
| AC-4 | Agent 列表优先从后端读取，失败则 fallback 硬编码 |
| AC-5 | Vite build 通过 |
