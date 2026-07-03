# 阶段1 PRD：MCP 客户端桥——Orbit 消费外部 MCP 工具

> 日期：2026-07-03 | 来源：Serena vs Orbit 对比调研
> 参考：`docs/research/serena-vs-orbit-comparison.md`

## 背景

Orbit 已有 MCP **服务端**（`src/orbit/knowledge/mcp_server.py`），可暴露工具给外部 Agent 调用。但 Orbit 的 Agent（architect/developer/reviewer/qa）无法消费外部 MCP 工具——它们通过进程内 `ToolRegistry` 调用工具，无 MCP 客户端能力。

Serena（[oraios/serena](https://github.com/oraios/serena)）提供 40+ 语言的 LSP 级代码智能，通过 MCP 协议暴露。Orbit 如果接入 Serena，其 Agent 循环中的代码导航/编辑能力将直接升级——从 Python `ast` 模块跳到真正的 LSP 语义理解。

**更广义的目标**：不止 Serena。Orbit 应能连接任意 MCP 服务器，将外部工具以透明方式注入 ToolRegistry，Agent 无感知调用。

## 用户故事

### P0 — 连接 Serena MCP 服务器
> 作为 Orbit 的 Developer Agent，当我在一个 Python/TypeScript 项目中工作时，我能通过 `find_symbol`/`replace_symbol_body` 等语义工具定位和编辑代码，而不是靠 grep 猜行号。

**验收标准**：
- [ ] Orbit 启动时自动连接配置的 MCP 服务器（stdio 子进程）
- [ ] `tools/list` 自动发现远程工具，注册到 ToolRegistry
- [ ] Agent 在 ReAct 循环中可调用远程 MCP 工具，与本地工具无异
- [ ] 远程工具调用失败时返回结构化错误，不阻断循环

### P1 — 泛化 MCP 客户端框架
> 作为 Orbit 运维者，我可以通过 YAML 配置文件添加/移除 MCP 服务器，无需改代码。

**验收标准**：
- [ ] `configs/mcp_clients.yaml` 定义服务器列表（command + args）
- [ ] 支持多服务器同时连接
- [ ] 启动失败时降级——该服务器工具不可用但不影响 Orbit 启动

### P2 — 工具发现与版本管理
> 作为工具管理员，我能看到每个 MCP 服务器暴露了哪些工具，以及调用审计日志。

**验收标准**：
- [ ] Dashboard 或日志中可见远程工具列表及来源
- [ ] 调用审计记录标注工具来源（本地/远程+服务器名）

## Non-Goals
- 不实现 MCP 协议的服务端推送/通知（仅需 request-response）
- 不修改现有 MCP 服务端（`mcp_server.py`）——它是服务端，这是客户端，互不干扰
- 不引入 MCP Python SDK——沿用 MVP 零依赖策略，手写 JSON-RPC 2.0 客户端

## 技术约束
- MCP 传输：stdio（子进程 stdin/stdout），首版不实现 HTTP/SSE
- JSON-RPC 2.0 协议
- 工具 Schema 转换：MCP `inputSchema` → OpenAI function calling 格式（现有 ToolEntry.schema 格式）

## 边界 Case
- MCP 服务器进程启动失败 → 记录 warning，跳过该服务器，Orbit 正常启动
- MCP 服务器中途崩溃 → 下次调用返回错误，不自动重启（V1 简化）
- 远程工具超时 → 30s 超时，返回 timeout 错误
- 工具名冲突（远程 vs 本地同名）→ 本地优先，远程工具加 `serena/` 前缀
- JSON-RPC 响应解析失败 → 返回原始错误给 Agent
- MCP 服务器未安装（如 `uvx serena` 失败）→ 启动时检测，给出人类可读的安装提示
