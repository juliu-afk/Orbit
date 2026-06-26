# 附录 A：Hermes Agent 源码全量研究

> 来源: `github.com/NousResearch/hermes-agent` MIT · v0.14.0 · 66K+ stars · Python 93.6%

---

## 1. Agent Loop（`agent/conversation_loop.py` 2683行）

### 核心函数：`run_conversation()` (行496)

```python
while (api_call_count < agent.max_iterations and agent.iteration_budget.remaining > 0):
    # 1. 检查中断
    if agent._interrupt_event.is_set(): break
    # 2. 构建请求 (system prompt + memory + context)
    messages = agent._build_messages()
    # 3. 注入 Anthropic cache control
    if provider == "anthropic": _inject_cache_markers(messages)
    # 4. 净化消息
    messages = _sanitize(messages)
    # 5. 可中断 API 调用 (后台线程 HTTP)
    response = await _interruptible_api_call(messages, tools)
    # 6. 解析 tool_calls → 分发工具
    if response.tool_calls: await _execute_tool_calls(response.tool_calls)
    # 7. 检查压缩触发
    if self.should_compress(): await self.compress()
```

### 10 种退出原因

| # | 退出原因 | 含义 |
|---|---------|------|
| 1 | `text_response(finish_reason=...)` | 正常完成 |
| 2 | `interrupted_by_user` | 用户中断（API调用前） |
| 3 | `interrupted_during_api_call` | 流式传输中中断 |
| 4 | `budget_exhausted` | 迭代预算耗尽 |
| 5 | `max_iterations_reached(N/M)` | 循环计数器上限 |
| 6 | `all_retries_exhausted_no_response` | API 从未返回 |
| 7 | `fallback_prior_turn_content` | 空 follow-up |
| 8 | `empty_response_exhausted` | 模型返回空 |
| 9 | `error_near_max_iterations(...)` | 接近上限时异常 |
| 10 | `unknown` | 兜底 |

### 迭代预算（`agent/iteration_budget.py` 62行）

| 参数 | 值 | 说明 |
|------|-----|------|
| `max_iterations` | 90 | 主 Agent 上限 |
| `delegation.max_iterations` | 50 | 子 Agent 上限 |
| `execute_code` 退还 | yes | 代码执行不消耗预算 |
| 线程安全 | `threading.Lock` | `consume()`/`refund()` |

---

## 2. Tool Calling 架构（三层分离·589行 registry）

### Layer 1: ToolRegistry (`tools/registry.py`)

```python
class ToolRegistry:
    _tools: Dict[str, ToolEntry] = {}   # name → entry
    _toolset_checks: Dict[str, Callable] = {}
    _lock = threading.RLock()

    def register(self, name, toolset, schema, handler, check_fn=None):
        """模块导入时调用——每个工具文件底部 self-register。"""
```

**ToolEntry 字段**: name, toolset, schema, handler, check_fn, requires_env, is_async, description, emoji, max_result_size_chars, dynamic_schema_overrides

### Layer 2: 工具集组合 (`toolsets.py` 939行)

```python
_HERMES_CORE_TOOLS = ["web_search","terminal","read_file","delegate_task",...]  # ~40 核心工具

TOOLSETS = {
    "hermes-cli":     {"tools": _HERMES_CORE_TOOLS},
    "hermes-telegram": {"tools": _HERMES_CORE_TOOLS},
    "hermes-acp":     {"tools": [...], "includes": ["web","vision"]},
    "safe":           {"tools": [], "includes": ["web","vision"]},  # 无 terminal
}
```

### Layer 3: AST 自发现 (`discover_builtin_tools`)

```python
def discover_builtin_tools():
    for py_file in Path("tools/").glob("*.py"):
        tree = ast.parse(py_file.read_text())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and
                isinstance(node.func, ast.Attribute) and
                node.func.attr == "register"):
                importlib.import_module(f"tools.{py_file.stem}")
                break  # 导入即触发注册
```

### 工具文件（96 个 `.py` 文件）

每个工具文件底部：
```python
from tools.registry import registry
registry.register(
    name="web_search",
    toolset="web",
    schema={...},                    # LLM 看到的 OpenAI function schema
    handler=handle_web_search,       # 实际执行函数
    check_fn=lambda: bool(os.environ.get("HERMES_WEB_SEARCH_API_KEY")),
)
```

### 并行调度（`agent/tool_dispatch_helpers.py` 448行）

三类工具：
- `_NEVER_PARALLEL_TOOLS = {"clarify"}` — 交互式，必须串行
- `_PARALLEL_SAFE_TOOLS = {"web_search","read_file","session_search",...}` — 只读，总是安全
- `_PATH_SCOPED_TOOLS = {"read_file","write_file","patch"}` — 路径不重叠时可并行

### 并发执行（`agent/tool_executor.py` 1538行）

```python
with ThreadPoolExecutor(max_workers=min(len(calls), 8)) as executor:
    futures = [executor.submit(_run_tool, i, tc, name, args) for ...]
    concurrent.futures.wait(futures, timeout=5.0)  # 5s heartbeat 检查中断
```

---

## 3. Context Compression（`agent/context_compressor.py` 2683行）

### 核心类：`ContextCompressor(ContextEngine)` (行612)

| 参数 | 默认值 | 位置 |
|------|--------|------|
| `threshold_percent` | 0.50 | `__init__` 行783 |
| `protect_first_n` | 3 | 行783 |
| `protect_last_n` | 20 | 行783 |
| `summary_target_ratio` | 0.20 | 行783 |
| `abort_on_summary_failure` | False | 行783 |

### 常量

| 常量 | 值 |
|------|-----|
| `_MIN_CTX_TRIGGER_RATIO` | 0.85 |
| `MINIMUM_CONTEXT_LENGTH` | 64000 |
| `_MIN_SUMMARY_TOKENS` | 2000 |
| `_SUMMARY_TOKENS_CEILING` | 12000 |

### 压缩 8 步骤（`compress()` 行2372）

1. `_prune_old_tool_results()` (行990) — 去重+摘要替换
2. 找 head 边界 — 保护前3条消息
3. `_find_tail_cut_by_tokens()` (行2094) — token 预算向后遍历
4. `_generate_summary()` (行1453) — LLM 摘要
5. 组装 head + summary + tail
6. `_align_boundary_forward/backward` — 不拆 tool_call/result 对
7. `_ensure_last_user_message_in_tail` — 防活跃任务丢失
8. 会话分叉 — 子会话 + parent-child lineage

### 防抖动

- `_ineffective_compression_count >= 2` → 退避
- 摘要前缀: `[CONTEXT COMPACTION — REFERENCE ONLY] ... latest message WINS`

---

## 4. Session Management（`hermes_state.py` 5351行）

### SessionDB 类 (行747)

**Schema version**: 16
**54 列** session 表：id, source, user_id, model, model_config, system_prompt, parent_session_id, started_at, ended_at, end_reason, message_count, tool_call_count, input_tokens, output_tokens, cwd, git_branch, git_repo_root, title, api_call_count, handoff_state, handoff_platform, handoff_error, rewind_count, archived, etc.

### 双 FTS5 索引（行692-745）

```sql
-- 标准分词（英文+数字）
CREATE VIRTUAL TABLE messages_fts USING fts5(content);
-- trigram 分词（CJK/Thai 子串查询）
CREATE VIRTUAL TABLE messages_fts_trigram USING fts5(content, tokenize='trigram');
-- INSERT/UPDATE/DELETE triggers 自动保持索引同步
```

### WAL + NFS 回退（`apply_wal_with_fallback` 行244）

- WAL 模式 → 并发读
- NFS/SMB/FUSE 检测 → 降级 DELETE 模式
- 损坏修复 (`repair_state_db_schema` 行457): 原地重建 FTS → 失败则 drop+rebuild

### FTS 搜索（`search_messages` 行3691）

- BM25 排序 + 片段生成
- source/role 过滤
- 支持 FTS5 查询语法（短语、布尔、前缀）

---

## 5. 可直接复制 vs 需适配

### 可直接复制（MIT 许可·零依赖）

| 组件 | 文件 | 行数 | 理由 |
|------|------|:--:|------|
| `ToolRegistry` 类 | `tools/registry.py` | 589 | 自包含，无外部依赖 |
| `IterationBudget` 类 | `agent/iteration_budget.py` | 62 | 零依赖，线程安全 |
| `ToolEntry` dataclass | `tools/registry.py` | — | 元数据 schema |
| `_should_parallelize_tool_batch()` | `agent/tool_dispatch_helpers.py` | 448 | 无状态规则引擎 |
| `tool_error()`/`tool_result()` 序列化器 | `tools/registry.py` | 15行 | 纯工具函数 |
| AST 自发现 | `discover_builtin_tools()` | — | 自包含文件扫描 |
| FTS5 schema + triggers | `hermes_state.py:692-745` | — | 纯 SQL |
| WAL + NFS 回退 | `apply_wal_with_fallback()` | — | 隔离工具函数 |
| 摘要前缀 guardrail | `SUMMARY_PREFIX` | — | 纯 prompt 文本 |
| tail 保护预算遍历 | `_find_tail_cut_by_tokens()` | — | 独立算法 |
| 工具修剪逻辑 | `_prune_old_tool_results()` | — | 无外部依赖 |

### 需适配

| 组件 | 理由 |
|------|------|
| `run_conversation()` 主循环 | 紧耦合 AIAgent 类属性/provider/session/memory |
| Provider transport 层 | Hermes 15+ providers，Orbit 用 LiteLLM |
| `ContextCompressor` 类 | 继承 ContextEngine，依赖 auxiliary_client |
| `SessionDB` 类 | 5351行紧耦合 Hermes config/CLI/gateway |
| `execute_tool_calls_concurrent()` | 依赖 AIAgent guardrails/checkpointing/middleware |
| Memory manager | Hermes 特有 MEMORY.md/USER.md 注入 |
| Skill 系统 | 自动创建+自改进，Hermes 特有 |
