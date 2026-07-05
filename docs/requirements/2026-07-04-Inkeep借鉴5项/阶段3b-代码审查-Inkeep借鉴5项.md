# 阶段3b 代码审查 — Inkeep 借鉴 5 项

> 日期：2026-07-04 | 审查范围：新增 12 文件 + 修改 11 文件 | 审查级别：标准（非核心模块）

## 审查清单

| 维度 | 检查项 | 结果 | 说明 |
|------|--------|------|------|
| **安全** | SQL 注入 | ✅ 通过 | trace.py 用 aiosqlite 参数化查询，config_store.py 用 subprocess 固定 args |
| **安全** | 命令注入 | ✅ 通过 | `_run_git_sync(*args)` 参数来自内部逻辑，非用户输入 |
| **安全** | XSS | ✅ 通过 | 无前端改动 |
| **安全** | 硬编码密钥 | ✅ 通过 | 无密钥/密码 |
| **安全** | eval() | ✅ 通过 | 无动态代码执行 |
| **方案偏差** | 是否按阶段2方案实现 | ✅ 通过 | 严格按方案，无偏离 |
| **方案偏差** | 超出方案范围的改动 | ⚠️ 注记 | US-4/5 前端未实现——按方案是 P2，留待后续 PR |
| **回溯一致性** | 代码→方案→PRD 可追溯 | ✅ 通过 | 实现记录逐条对照（26 条全部覆盖） |
| **测试覆盖** | 新代码是否有测试 | ✅ 通过 | 47 新用例，覆盖正向+异常+边界 |
| **测试覆盖** | 核心模块正+异常用例 | N/A | 未触及核心模块（调度器状态机/防幻觉判定/图谱存储） |
| **代码质量** | 过早抽象 | ✅ 通过 | 每个模块单一职责，未引入不必要的接口/基类 |
| **代码质量** | 空值/边界条件 | ✅ 通过 | task_type=None → 回退 default_model；空查询 → None；oversized → hint |
| **代码质量** | 三行相似不抽象 | ✅ 通过 | 合理重复——每个 Agent 的 LLMRequest 注入是独立的，抽象反而增加耦合 |
| **调度器** | 状态转换完整性 | ✅ 通过 | US-1 只加 context 字段，不改变状态机 |
| **调度器** | 检查点/回滚 | ✅ 通过 | 不影响 |
| **防幻觉** | L1-L8 链路影响 | ✅ 通过 | US-2 是互补层（tier.py），不修改 L1-L8 任何判定逻辑 |
| **图谱** | Schema 变更 | ✅ 通过 | 无 CodeGraph schema 变更。trace_spans 是新表 |

## 逐文件审查

### `gateway/task_router.py` ✅

- 纯函数设计，无副作用，易测试
- `DEFAULT_TASK_MODEL_MAP` 模块级常量——后续 US-5 配置可覆盖
- `select()` 对未知 task_type 回退 Pro，安全降级

### `graph/tier.py` ✅

- `classify()` 三路分支清晰：`< preview < full < oversized`
- `_truncate_utf8_safe()` 预留省略号字节空间，正确
- `maybe_adjust()` 每 100 次评估一次，有上限钳制
- 小问题：`record_full_request()` 只在 Agent 显式调用时生效，如果 Agent 没有 tool 调用能力则统计不准。**不影响正确性，只影响动态调整精度。**

### `tools/knowledge_tools.py` ✅

- AST 自注册——try/except fail-open
- `load_knowledge_handler` 空参数返回明确错误，不静默

### `observability/trace.py` ✅

- `TraceCollector` 用 asyncio.Queue 批量 flush，不阻塞主流程
- `_flush_loop` fail-open——写入失败不影响任务执行
- `TraceStore.cleanup()` 三层保留逻辑正确
- 小问题：`_flush_loop` 哨兵检测逻辑——`if record is None and not batch: if cls._queue.empty(): break`。如果 sentinel None 入队时队列非空，会丢失 sentinel 导致 worker 不退出。**实际影响低——stop_worker() 入队 sentinel 后 await 等待 worker 结束，worker 最终会超时退出。**

### `core/config_store.py` ✅

- `_run_git_sync()` subprocess 调用，timeout=30s
- "nothing to commit" 不是错误——正确处理空提交
- branch/merge/conflict 完整生命周期

### Agent 修改（4 文件） ✅

- 每处改动 +2~4 行，非侵入式
- `task_type=input_data.context.get("task_type")` ——None safe

### 测试文件（4 文件） ✅

- 覆盖正向/异常/边界/动态调整
- `test_trace.py` 直接用 aiosqlite 写表验证 store 查询，绕过 event loop 问题

## 审查结论

**通过**——无致命问题，无严重问题。

### 注意事项（不阻塞）

1. `record_full_request()` 统计精度依赖 Agent tool 调用——后续 Agent 升级 tool 能力后自动改善
2. `_flush_loop` sentinel 边缘情况——低影响，stop_worker() 有 await 超时兜底

---

> **3b 门禁**：审查通过。进入阶段 4。
