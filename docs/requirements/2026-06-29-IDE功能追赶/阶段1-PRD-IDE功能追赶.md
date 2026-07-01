# 阶段 1 PRD：Orbit IDE 功能追赶

> 基线: docs/PRD+ADR_IDE功能追赶.md §9.0-9.3 | 日期: 2026-06-29 | 状态: ✅ 18/18 全部完成 (2026-07-01)

## 决议

| Q | 决议 |
|---|------|
| Q1 编辑器 | Monaco Editor + vite-plugin-monaco-editor，npm 打包 |
| Q2 路由 | 独立 /review/:taskId + /review/:taskId/:file |
| Q3 GPG | 做——Phase 1.2。git commit -S |
| Q4 存储 | SQLAlchemy 2.0 ORM，dev SQLite / prod PostgreSQL |

## 功能范围（18 项）

1-5: Diff 查看器/语法高亮/hunk 审批/文件树/只读编辑器+注释
6: 问题面板（L4 mypy 诊断）
7-10: Git 提交+GPG+diff+合并冲突
11-15: Go to Def/References/Hover/Outline/全局搜索
16-18: 测试面板/覆盖率/失败→Diff 关联

## Non-Goals

不做完整 IDE/调试器/插件市场/Live Share/Jupyter/远程开发

## 实施完成记录（2026-07-01）

| # | 功能 | 状态 | PR |
|---|------|:--:|:--:|
| 1 | Diff 查看器 | ✅ | #109 |
| 2 | 语法高亮 | ✅ | Monaco 内置 |
| 3 | Hunk 审批 | ✅ | #136 |
| 4 | 文件树 | ✅ | #109 |
| 5 | 只读编辑器+注释 | ✅ | #136 |
| 6 | 问题面板 | ✅ | #109 |
| 7 | Git 提交 | ✅ | #109 |
| 8 | GPG 签名 | ✅ | #109 |
| 9 | Git Diff | ✅ | #109 |
| 10 | 合并冲突 | ✅ | #142 |
| 11 | Go to Definition | ✅ | #137 |
| 12 | References | ✅ | #137 |
| 13 | Hover | ✅ | #137 |
| 14 | Outline | ✅ | #136 |
| 15 | 全局搜索 | ✅ | #136 |
| 16 | 测试面板 | ✅ | #136 |
| 17 | 覆盖率 | ✅ | #136 |
| 18 | 失败→Diff 关联 | ✅ | #142 |
