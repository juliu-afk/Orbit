# Serena vs Orbit — 对比分析

> 调研日期：2026-07-03 | PR #188 + #191 | 状态：✅ 已集成

## Serena

开源（MIT），GitHub [oraios/serena](https://github.com/oraios/serena)。定位：给 AI Agent 的 IDE 后端——通过 MCP 暴露 LSP 语义工具。

**核心工具**：`find_symbol` / `find_referencing_symbols` / `get_symbols_overview` / `replace_symbol_body` / `rename_symbol` / `safe_delete_symbol` / `insert_after_symbol` / `insert_before_symbol`

**Token 效率**：overview ~300 tokens vs 整文件 ~15K（96% 减少）

## Orbit 集成

| 里程碑 | PR | 内容 |
|--------|----|------|
| 基础设施 | [#188](https://github.com/juliu-afk/Orbit/pull/188) | MCPClientConnection + ToolRegistry MCP 桥 |
| 闭环 | [#191](https://github.com/juliu-afk/Orbit/pull/191) | ROLE_TOOLS + Prompt + 启动检测 |

**安装**：`pip install serena-agent` → `configs/mcp_clients.yaml` 启用 → Orbit 启动自动连接。

**已知限制**：首次启动需下载 LSP 后端（>90s），后续秒级。仅 Python 项目有完整 LSP 支持。
