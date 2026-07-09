# Phase 2 PRD — 图谱引擎升级（Tree-sitter + detect_changes + 统一查询）

> 基线：Phase 1 完成（PR #253）— MCP 工具 4→12, Serena 卸载, OKF 导出
> 调研：`docs/research/CBM+OKF+Serena+可视化-落地分析.html` §H.3

## 背景

Phase 1 补齐了查询和编辑工具。但底盘仍是 Python `ast`——单语言。前端 TS/Vue、Tauri Rust、Helm YAML 全部不在图谱中。设计文档 Step 3.1 ADR 已写明"若需支持多语言，需切换至 Tree-sitter"。

## 用户故事

- 作为 Agent，我需要理解 frontend/ 的 TypeScript 代码结构，而不只是 backend/ 的 Python
- 作为调度器，我需要知道 git diff 修改了哪些函数，以便智能重调度受影响任务
- 作为开发者，我需要 `query_graph(type="code", symbol="...")` 统一入口，而不是记三个引擎的不同 API
- 作为团队成员，我 clone 项目后不想花几分钟重建完整索引

## 验收标准

| # | 验收标准 | 验证 |
|---|---------|------|
| AC1 | `code_graph.py` 解析 .py + .ts/.tsx + .sql 文件 | 索引含前端 TS + SQL 迁移脚本 |
| AC2 | 现有 CodeNode/Edge schema 不变，所有现有测试通过 | 零回归 |
| AC3 | `detect_changes` 返回 git diff 受影响的符号 + 风险等级 | 改一个文件→返回受影响的函数列表 |
| AC4 | `query_graph(type, **filters)` 统一路由到 code/db/config engine | 三种 type 均返回结构化结果 |
| AC5 | `.orbit/graph/graph.db.zst` 可被解压+增量索引 | 队友 clone 后解压→跳过全量重建 |
| AC6 | `rename_symbol` 工作区级重命名 + 更新 edges 表 | 重命名后 edges 表引用不悬空 |
| AC7 | `type_hierarchy` 返回类的超类型/子类型链 | BFS 上下遍历继承边 |

## ⚠️ 新依赖（需确认）

| 依赖 | 用途 | 包名 |
|------|------|------|
| **tree-sitter** | 多语言 AST 解析（Python/TS/SQL grammar） | `tree-sitter` + language packs |
| **zstandard** | 图谱产物 zstd 压缩/解压 | `zstandard` |

## 范围

**Do:** Tree-sitter 替代 ast（保持 CodeNode/Edge schema 不变）、detect_changes、query_graph() 统一接口、zstd 共享图谱、rename_symbol、type_hierarchy。

**Don't:** DATA_FLOWS 边（Phase 3）、节点层级扩展（Phase 3）、后台 watchdog（Phase 3）、OKF 导入（Phase 3）。不改前端。

## Non-Goals

- 不改变现有 4 个引擎的查询 API（query_graph 是新增入口，不删旧方法）
- 不做 LSP 类型推断（P3）
- 不做代码语义搜索（P3）
