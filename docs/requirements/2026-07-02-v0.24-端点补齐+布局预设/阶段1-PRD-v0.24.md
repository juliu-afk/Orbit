# 阶段1 PRD — v0.24 端点补齐 + 驾驶舱增强

> 2026-07-02 | 待确认 | 前序: v0.23 (#167)

## 背景

1. v0.22.1 中 CMDS/Agent 列表回退到硬编码，因为后端端点不存在。v0.24 补齐后端端点并接线前端。
2. v0.23 提供了布局自定义，但缺乏预设和一键切换。补充布局预设和快捷键面板。

## 用户故事

| ID | 故事 | 优先级 |
|----|------|--------|
| US-1 | Slash 命令列表由后端 `/api/v1/terminal/commands` 返回 | P0 |
| US-2 | Agent 列表由后端 `/api/v1/agents` 返回 | P0 |
| US-3 | 布局预设一键切换（默认/宽屏/专注模式） | P1 |
| US-4 | ⌘/ Ctrl+/ 弹出快捷键参考面板 | P1 |

## 技术方案

### 1. 后端端点

| 端点 | 文件 | 返回 |
|------|------|------|
| `GET /api/v1/terminal/commands` | terminal_routes.py | `{ commands: string[] }` |
| `GET /api/v1/agents` | agent_llm.py | `{ agents: Array<{name:string}> }` |

两个路由器均已注册，只需在已有 router 上加 `@router.get`。

### 2. 前端接线

- InputBox.vue: 恢复 apiGet fallback 模式（后端可用则动态，否则硬编码）
- AgentInfoPanel.vue: 同上

### 3. 布局预设

SettingsDialog 新增 Presets：
- **Default**: 文件树左 + 聊天中 + Agent 右（当前）
- **Wide**: 文件树折叠 + 聊天全宽 + Agent 右
- **Focus**: 文件树左 + 聊天中 + Agent 折叠

一键设置 fileTreeLeft/agentRight/fileTreeWidth/rightPanelWidth。

### 4. 快捷键面板

⌘/ 弹出 el-dialog，列出所有快捷键。纯展示组件 `ShortcutPanel.vue`。

## 改动范围

| 文件 | 操作 |
|------|------|
| `src/orbit/api/routes/terminal_routes.py` | 修改——`GET /commands` |
| `src/orbit/api/routes/agent_llm.py` | 修改——`GET /` |
| `InputBox.vue` | 修改——恢复 apiGet fallback |
| `AgentInfoPanel.vue` | 修改——恢复 apiGet fallback |
| `SettingsDialog.vue` | 修改——+ Presets 按钮 |
| `ShortcutPanel.vue` | **新建**——快捷键面板 |
| `TerminalShell.vue` | 修改——⌘/ handler + ShortcutPanel |
| `shell.ts` | 修改——+ layoutPreset 方法 |

## 验收标准

- AC-1: `/api/v1/terminal/commands` 返回命令列表
- AC-2: `/api/v1/agents` 返回 agent 列表
- AC-3: InputBox CMDS 从后端实时获取
- AC-4: AgentInfoPanel Agent 列表从后端实时获取
- AC-5: 布局预设一键切换
- AC-6: ⌘/ 弹出快捷键面板
- AC-7: pytest + vite build 通过
