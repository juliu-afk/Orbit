# Orbit IDE 功能追赶计划 — V15

> **发布日期**: 2026-06-29 | **状态**: 阶段 1-2 规划中
> 
> 目标：让专业程序员能够在 Orbit 内完成"审查 AI Agent 产出→打回/批准→合并"闭环。
> Orbit 不替代 IDE，而是补齐 AI 产出物的**审查、验证、干预界面**。

## 前置分析

经典 IDE 有而 Orbit 无的功能共 140+ 项。排除"完整 IDE 编辑器/调试器/插件市场/Live Share/Notebook/远程开发"等违背 Agent-First 范式的功能后，**53 项需要实现**。

分级逻辑：
- 🔴 **阻塞级 (P0)**：没这个→专业程序员用不了 Orbit
- 🟡 **重要级 (P1)**：没这个→能用但体验重残
- 🟢 **加分级 (P2)**：没这个→能用但缺少差异化竞争力

## 10 周迭代计划（V15.0 — V15.2）

| 周 | 版本 | 阶段 | 交付物 | 功能数 |
|---|---|---|---|---|
| W1-W3 | v0.18.0 | 审查基础 (P0) | Diff 查看器 + 语法高亮 + 文件树 + 问题面板 + Git 面板+GPG + 导航 | 18 |
| W4-W6 | v0.19.0 | 审查增强 (P1) | Blame + 审查注释 + 终端 + 诊断 + 快速修复 + Agent 推理可视化 | 11 |
| W7-W8 | v0.20.0 | 编辑干预 (P1) | 轻量编辑器 + 补全 + 重命名 + 格式化 + 构建面板 | 8 |
| W9-W10 | v1.0.0 | 智能审查 (P2) | 风险评分 + 影响分析 + 合规标注 + 协作审查 + 模块仪表盘 | 18 |

---

## Phase 1: 审查基础（W1-W3，v0.18.0）🔴 阻塞级

### 1.1 Diff 审查系统（核心）

| # | 功能 | 优先级 | 依赖 |
|---|------|--------|------|
| 1 | Diff 查看器（并排+行内，Monaco DiffEditor） | P0 | Monaco Editor 集成 |
| 2 | Diff 中语法高亮（Python/TS/JS/SQL/YAML/TOML） | P0 | Monaco 语言支持 |
| 3 | 按 Hunk/行 批准或拒绝 | P0 | Diff Editor + 后端 API |
| 4 | 文件树/项目资源管理器（vue3-file-tree 或自研） | P0 | 项目 API |
| 5 | 只读编辑器（Monaco readOnly）+ 行级审查注释 | P0 | Monaco + 注释 API |
| 6 | 问题面板（Error/Warning——mypy/ESLint 输出渲染） | P0 | L4 防幻觉输出管道 |

### 1.2 版本控制 UI

| # | 功能 | 优先级 | 依赖 |
|---|------|--------|------|
| 7 | Git 提交面板（选文件+写 message） | P0 | Git 后端 API |
| 8 | GPG 签名提交（读取系统 GPG keyring + `git commit -S`） | P0 | GnuPG / Git |
| 9 | Git 差异对比（与 HEAD / 与分支 / per-task before-after） | P0 | Diff Editor + Git API |
| 10 | 合并冲突可视化解决（三路合并编辑器） | P0 | Monaco 三路合并模式 |

### 1.3 代码导航

| # | 功能 | 优先级 | 依赖 |
|---|------|--------|------|
| 11 | Go to Definition（F12）——复用 CodeGraph 索引 | P0 | CodeGraph + Monaco |
| 12 | Find All References——复用 CodeGraph 索引 | P0 | CodeGraph + Monaco |
| 13 | 悬停类型/Hover Info——复用 mypy/L4 输出 | P0 | L4 mypy + Monaco HoverProvider |
| 14 | 大纲/Outline 视图（函数/类列表） | P0 | CodeGraph AST |
| 15 | 全局搜索（文件名 Ctrl+P + 内容 Ctrl+Shift+F） | P0 | 全文索引 |

### 1.4 测试可见性

| # | 功能 | 优先级 | 依赖 |
|---|------|--------|------|
| 16 | 测试结果面板（pytest 输出结构化渲染） | P0 | pytest --json 输出 |
| 17 | 覆盖率着色（文件树/行级绿-红-灰） | P0 | coverage.json → 编辑器装饰 |
| 18 | 失败测试→Diff 关联（点击失败用例→对应 Agent 改动→一键回退/重分派） | P0 | 测试面板 + Diff API + 检查点 |

---

## Phase 2: 审查增强 + 编辑干预（W4-W8，v0.19.0—v0.20.0）🟡 重要级

### 2.1 审查增强

| # | 功能 | 优先级 | 依赖 |
|---|------|--------|------|
| 17 | Git Blame 内联（Agent vs Human，每行标注作者） | P1 | Git blame + Monaco |
| 18 | 审查注释系统（行级评论→标记→Agent 认领→修复→关闭） | P1 | 注释 API + Agent 通信 |
| 19 | 审查历史/时间线（同段代码的修改+审查链） | P1 | 检查点 + 审计日志 |
| 20 | 代码快照对比（per-task before/after 完整文件） | P1 | 检查点管理器 |
| 21 | Agent 意图注释（每个 diff hunk 附带 Agent thinking 摘要） | P1 | Agent 上下文持久化 |

### 2.2 Agent 行为可视化

| # | 功能 | 优先级 | 依赖 |
|---|------|--------|------|
| 22 | DAG 节点可交互（点击→该步骤输入/输出/diff/日志） | P1 | vis-network + 已有 EventBus |
| 23 | Token 消耗 per-file 明细 | P1 | TokenBudgetTracker 扩展 |
| 24 | Agent 推理链展示（审查时可读 reasoning trace） | P1 | AgentContext 持久化 |
| 25 | 多 Agent 同段代码观点对比（Reviewer vs Developer 分歧） | P1 | AgentMessageBus 记录 |

### 2.3 诊断 & 快速修复

| # | 功能 | 优先级 | 依赖 |
|---|------|--------|------|
| 26 | 实时诊断（红色波浪线推送）——L4 mypy 结果→Monaco markers | P1 | L4 + Monaco |
| 27 | 快速修复（Lightbulb/Code Actions）——"Add import"/"Fix type" | P1 | L4 + Monaco CodeActionProvider |
| 28 | 一键格式化触发 | P1 | ruff/black 后端 |

### 2.4 编辑与干预

| # | 功能 | 优先级 | 依赖 |
|---|------|--------|------|
| 29 | 轻量编辑器（Monaco 可写模式——人工改 3 行场景） | P1 | Monaco |
| 30 | 基础代码补全（人工编辑时） | P1 | Monaco + CodeGraph |
| 31 | 安全重命名（F2——预览+确认+撤销） | P1 | CodeGraph + Monaco RenameProvider |
| 32 | 常用代码片段 | P1 | Monaco Snippets |

### 2.5 构建 & 运行

| # | 功能 | 优先级 | 依赖 |
|---|------|--------|------|
| 33 | 集成终端（xterm.js） | P1 | xterm.js + 后端 PTY |
| 34 | 构建输出面板（CI 输出+错误解析+点击跳转） | P1 | 终端 + 问题匹配器 |
| 35 | 右键 Run/Debug 单测 | P1 | pytest API + 终端 |

---

## Phase 3: 智能审查（W9-W10，v1.0.0）🟢 加分级

### 3.1 智能审查引擎

| # | 功能 | 优先级 | 依赖 |
|---|------|--------|------|
| 36 | 风险评分 per file per diff（L1-L8 映射→文件级风险%） | P2 | 8 层防幻觉 + 前端渲染 |
| 37 | 自动审查摘要（PR 打开→5 文件改动，1 高风险改核心逻辑） | P2 | 风险评分 + 自然语言生成 |
| 38 | 影响分析可视化（CodeGraph 依赖图→高亮受影响模块） | P2 | CodeGraph + vis-network |
| 39 | 测试缺口自动标记（函数 A 改了但测试未更新→标红） | P2 | CodeGraph + coverage 数据 |

### 3.2 合规 & 规则

| # | 功能 | 优先级 | 依赖 |
|---|------|--------|------|
| 40 | 合规规则违反标注（float 非 Decimal、缺权限装饰器→diff 标红） | P2 | ComplianceRule 引擎 |
| 41 | 审查清单自动生成（改核心模块→"必须检查借贷平衡"） | P2 | 合规引擎 + 知识图谱 |

### 3.3 协作审查

| # | 功能 | 优先级 | 依赖 |
|---|------|--------|------|
| 42 | 多人工审查者协作（看彼此注释+决定） | P2 | WebSocket + 注释系统 |
| 43 | 审查状态流转（Pending→In Review→Changes Requested→Approved→Merged） | P2 | 审查 API |

### 3.4 项目级洞察

| # | 功能 | 优先级 | 依赖 |
|---|------|--------|------|
| 44 | Agent 贡献统计（Agent vs Human 行数/打回率/一次通过率） | P2 | 审计日志聚合 |
| 45 | 技术债务热力图（高频改动+低覆盖→高风险模块） | P2 | CodeGraph + coverage |
| 46 | 模块健康仪表盘（改动频次+测试通过率+幻觉率+审查通过率） | P2 | AgentOps 聚合 |
| 47 | 知识图谱可交互可视化（三图点击→跳转代码） | P2 | vis-network + 三图 API |

### 3.5 设置 & 数据库

| # | 功能 | 优先级 | 依赖 |
|---|------|--------|------|
| 48 | 色彩主题（暗/亮） | P2 | CSS 变量 + Element Plus 主题 |
| 49 | 审查策略配置（哪些文件需多少层幻觉检测、哪些模块强制人工） | P2 | 配置引擎 |
| 50 | 快捷键自定义 | P2 | Monaco KeybindingService |
| 51 | 数据库 Schema 可视化（DBGraph→表关系图） | P2 | DBGraph + vis-network |
| 52 | 迁移脚本审查（before/after schema 对比） | P2 | DBGraph + Diff Editor |

### 3.6 故障恢复增强

| # | 功能 | 优先级 | 依赖 |
|---|------|--------|------|
| 53 | 任务级回滚可视化（检查点→可视化选择回滚点→预览→确认） | P2 | Checkpoint + 前端 |

---

## 架构约束

### 前端技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| 代码编辑器 | Monaco Editor (VS Code 同款) | 支持 DiffEditor/语法高亮/HoverProvider/CodeAction/markers——一次性覆盖 20+ 功能 |
| 终端 | xterm.js | 事实标准，GitHub Codespaces/VS Code 同款 |
| 文件树 | 自研（Vue 3 递归组件） | 需深度集成审查状态图标+覆盖率着色，第三方库可能不够灵活 |
| 图可视化 | vis-network（已有）+ 增强 | 已集成，只需扩展交互 |

### 后端新增模块

| 模块 | 路径 | 功能 |
|------|------|------|
| 文件服务 | `src/orbit/files/` | 文件 CRUD、内容读取、diff 生成 |
| 审查引擎 | `src/orbit/review/` | 注释 CRUD、审查状态机、批准/拒绝 |
| LSP 代理 | `src/orbit/lsp/` | L4 mypy 输出→标准化诊断格式、格式化触发 |
| 终端代理 | `src/orbit/terminal/` | PTY 管理、xterm.js 通信 |

### 禁止新增依赖（先问再装）

Monaco Editor、xterm.js 需通过 pnpm add 安装——先确认用户。

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| V15.0 | 2026-06-29 | 初始规划：53 项功能，3 Phase，10 周 |

---

> 详细 PRD+ADR 见 `docs/PRD+ADR_IDE功能追赶.md`
> 阶段 1-2 需求文档见 `docs/requirements/2026-06-29-IDE功能追赶/`
