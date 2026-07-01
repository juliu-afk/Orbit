# 阶段 1：PRD — Orbit 驾驶舱 UI 翻新

> **日期**: 2026-07-01 | **版本**: v1.0 | **状态**: 待确认
>
> **背景**: 当前 Orbit 前端 (Vue3 + Element Plus + 手写暗色 CSS → Tauri WebView) 视觉风格偏向企业管理后台，与主流 Agent 工具 (Claude Code、Cursor、k9s) 的终端/原生质感差距大。本轮翻新不改变后端 API/数据模型——仅换前端的皮和交互范式。

## 1. 当前状态

| 维度 | 现状 | 问题 |
|------|------|------|
| **组件库** | Element Plus 2.7 (el-button/el-card/el-dialog/el-table…) | 管理后台味太重，跟 agent 工具气质不搭 |
| **布局** | 3 个独立路由页面 (Boot → Dashboard → Review)，页面间跳转 | 不是面板分屏，割裂感强 |
| **样式** | 手写 scoped CSS，暗色主题 #0a0a14 | 维护成本高，设计不统一 |
| **右键菜单** | 浏览器默认菜单 | 用户体验差，不像桌面应用 |
| **交互入口** | ChatPanel 里的 el-input + 按钮 | web 表单味，不是 agent 对话工具该有的样子 |
| **Agent 信息** | 散落在右侧 sidebar 混合展示 | 不够显眼，用户不知道"谁在干活" |
| **代码审查** | `/review/:taskId` 独立页面 → Monaco DiffEditor | 需路由跳转，打断主交互流 |
| **Tauri 集成** | 仅 minimize/close 按钮 | 没有利用 Tauri 原生能力 |

## 2. 用户故事

### P0 — 核心交互（必须交付）

| ID | 故事 | 验收标准 |
|----|------|---------|
| **US-1** | 作为开发者，我看到等宽字体终端风格的聊天界面，能通过文本输入与 Orbit agent 自然对话 | 输入框始终在底部，消息逐条渲染（带 `>` / `✦` / `✓` 前缀和 ANSI 着色），Ctrl+C/V 正常复制粘贴 |
| **US-2** | 作为开发者，我右键任意消息能弹出自定义菜单（复制/引用/打开文件/重新执行） | 浏览器默认右键菜单不出现，自定义菜单定位准确，操作执行正确 |
| **US-3** | 作为开发者，我能引用某条消息进行回复 | 右键→"引用"→气泡 chip 出现在输入框上方，`✕` 可取消 |
| **US-4** | 作为开发者，我能看到当前交互 agent 的 LLM 型号和运行中的 agent 角色列表 | 右侧信息面板常驻，实时反映当前 active agent 及模型 |
| **US-5** | 作为开发者，左侧文件树可折叠展开，选中文件后右侧/上方浮出 Monaco diff 面板 | ⌘B 切换文件树，代码审查不跳出当前窗口 |

### P1 — 体验增强（应交付）

| ID | 故事 | 验收标准 |
|----|------|---------|
| **US-6** | 作为开发者，窗口呈半透明玻璃质感，能看到桌面背景 | Tauri `transparent:true` + Mica/模糊，Windows 11 Mica / macOS Vibrancy / Windows 10 退化为纯色 fallback |
| **US-7** | 作为开发者，DAG 图、Token 图表、搜索通过底部状态栏图标 → 浮层/抽屉打开 | 入口在状态栏，浮层采用 Element Plus Drawer 或纯手写，打开后不遮挡主聊天区 |
| **US-8** | 作为开发者，聊天记录在关闭窗口后依然保留，重新打开能继续上次对话 | 复用现有 session/memory 持久化，不做改动 |
| **US-9** | 作为开发者，我能用 `↑↓` 键浏览历史消息，用 `Tab` 自动补全 slash 命令 | 键盘导航体验接近终端 |

### P2 — 锦上添花（可后续迭代）

| ID | 故事 | 验收标准 |
|----|------|---------|
| **US-10** | 作为开发者，面板布局可用鼠标拖拽分割线调整大小 | 类似 tmux/i3 的可拖拽 resizer（v0.22 不做——后续版本迭代） |
| **US-11** | 作为开发者，启动动画流畅过渡到主界面 | BootView 预检保留，视觉风格统一到终端设计语言（等宽字体、暗色调、进度条→终端风格） |
| **US-12** | 作为开发者，未来可自选色调/透明度/布局 | 设置面板→CSS 变量切换，v0.23/v0.24 迭代 |

## 3. 技术选型决策

| 决策点 | 选型 | 排除项及理由 |
|--------|------|-------------|
| **渲染引擎** | DOM + 终端 CSS | xterm.js：Canvas 渲染增加坐标反查复杂度，不适合"消息级结构化交互"。DOM 天然支持消息节点、右键定位、引用 chip |
| **消息模型** | 结构化——每条消息独立 Vue 组件节点 | 非结构化字符流：需要手动维护行号→消息映射，增加无谓复杂度 |
| **组件库** | 全部卸载 Element Plus，手写或引入轻量 utility（VueUse 等） | Element Plus：太重、视觉风格不匹配。但保留 el-drawer/el-popover 等少数纯交互组件可考虑 |
| **样式** | Tailwind CSS 或 UnoCSS + CSS 变量体系 | 手写 scoped CSS：维护成本高、不一致。用 utility class + design tokens 统一视觉 |
| **窗口透明** | Tauri v2 `transparent: true` + CSS `backdrop-filter: blur()` | 不做透明则跟普通 Electron 应用无异 |
| **持久化** | 保留现有 session/message 存储，不做改动 | 不需要 |

## 4. 布局设计

```
┌──────┬──────────────────────────────┬──────────────────────┐
│      │                              │  ◉ CLAUDE OPUS      │  ← 交互 agent 身份
│ FILE │   orbit> 输入框 + 消息流...   │  ───────────────     │
│ TREE │                              │  Running agents:     │
│      │   agent [opus]> analyzing... │  · clarifier/gpt-4o  │
│ src/ │   ✦ found auth/middleware.py │  · context/haiku     │
│  auth│   ✓ [edit] auth/middleware   │  · factory/opus      │
│  api │                              │                      │
│ tests│   You> 这个文件再改一下       │  budget 45.2k        │
│      │                              │                      │
│      │   agent [opus]> 明白，更新中  │  ───────────────     │
│      │                              │  [CODE REVIEW]       │  ← 需要时可切换面板
│      │   $ █                         │                      │
├──────┴──────────────────────────────┴──────────────────────┤
│ [DAG] [📊 Charts] [🔍]  │ auth/mw.py:53 ✓ │ orbit ◉ │ 45.2k │
└───────────────────────────────────────────────────────────┘
```

### 面板模式

| 状态 | 左 | 中 | 右 |
|------|-----|----|-----|
| **默认** | 文件树 (240px) | 终端聊天 (flex:1) | Agent 信息面板 (220px) |
| **代码审查** | 文件树 (240px) | 终端聊天 (flex:1) | Monaco diff (50% 宽度，从右滑出) |
| **深度审查** | 文件树 (240px) | 终端聊天 (60%) + Monaco diff (上方 40%) | Agent 信息 (220px) |

- 文件树：⌘B 折叠/展开
- DAG / Token Chart / 搜索 → 底部状态栏 icon 点击 → el-drawer 或浮层从右/下滑出
- Agent 信息面板始终可见（右侧），代码审查时被 Monaco 替换 or 并排

## 5. 前端架构变更

### 5.1 组件树（新）

```
App.vue
├── TerminalShell (主布局容器，CSS Grid)
│   ├── FileTreePanel.vue          (左侧，可折叠)
│   │   └── FileTreeNode.vue       (递归)
│   ├── TerminalChat.vue            (核心消息区)
│   │   ├── MessageItem.vue        (单条消息——agent/user/tool/error)
│   │   ├── InputBox.vue           (输入区 + 引用 chip + send 按钮)
│   │   ├── QuoteChip.vue          (引用气泡，在 InputBox 上方)
│   │   └── ContextMenu.vue        (全局自定义右键菜单)
│   ├── AgentInfoPanel.vue         (右侧——LLM 信息 + 运行中 agent)
│   ├── MonacoPanel.vue            (浮出代码审查面板)
│   └── StatusBar.vue              (底部——DAG/Chart/Search 入口 + 连接态)
├── DAGDrawer.vue                  (vis-network，el-drawer 或浮层)
├── TokenChartDrawer.vue           (ECharts，浮层)
└── SearchDrawer.vue              (搜索面板，浮层)
```

### 5.2 保留的模块（不改逻辑，只调整容器）

| 原文件 | 新位置/方式 | 说明 |
|--------|-----------|------|
| `MonacoDiffEditor.vue` | 嵌入 `MonacoPanel.vue` | 代码逻辑不动 |
| `DagCanvas.vue` | 嵌入 `DAGDrawer.vue` | vis-network 代码不动 |
| `TokenChart.vue` | 嵌入 `TokenChartDrawer.vue` | ECharts 代码不动 |
| `AgentLLMStatus.vue` | 嵌入 `AgentInfoPanel.vue` | 角色+模型展示不动 |
| `CircuitBreakerLight.vue` | 简化后嵌入 `StatusBar.vue` | 保留熔断状态灯 |
| `FileTreePanel.vue` / `FileTreeNode.vue` | 不变，移到左侧 | 保留文件树逻辑 |

### 5.3 卸载的模块

| 文件 | 原因 |
|------|------|
| `ChatPanel.vue` → 替换为 `TerminalChat.vue` | 整体交互范式改变 |
| `ChatStream.vue` → 合并进 `TerminalChat.vue` | SSE 流直接在消息列表渲染 |
| `DashboardView.vue` → 替换为 `TerminalShell.vue` | 不再是页面路由，改为单面板 |
| `ReviewView.vue` → 替换为 `MonacoPanel.vue` | 不再是路由，改为滑出面板 |
| `BootView.vue` → 保留但改为透明启动画面 | 去掉 Element Plus 依赖 |
| `SessionBar.vue` → 精简后嵌入 `StatusBar.vue` | 只保留 project badge + session dropdown |
| 大部分 Element Plus 组件依赖 | 视觉风格不匹配 |

### 5.4 路由简化

```
旧: / → /boot → /dashboard → /review/:taskId
新: / → /boot → / (单页主面板，一切交互在面板内完成)
```

不再有页面跳转。`/review`、`/search` 等行为由面板显隐控制，路由不做导航。

## 6. 数据流不变

- WebSocket → `useWebSocket` composable → 各 Pinia store（行为不变）
- SSE → `useEventSource` composable → 消息追加到 `chatStore`（行为不变）
- HTTP → `services/api.ts`（行为不变）
- 所有 Pinia store 接口不动，只调整组件如何消费 store 数据

## 7. 非目标 (Non-Goals)

- 不改后端 API 契约
- 不改数据库 schema
- 不改 Pinia store 接口（内部可调整，面向组件的 interface 不变）
- 不引入新的 LLM provider / agent 逻辑
- 不改 Tauri Rust 层（除窗口透明配置）

## 8. 边界 case 清单

| 场景 | 预期行为 |
|------|---------|
| WebSocket 断开 | StatusBar 连接灯变红，"重连中…" 文字，指数退避重连不影响 UI 操作 |
| SSE 流中断 | 消息显示 "[传输中断]" 标记，可点击重新请求 |
| 消息量超过 1000 条 | 虚拟滚动（Vue-virtual-scroller 或手写） |
| 透明窗口在 Windows 7/10 | 退化为纯色背景 rgba(10,10,20,1)，关闭 blur |
| 全屏模式 | 透明自动关闭（Windows 系统行为），全屏下纯色背景 |
| Tauri 最小化/恢复 | Agent 连接不断，恢复后 WebSocket 重新连接 |
| 窗口拖拽 resize | 面板 flex 比例保持，Monaco/Canvas 重新 layout |
| 代码审查打开时收到新 agent 消息 | 新消息追加到终端聊天，Monaco 面板不受影响 |
| 引用已删除的消息 | 引用 chip 显示 "[消息已删除]" 灰色文字 |
| 复制多行消息 | 保留 ANSI 纯文本（去除着色），换行符保留 |
| DAG 数据为空（无 running task） | 浮层显示 "无运行中任务" 空状态 |
| 文件树文件数量 > 500 | 树节点虚拟滚动，避免 DOM 爆炸 |
| 窗口从休眠恢复 | WebSocket reconnect，SSE 流不自动恢复（需用户重新触发） |

## 9. 防幻觉/调度器影响评估

**本轮改动不触及**：
- 调度器状态机（不改 `src/orbit/scheduler/` 任何代码）
- 防幻觉 L1-L8 层（不改判定逻辑）
- 图谱查询接口（不改 CodeGraph 任何代码）
- 沙箱执行（不改 Docker 隔离逻辑）

**间接受益**：
- 用户对 agent 角色+模型的可见性提升 → 更容易发现"错误 agent 在运行" → 有助于人工介入纠正 agent 行为偏差

## 10. 验收标准总表

| # | 标准 | 验证方式 |
|---|------|---------|
| AC-1 | 无 Element Plus 组件（el-button/el-card/el-dialog/el-table）出现在主界面 | 代码搜索 `el-` 标签 |
| AC-2 | 右键菜单为自定义菜单，浏览器默认菜单不出现 | 手动测试 |
| AC-3 | 引用消息功能正常：右键→引用→chip 出现→输入发送→chip 消失 | 手动测试 |
| AC-4 | Agent 信息面板实时显示交互 agent LLM 及运行中 agent | 手动测试 |
| AC-5 | 文件树可折叠展开，文件选择后 Monaco diff 在右侧出现 | 手动测试 |
| AC-6 | DAG / Token Chart / 搜索入口在底部状态栏可见 | 手动测试 |
| AC-7 | 窗口半透明效果可见（Windows 11 / macOS） | 手动测试 |
| AC-8 | 聊天记录保存到 session，关闭重开后恢复 | 自动测试 (Playwright) |
| AC-9 | 所有前端单元测试通过，覆盖率不下降 | CI `pnpm vitest run` |
| AC-10 | 冒烟测试通过（Boot → Dashboard 预检 → Agent 对话 → 代码审查） | Playwright E2E |
| AC-11 | Tauri 构建 `Orbit.exe` 正常运行 | `bash scripts/build-desktop.sh` |

## 11. 待确认问题

1. ~~xterm.js vs DOM + 终端 CSS~~ → **已确认：DOM + 终端 CSS**
2. ~~半透明窗口~~ → **已确认：Tauri transparent + Mica 毛玻璃**
3. ~~Tailwind CSS vs UnoCSS~~ → **已确认：Tailwind CSS**
4. ~~BootView 预检动画是否保留？~~ → **已确认：保留，视觉统一到终端设计语言**
5. ~~颜色主题方案？~~ → **已确认：暗色调 + 设计 token 体系，v0.22 不做用户自选**
6. ~~透明度/布局自选~~ → **已确认：v0.22 不做，硬编码最优布局，后续版本迭代**
