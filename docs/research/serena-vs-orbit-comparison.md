# Serena vs Orbit — 对比分析与偷师清单

> 调研日期：2026-07-03 | 来源：Web 搜索 + Orbit 代码库探索

## 1. Serena 是什么

**开源**：✅ 是。GitHub [oraios/serena](https://github.com/oraios/serena)，免费 MIT 协议。
PyPI: `serena-agent` v1.5.1，`uv tool install -p 3.13 serena-agent` 一行安装。

**定位**：给 AI Coding Agent 用的"IDE 后端"——通过 MCP 协议暴露 IDE 级语义工具。不是 Agent 本身，是 Agent 的工具箱升级。

**核心架构**：

```
LLM (Claude Code / Codex / Cursor)
  ↕ MCP 协议 (stdio/HTTP)
Serena MCP Server (FastMCP)
  ↕
┌─────────────────┬─────────────────┐
│ SolidLSP (免费)  │ JetBrains 插件   │
│ 40+ 语言 LSP    │ (付费，更强重构)  │
└─────────────────┴─────────────────┘
```

**关键工具清单**：

| 类别 | 工具 | 作用 |
|------|------|------|
| 符号读取 | `get_symbols_overview` | 文件大纲 ~300 tokens |
| | `find_symbol` | 按语义名路径定位符号 |
| | `find_referencing_symbols` | 查所有调用点 |
| 符号编辑 | `replace_symbol_body` | 手术级替换函数体 |
| | `insert_after/before_symbol` | 在符号前后插入代码 |
| | `rename_symbol` | LSP 驱动的跨文件重命名 |
| | `safe_delete_symbol` | 安全删除符号 |
| 重构 | `move_symbol` | 移动符号/文件/目录 (JB) |
| | `inline_symbol` | 内联函数/变量 (JB) |
| 记忆 | `write_memory` / `read_memory` | 跨会话持久化记忆 |

**Token 效率数据**（社区实测）：
- `get_symbols_overview` 替代全文件读取：**96% token 减少**
- `find_symbol` 替代 grep 搜索：**~90% token 减少**
- `rename_symbol` 替代手工跨文件替换：**~95% 步骤减少**
- 整体任务 token 成本：**50-70% 降低**

---

## 2. Orbit 现状

Orbit 是多 Agent 编排系统（调度器 + 7 角色 Agent + ReAct 循环 + Docker 沙箱），代码导航只是其 IDE 功能追赶中的附属模块。

**代码导航现状**：

| 能力 | 实现方式 | 局限 |
|------|---------|------|
| Go to Definition | `ast` 解析 → CodeNode 表名匹配 | **仅 Python**，返回文件名不返行号 |
| Find References | Edge 表 `calls` 边反向查 | 仅返回调用者函数名，无文件位置 |
| Outline | `ast` 现场解析 | **仅 Python** |
| Hover | `get_symbol_meta()` | **bug——方法不存在，500 错误** |
| 搜索 | 纯 Python grep + ripgrep API | 文本级，无语义 |
| LSP | mypy 子进程包装 | 非 LSP 协议，仅诊断 |
| 重命名 | ❌ 不存在 | `edit_file` 是盲字符串替换 |
| 移动/内联 | ❌ 不存在 | — |

**MCP 服务**：有，但仅暴露一个 `query_knowledge` 工具（查会计/金融领域知识），不暴露任何代码分析能力。

---

## 3. 关键差距对比

| 维度 | Serena | Orbit | 差距 |
|------|--------|-------|------|
| 代码解析 | 40+ 语言 LSP | Python `ast` 模块 | **Orbit 仅 Python** |
| 符号定位 | `find_symbol(name_path)` 语义路径 | CodeNode 表名匹配 | **Orbit 无精确行号/列号** |
| 查找引用 | LSP `references` 全量精确 | Edge 表 caller 名列表 | **Orbit 无文件位置** |
| 重命名 | LSP `rename` 跨文件原子操作 | ❌ 无 | **零到一差距** |
| 符号级编辑 | `replace_symbol_body` 等 4 个工具 | `edit_file` 盲替换 | **手术刀 vs 锤子** |
| MCP 暴露 | 完整代码工具链通过 MCP | 仅知识查询 | **Orbit MCP 不暴露代码能力** |
| 多语言 | 40+ | 仅 Python（分析）/ 多语言（显示） | **分析层单语言** |
| 重构 | rename/move/inline (JB 插件) | ❌ 无 | **零到一差距** |
| 编辑器集成 | VS Code / JetBrains / 所有 MCP 客户端 | 独立 Tauri 桌面应用 | **Orbit 封闭，Serena 开放** |

---

## 4. 偷师清单——Orbit 可直接借鉴的

### 4.1 高价值、低成本（立即可做）

**A. 修复 hover 端点 bug**
- 文件：`src/orbit/api/routes/codegraph_routes.py:110`
- `get_symbol_meta` 方法不存在 → `AttributeError`
- 修复：在 `CodeGraphEngine` 加 `get_symbol_meta`，从 `CodeNode.meta` JSON 字段读取

**B. 将 CodeGraph 能力暴露为 MCP 工具**
- 文件：`src/orbit/knowledge/mcp_server.py`
- 已有 MCP 框架（JSON-RPC 2.0 over stdio），只需注册新工具：
  - `find_symbol` → 调 `CodeGraphEngine.find_definitions_cross_file`
  - `find_referencing_symbols` → 调 `CodeGraphEngine.get_callers`
  - `get_symbols_overview` → 调 codegraph API 的 outline
- 工作量：~50 行代码

**C. 增强 Go to Definition 返回行号**
- `CodeNode` 已有 `start_line`/`end_line` 字段
- `/codegraph/definition` 当前只返回 `file_path`
- 改为返回 `{file_path, start_line, end_line}` ——向前兼容

### 4.2 中价值、中成本（下一迭代）

**D. 引入 tree-sitter 替代 `ast` 模块**
- 当前 `ast` 仅支持 Python；tree-sitter 支持 Python/TS/JS/Go/Rust 等
- Serena 走 LSP 路线（SolidLSP），Orbit 可选更轻量的 tree-sitter
- 更换 `CodeGraphEngine` 的解析后端，保持查询接口不变
- 风险：tree-sitter 的调用图精度不如 LSP（无类型推断）

**E. 实现 `replace_symbol_body`**
- 核心逻辑：`CodeNode.start_line`/`end_line` → 定位函数体范围 → 精确替换
- 比 `edit_file(old_string, new_string)` 可靠得多——不靠字符串匹配
- 需要 tree-sitter 提供精确的 body 起止位置（`ast` 也能做）

**F. 符号级重命名**
- 依赖 LSP 或 tree-sitter 的引用解析
- Serena 的 `rename_symbol` 调用 LSP `textDocument/rename`
- Orbit 方案：用 tree-sitter 找到所有引用 → 批量 `edit_file`
- 或者：对接 pyright LSP（只 Python 也够用）

### 4.3 高价值、高成本（战略方向）

**G. 真正的 LSP 客户端**
- Serena 的 SolidLSP 层是对 `multilspy` 的封装
- Orbit 可复用类似方案：`pip install multilspy` 或直接对接 pyright
- 解锁：精确跳转、引用、重命名、诊断、hover——跨 40+ 语言
- 这是 Serena 最核心的竞争力

**H. Orbit MCP 服务器——暴露完整代码智能**
- 当前 Orbit 的 MCP 是"领域知识查询"，不是"代码助手"
- 如果能像 Serena 一样，把 CodeGraph + LSP 能力包装成 MCP 工具
- 外部 Agent（Claude Code、Codex）就能用 Orbit 做代码导航
- 这会让 Orbit 从"独立桌面应用"变成"可被任何 Agent 调用的代码智能后端"

---

## 5. 建议优先级

| 优先级 | 事项 | 工作量 | 理由 |
|--------|------|--------|------|
| P0 | 修复 hover bug（4.1-A） | 30min | 线上 500，用户可见 |
| P1 | Go to Def 返回行号（4.1-C） | 1h | 数据已有，只是不返回 |
| P1 | CodeGraph → MCP 工具（4.1-B） | 2h | 已有 MCP 框架，纯注册 |
| P2 | tree-sitter 替代 ast（4.2-D） | 1-2天 | 解锁多语言，是重构/重命名的基础 |
| P2 | `replace_symbol_body`（4.2-E） | 1天 | 依赖 tree-sitter，显著提升编辑可靠性 |
| P3 | 符号重命名（4.2-F） | 2-3天 | 依赖 LSP 或 tree-sitter 引用图 |
| P4 | 完整 LSP 客户端（4.3-G） | 1-2周 | 战略级，但工作量大 |
| P4 | Orbit MCP 代码智能（4.3-H） | 1周 | 依赖 LSP 客户端 |

---

## 6. 结论

**Serena 是开源的**，核心价值在"把 IDE 的语义理解能力通过 MCP 喂给 AI Agent"。

**Orbit 和 Serena 不是竞品**——Orbit 是 Agent 编排系统，Serena 是 Agent 工具增强。两者互补：Orbit 如果集成 Serena 级别的代码智能，其 Agent 循环中的 architect/developer/reviewer 角色效率会大幅提升。

**最值得偷师的三个点**：
1. **符号级编辑**（`replace_symbol_body`）——手术刀替代锤子
2. **LSP 驱动**——从 Python `ast` 升级到真正的语言服务器
3. **MCP 作为开放接口**——让 Orbit 的代码智能可被外部 Agent 调用
