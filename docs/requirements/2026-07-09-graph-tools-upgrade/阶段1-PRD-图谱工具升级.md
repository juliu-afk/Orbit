# Phase 1 PRD — 图谱工具升级 + Serena 卸载 + OKF 知识导出

> 基线调研：`docs/research/CBM+OKF+Serena+可视化-落地分析.html`（2026-07-09）
> 决策：不接 CBM MCP。OKF 仅知识图谱。卸载 Serena，缺口自研补。可视化已实现不纳入。

## 背景

Orbit 当前 MCP 仅 4 个工具（query_knowledge / find_symbol / find_referencing_symbols / get_symbols_overview），Agent 代码查询能力弱。Serena 外部依赖 22/28 工具与 Orbit 重复。知识图谱无标准交换格式。

## 用户故事

- 作为 Agent，我需要 `trace_path` 追踪多跳调用链，以便理解代码影响面
- 作为 Agent，我需要 `get_architecture` 快速了解项目结构，而非逐文件探索
- 作为 Agent，我需要 `search_code` 在已索引文件中搜索并关联图谱节点
- 作为 Agent，我需要 `dead_code` 检测零调用者函数
- 作为 Agent，我需要语义编辑工具（replace/insert/delete）精确修改代码
- 作为会计人员，我需要用 Obsidian/VS Code 编辑知识图谱内容，而非学 SQL

## 验收标准

| # | 验收标准 | 验证方式 |
|---|---------|---------|
| AC1 | MCP 工具从 4 → 13（新增 9 个） | `/mcp` 列出 13 工具 |
| AC2 | trace_path 支持 depth 1-5，方向 in/out/both，响应 &lt;50ms | 对已知函数测试调用链 |
| AC3 | get_architecture 返回语言/模块/入口点/热点，&lt;2KB | 调用后检查返回结构 |
| AC4 | search_code 返回结果关联 CodeNode | grep + 验证 symbol 字段非空 |
| AC5 | 4 个编辑工具正确更新文件 + 增量索引 | 编辑后查 CodeNode 确认更新 |
| AC6 | Serena 完全卸载——代码中无 serena 引用 | `rg -i serena src/` 零结果 |
| AC7 | OKF bundle 导出到 .orbit/knowledge/，符合 v0.1 spec | okf-mcp validate 通过 |

## 范围

**Do:** 9 个新 MCP 工具 + Serena 清理 + OKF 导出器 PoC。改动限于 `src/orbit/knowledge/mcp_server.py` + Serena 相关文件清理 + 新增 `okf_exporter.py`。

**Don't:** 不改 graph engines。不改前端。不做 Tree-sitter 迁移（Phase 2）。不做 detect_changes（Phase 2）。

## Non-Goals

- 不改变 CodeNode/Edge schema
- 不引入新数据库/新存储
- 不影响现有 4 个工具的行为
- 不修改防幻觉层 L1-L9

## 成功指标

- MCP 工具数：4 → 13
- Serena 引用数：6+ → 0
- 新增代码量：≤500 行
- 新依赖数：0
