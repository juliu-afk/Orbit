# 阶段 1 PRD —— 聊天框智能模式 + Skill 自动路由

> 日期: 2026-07-13 | 分支: feat/chat-mode-skill-routing
> 更新: 用户确认范围扩大 + 三个设计决策确认

---

## 1. 背景

Orbit 聊天框当前有三个模式按钮（Ask / Edit / Agent），但**纯装饰性**——`currentMode` 只改 placeholder 文案，不控制任何实际行为。所有消息走同一条 WebSocket 路径。

同时 Orbit 已有丰富的底层智能基础设施，但聊天框没用上：

| 已有能力 | 位置 | 聊天框用到？ |
|----------|------|-------------|
| ChatterAgent chat/programming 意图分类 | `agents/chatter.py:222-229` | ✅ 用了 |
| ModeTuner "快点"/"深入" 自然语言检测 | `modes/tuner.py:78` | ❌ 只在 ClarifierAgent |
| Compose 7 个 SKILL.md 定义 | `compose/skills/` | ❌ 只在 spec 管道 |
| ComposeOrchestrator DAG 调度 | `compose/orchestrator.py` | ❌ 只能通过 spec YAML 触发 |
| 斜杠命令硬编码路由 | `chat.py:333-351` | ✅ 用了但不可扩展 |

**问题**：
1. 用户无法通过聊天框控制 Agent 权限级别
2. Skill 必须手动打斜杠，新增命令要改后端 if-else
3. Compose 管道和聊天框是两套独立系统，无法从聊天框触发多步编排
4. 没有 Skill 的可视化管理能力

**已确认的设计决策**：
- 模式按钮换成 Claude Code 的四级：**Manual / Edit Automatically / Plan / Auto Mode**
- Edit 确认方式：**首次弹确认 + 会话级记住**
- Skill 自动匹配阈值：**≥0.7 直接触发 / 0.4-0.7 提示确认 / <0.4 跳过**

---

## 2. 用户故事

### P0（核心——本次必须交付）

**US1: 四级权限模式生效**
> 作为开发者，我切换 Manual / Edit Automatically / Plan / Auto Mode 时，聊天框真正限制 Agent 的工具执行权限。

验收标准：
- **Manual**：每次工具调用都弹确认（读+写都确认）
- **Edit Automatically**：读工具自动放行，写工具首次弹确认 + "本会话记住"选项
- **Plan**：Agent 只做只读分析+方案设计，不执行任何写入。输出方案文档
- **Auto Mode**：全自动执行，不弹确认
- 切换模式时 UI 有视觉反馈（按钮高亮 + 输入框颜色变化）
- 模式状态通过 WebSocket 传给后端

**US2: Skill 斜杠自动补全 + 动态注册**
> 开发者打 `/` 时自动弹出所有已注册 Skill，新增 Skill 只需加 SKILL.md，无需改路由代码。

验收标准：
- `/` 触发动态 Skill 列表（从后端 `GET /api/v1/skills` 获取）
- 新增 SKILL.md → 重启后自动可用（或热更新后即时可用）
- 不在列表的 `/xxx` 当作普通文本发送

**US3: 自然语言自动匹配 Skill**
> 用户说"帮我审查一下最近改的代码"，系统自动识别意图并触发 review Skill。

验收标准：
- 非 `/` 开头时，ChatterAgent 检测是否为已知 Skill 的触发意图
- 置信度 ≥ 0.7：直接触发，告知用户"即将启动 XX 技能"
- 置信度 0.4-0.7：提示"是否要启动 XX 技能？"让用户确认
- 置信度 < 0.4：走现有 chat/programming 分类
- 多 Skill 匹配时展示候选列表（最多 3 个）

**US4: 聊天框调用 Compose 管道**
> 复杂需求（多步编排）从聊天框直接触发 ComposeOrchestrator，不写 spec YAML 文件。

验收标准：
- 用户输入"设计并实现 XXX"时，ChatterAgent 检测到多步需求
- 自动生成临时 spec → 调 ComposeOrchestrator → 流式输出进度到聊天框
- 单步 Skill（"审查代码"）仍走直接 Agent 执行，不走编排管道
- 编排结果（计划/任务/状态）在聊天框可见

### P1（增强——本次交付）

**US5: Skill GUI 编辑器**
> 用户在前端可视化编辑 SKILL.md，不手动写 YAML + Markdown。

验收标准：
- 新增 Skill 管理面板（网页内，非独立窗口）
- 展示已注册 Skill 列表（名称、描述、阶段、状态）
- 可新建/编辑/删除 Skill（写回 SKILL.md 文件）
- YAML frontmatter 用表单字段编辑，body 用 Markdown 编辑器
- 保存后即时生效（配合热更新）

**US6: Skill 版本管理 + 热更新**
> Skill 修改后热加载，不改代码就能生效。历史版本可追溯可回滚。

验收标准：
- 文件系统 watcher 检测 SKILL.md 变化 → `SkillRegistry.reload()` 自动重载
- Skill 版本号语义化（`version: 1.2.0`），Git-based 历史追溯
- 前端展示当前版本和历史变更
- 支持回滚到上一版本

### P2（远期）

**US7: 用户自定义 Skill**
> 高级用户在项目级目录定义自己的 Skill，系统自动发现并注册。

**US8: Skill A/B 测试**
> 同一 Skill 多版本并行，用户可选版本，收集效果数据。

---

## 3. 验收标准（完整清单）

| # | 标准 | 优先级 | 对应 US |
|---|------|--------|---------|
| AC1 | Manual 模式每次工具调用弹确认 | P0 | US1 |
| AC2 | Edit Automatically 模式读放行、写首次确认+会话记住 | P0 | US1 |
| AC3 | Plan 模式只读分析+输出方案，不执行写入 | P0 | US1 |
| AC4 | Auto Mode 全自动无确认 | P0 | US1 |
| AC5 | 模式切换有视觉反馈 | P0 | US1 |
| AC6 | `/` 触发动态 Skill 列表（从后端 API 获取） | P0 | US2 |
| AC7 | 新增 SKILL.md 无需改路由代码 | P0 | US2 |
| AC8 | 自然语言匹配 Skill（三档阈值） | P0 | US3 |
| AC9 | Skill 匹配失败走现有逻辑 | P0 | US3 |
| AC10 | 多步需求自动调 ComposeOrchestrator | P0 | US4 |
| AC11 | 编排进度流式输出到聊天框 | P0 | US4 |
| AC12 | 模式状态通过 WebSocket 传给后端 | P0 | US1 |
| AC13 | Skill 管理面板可 CRUD Skill | P1 | US5 |
| AC14 | Skill 文件变更热加载 | P1 | US6 |
| AC15 | Skill 版本可追溯可回滚 | P1 | US6 |

---

## 4. Non-Goals（本次不做）

- 不改 AG-UI 协议本身（只在已有消息类型上加字段）
- 不做 Skill 的 A/B 测试框架
- 不做 Skill 市场/社区分享
- 不做跨项目 Skill 同步

---

## 5. 边缘情况

| 场景 | 预期行为 |
|------|---------|
| WebSocket 断连时切换模式 | 本地 UI 立即响应，重连后同步当前模式给后端 |
| Skill registry 为空 | 斜杠补全不弹出，自然语言跳过匹配 |
| 用户输入既是 `/` 又是自然语言匹配 | 斜杠优先（显式 > 隐式） |
| 同 prompt 匹配多个 Skill（置信度接近） | 弹出歧义消除列表让用户选（最多 3 个） |
| Manual 模式下弹确认太频繁 | 同一工具+同一参数类型 5 秒内不重复弹 |
| Plan 模式下用户说"帮我写文件" | 生成文件内容+方案，但不写入。提示"Plan 模式——以上为方案，切换到其他模式后可执行" |
| 多 Skill 链中某个失败 | ComposeOrchestrator 暂停，聊天框展示失败节点和选项（重试/跳过/终止） |
| 热更新时 Skill 文件有语法错误 | 保留旧版本，日志报错，UI 提示"热更新失败——Skill 文件格式错误" |
| 回滚 Skill 到已删除版本 | 从 Git 历史恢复，提示"该版本将覆盖当前版本" |

---

## 6. 成功指标

- 用户从输入到触发目标 Skill 的操作步骤减少 50%（自然语言 vs 手动打斜杠）
- Skill 自动匹配准确率 ≥ 85%
- 热更新生效时间 < 2 秒（文件保存到 registry 更新）
- 模式切换后第一次工具调用即体现权限变化

---

## 7. 现有代码基准

| 组件 | 文件 | 现状 |
|------|------|------|
| 模式按钮 | [InputBox.vue:7-9](frontend/src/components/chat/InputBox.vue#L7-L9) | `currentMode` 本地 ref，不 emit |
| 斜杠补全 | [InputBox.vue:20-28](frontend/src/components/chat/InputBox.vue#L20-L28) | 6 个硬编码 fallback |
| 消息发送 | [TerminalChat.vue:45-51](frontend/src/components/chat/TerminalChat.vue#L45-L51) | 不传 mode |
| 意图路由 | [chat.py:389-427](src/orbit/api/routes/chat.py#L389-L427) | chat vs programming 二分 |
| 命令路由 | [chat.py:333-351](src/orbit/api/routes/chat.py#L333-L351) | if-else 硬编码 |
| Skill 定义 | [compose/skills/](src/orbit/compose/skills/) | 7 个 SKILL.md |
| Skill 加载 | [parser.py:57](src/orbit/compose/parser.py#L57) | `discover_skills()` |
| 编排器 | [orchestrator.py:57](src/orbit/compose/orchestrator.py#L57) | `run_spec()` 仅接受 YAML text |
| Mode 配置 | [modes/](src/orbit/modes/) | YAML 配置，Loader + Tuner |
| ReActAgent | [agent.py:168](src/orbit/agents/react_agent/agent.py#L168) | 工具调用循环，无 mode 门禁 |
| ToolRegistry | [core.py:305](src/orbit/tools/registry/core.py#L305) | `dispatch()` 有 PermissionEngine 但无 mode |
