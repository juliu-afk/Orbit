# 阶段 1 PRD：Orbit IDE 功能追赶

> **基线文档**: `docs/PRD+ADR_IDE功能追赶.md` §9.0-9.3
> **开发计划**: `docs/开发计划/06-IDE功能追赶计划.md`
> **日期**: 2026-06-29 | **状态**: 已确认，进入阶段 2

## 1. 背景

Orbit v0.17.0 后端能力完整——Agent 编排、8 层防幻觉、三图谱、合规验证。但专业程序员审查 Agent 产出时，只能用 Git 命令行或切到 VS Code。Orbit 驾驶舱只有监控面板，缺少代码级审查界面。

本阶段补齐 🔴 阻塞级 18 项功能，让程序员能够在 Orbit 内完成：看 diff → 审代码 → 导航 → 看诊断 → 批准/打回 → GPG 签名提交。

## 2. 用户故事

| 优先级 | 用户故事 |
|--------|---------|
| P0 | 作为程序员，我想在 Orbit 看到 Agent 改了什么代码（语法高亮 diff），逐段批准或打回，不要切到命令行 `git diff` |
| P0 | 作为程序员，我想看到代码文件的全貌，不是只有 diff snippet，还能在行上添加审查注释 |
| P0 | 作为程序员，我想看到 mypy 类型错误在哪一行（红色波浪线），不要手动跑 mypy |
| P0 | 作为程序员，我想在审查时跳转到函数定义，评估 Agent 的改动对调用者的影响 |
| P0 | 作为程序员，我想确认后亲自 commit——Agent 绝不能自动 commit |
| P0 | 作为程序员，我想用 GPG 签名提交，让 GitHub 显示 Verified 标记 |
| P0 | 作为程序员，我想看测试结果面板——哪些测试通过了、哪些失败了、失败详情 |
| P0 | 作为程序员，点击失败测试能看到对应的 Agent 改动，一键回退或重分派 |
| P1 | 作为程序员，我想看到代码覆盖率——哪些文件被测试覆盖了、哪些行没覆盖 |
| P1 | 作为程序员，多个 Agent 并发修改同一文件时，我想用可视化合并工具解决冲突 |

## 3. 功能范围（18 项）

### Diff 审查系统
1. **Diff 查看器**（并排+行内）：Monaco DiffEditor 封装
2. **语法高亮**：Python/TypeScript/JavaScript/SQL/YAML/TOML/JSON/Markdown
3. **Hunk 级批准/拒绝**：自定义 gutter 按钮
4. **文件树**：项目结构 + 审查状态图标（待审/已批/打回/无变更）
5. **只读编辑器 + 行级审查注释**：Monaco readOnly + glyph margin

### 诊断
6. **问题面板**：mypy 错误/警告列表，点击跳转

### Git + GPG
7. **Git 提交面板**：选文件 + message
8. **GPG 签名提交**：读取系统 GPG keyring + `git commit -S<keyid>` + GitHub Verified
9. **Git 差异对比**：vs HEAD / vs 分支 / per-task before-after
10. **合并冲突可视化解决**：三路合并

### 导航
11. **Go to Definition**（F12）：复用 CodeGraph
12. **Find All References**（Shift+F12）：复用 CodeGraph
13. **悬停类型信息**：L4 mypy 输出
14. **大纲视图**：函数/类列表
15. **全局搜索**：文件名（Ctrl+P）+ 内容（Ctrl+Shift+F）

### 测试可见性
16. **测试结果面板**：pytest 输出结构化渲染
17. **覆盖率着色**：文件树 + 行级装饰
18. **失败测试→Diff 关联**：点击失败用例→定位到 Agent 改动→一键回退或重分派 Agent

## 4. Non-Goals（本期不做）

- 不做完整 IDE 编辑器（多光标/分屏/Zen/调试器）
- 不做轻量编辑器（Phase 2）
- 不做集成终端（Phase 2）
- 不做实时诊断（Phase 2）
- 不做 Git Blame、审查历史（Phase 2）
- 不做智能审查（Phase 3）
- 不做协作审查（Phase 3）

## 5. 验收标准

| # | 标准 | 验证方式 |
|---|------|---------|
| SC1 | 审查 5 文件 PR 闭环在 Orbit 内完成（含 GPG 签名提交），零切出 | E2E 测试 |
| SC2 | 1000 行 diff 加载+渲染 <2s | 性能基准 |
| SC3 | 18 项功能每项可独立验收 | 单元+集成测试 |
| SC4 | GPG 签名提交在 GitHub 显示 Verified | 集成测试 |

## 6. 待确认问题——已决议

| # | 问题 | 决议 |
|---|------|------|
| Q1 | Monaco Editor 集成方式 | `pnpm add monaco-editor` + `vite-plugin-monaco-editor`，npm 打包（不用 CDN——桌面需离线） |
| Q2 | 审查路由 | **独立路由** `/review/:taskId` + `/review/:taskId/:file`，与 Dashboard 分离 |
| Q3 | GPG 签名 | **做**——Phase 1.2。读取系统 GPG keyring，`git commit -S` |
| Q4 | 审查注释存储 | **SQLAlchemy 2.0 ORM**——dev SQLite，生产 PostgreSQL（`DATABASE_URL` 环境变量切换） |

---

> ✅ 已确认。进入阶段 2（技术方案）。
