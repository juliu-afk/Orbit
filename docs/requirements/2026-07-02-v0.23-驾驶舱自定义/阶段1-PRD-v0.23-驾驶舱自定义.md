# 阶段1 PRD — v0.23 驾驶舱自定义（主题+布局+透明度+拖拽）

> 2026-07-02 | 待确认 | 前序: Step 10 PRD

## 用户故事
- US-1: 暗/亮主题一键切换，偏好持久化
- US-2: 文件树、右侧面板宽度可拖拽调整
- US-3: 窗口透明度/毛玻璃强度滑块可调
- US-4: 文件树、Agent 面板可切换左/右位置
- US-5: 所有设置在统一 el-dialog 设置面板管理

## 技术选型
| 决策 | 选型 | 理由 |
|------|------|------|
| 主题 | CSS `[data-theme="light"]` 变量覆盖 | 纯 CSS，不碰 Tauri |
| 透明度 | `--glass-opacity` + `--glass-blur` CSS 变量 | CSS-only |
| 拖拽 | 原生 pointer events | 零依赖 |
| 布局 | CSS Grid `grid-template-areas` 动态拼接 | 文件树/Agent 位置互换 |
| 持久化 | settings.ts Pinia store + localStorage | 统一管理 |
| 面板 | el-dialog (Element Plus) | 与现有对话框风格一致 |

## 改动范围
| 文件 | 操作 |
|------|------|
| stores/settings.ts | 新建——Pinia store 管理所有设置 |
| components/layout/SettingsDialog.vue | 新建——el-dialog 设置面板 |
| style.css | 修改——`[data-theme="light"]` + glass 变量 |
| views/TerminalShell.vue | 修改——拖拽分割线 + grid-areas 动态化 + FileTreePanel |
| components/layout/StatusBar.vue | 修改——⚙ 齿轮按钮 |

## 验收标准
- AC-1: 暗/亮主题切换正常，刷新后保持
- AC-2: 文件树和右侧面板可拖拽调整宽度，刷新后保持
- AC-3: 透明度滑块实时生效，刷新后保持
- AC-4: 文件树可切换左右位置，Agent 面板可切换左右位置
- AC-5: ⚙ 入口可见，设置面板正常
- AC-6: Vite build 通过
