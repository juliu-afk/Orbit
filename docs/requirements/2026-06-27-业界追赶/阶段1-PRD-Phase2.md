# PRD：业界追赶 Phase 2——上下文压缩+记忆系统+自进化

> 版本: v1.0 | 日期: 2026-06-27 | 状态: 待确认
> 基于: `阶段1-PRD-业界追赶.md` Phase 2 需求 + 5 框架源码研究

---

## 1. 背景

Phase 1 让 Agent 能读代码→写代码→跑测试闭环。但 Agent 还是"健忘"的：
- 长对话 token 无限增长，超出模型上下文窗口即崩溃
- 每次新任务从零开始，无记忆积累
- 会话历史不可搜索，有价值信息无法回溯
- 无自进化能力——Agent 不随时间变聪明

Phase 2 解决这些问题，参考 Hermes/MiMo Code/OpenClaw 的生产级实现。

---

## 2. 用户故事

### P0

- **作为 ReActAgent**，我希望能检测上下文 token 用量，接近窗口限制时自动压缩，避免 LLM 调用失败。
- **作为用户**，我希望 Agent 记住之前学到的经验（教训、决策、模式），下次任务自动应用。
- **作为运维人员**，我希望能全文搜索历史会话，找到某次对话的关键信息。

### P1

- **作为系统**，我希望在 Agent 静默轮次（无实质性输出）时自动刷新记忆，不丢失上下文。
- **作为系统**，我希望能执行 /dream 自进化命令，定期合并去重记忆文件，保持 <200 行。

---

## 3. 验收标准

### AC7: 上下文压缩

| # | 标准 | 参考 |
|---|------|------|
| AC7.1 | 实现 50%/85% 双阈值触发：<50% 跳过，50-85% 后台摘要，≥85% 强制压缩 | Hermes context_compressor.py |
| AC7.2 | 实现 8 步算法：token估算→阈值检查→截断→修剪→摘要→滑动窗口→去重→后检查 | 同上 |
| AC7.3 | 压缩后仍 ≥85% → 子 Session 分叉（parent-child lineage 记录） | Hermes fork 机制 |
| AC7.4 | 摘要层使用廉价模型（GLM-4.7 Flash），不消耗主力模型 token | 成本优化 |

### AC8: Token 预算 + 5 层管线

| # | 标准 | 参考 |
|---|------|------|
| AC8.1 | Token 预算模型：max_context_window - reserved_output - current_usage = available | Claude Code budget |
| AC8.2 | 5 层管线：truncation → pruning → summary → sliding → dedup | Claude Code 5-layer |
| AC8.3 | 每层独立可测试，可跳过（按阈值判定） | 模块化设计 |
| AC8.4 | 预算耗尽时阻止 LLM 调用，返回明确错误 | 防御性 |

### AC9: 文件记忆系统

| # | 标准 | 参考 |
|---|------|------|
| AC9.1 | 4 文件：MEMORY.md / checkpoint.md / progress.md / notes.md | MiMo Code memory/ |
| AC9.2 | YAML frontmatter + markdown body，checksum 完整性校验 | 结构化 |
| AC9.3 | SQLite FTS5 全文搜索 + BM25 评分 + snippet 高亮 | Hermes 双FTS5 |
| AC9.4 | CJK 中文 bigram 分词支持 | MiMo Code CJK |
| AC9.5 | 双向同步（文件 ↔ 内存 reconcile），冲突检测 | 一致性 |

### AC10: /dream 命令

| # | 标准 | 参考 |
|---|------|------|
| AC10.1 | 5 阶段：gather → merge_1 → merge_2 → dedup → verify | MiMo Code dream.txt |
| AC10.2 | 输出验证：保持 <200 行 + <10KB | 尺寸门禁 |
| AC10.3 | 7 天自动触发（asyncio.create_task 循环） | auto-dream.ts |
| AC10.4 | DreamAgent 继承 ReActAgent，拥有完整工具访问 | Agent 架构 |

### AC11: 会话持久化

| # | 标准 | 参考 |
|---|------|------|
| AC11.1 | FTS5 虚拟表 + insert/delete/update 触发器 | Hermes hermes_state.py |
| AC11.2 | `fts_search()` 支持 session/role 过滤 + BM25 排序 | 全文搜索 |
| AC11.3 | 会话表扩展：parent_session_id + lineage_reason | fork 追踪 |
| AC11.4 | `create_fork()` / `get_child_sessions()` | lineage 查询 |

### AC11a: Pre-compaction Flush

| # | 标准 | 参考 |
|---|------|------|
| AC11a.1 | 静默 turn 检测（无 tool_calls + 无实质性内容） | OpenClaw memory flush |
| AC11a.2 | 自动追加 daily log 到 MEMORY.md |  |
| AC11a.3 | NO_REPLY 事件（驾驶舱不可见） |  |

### AC11b: Checkpoint 边界

| # | 标准 | 参考 |
|---|------|------|
| AC11b.1 | TAIL 10K-20K tokens 检查点边界 | MiMo Code checkpoint.ts |
| AC11b.2 | 5 条文本保护（错误/路径/行号/配置/用户输入）永不被压缩 |  |
| AC11b.3 | 可压缩工具结果擦除（大代码块/分隔线/冗余空格） |  |

---

## 4. 影响范围

| 模块 | 改动 | 类型 |
|------|------|------|
| `src/orbit/compression/` | **新增**——4 文件 | 新模块 |
| `src/orbit/memory/` | **新增**——4 文件 | 新模块 |
| `src/orbit/dream/` | **新增**——3 文件 | 新模块 |
| `src/orbit/sessions/fts.py` | **新增**——FTS5 管理 | 新模块 |
| `src/orbit/checkpoint/boundary.py` | **新增**——边界算法 | 新模块 |
| `src/orbit/scheduler/flush.py` | **新增**——记忆刷新 | 新模块 |
| `src/orbit/agents/react_agent.py` | **修改**——pre-LLM 压缩钩子 | 修改 |
| `src/orbit/scheduler/orchestrator.py` | **修改**——L4/L5 加载 | 修改 |
| `src/orbit/sessions/registry.py` | **修改**——+6 方法 | 修改 |
| `src/orbit/prompt/builder.py` | **修改**——记忆注入 | 修改 |

---

## 5. 边缘情况

| 场景 | 处理 |
|------|------|
| FTS5 未编译进 SQLite | `PRAGMA compile_options` 检测 → 回退 LIKE 搜索 |
| 记忆文件并发写入冲突 | fcntl.flock (Linux) / msvcrt.locking (Windows) |
| Token 估算误差 >20% | 默认 chars/4，可选 tiktoken extra |
| 压缩后仍超 85% | Fork child session + lineage 记录 |
| /dream 触发时 Agent 正忙 | 跳过本轮，下一周期再试 |
| CJK 搜索精度不足 | bigram 基准 + trigram 回退 |
| 7 天计时器跨重启丢失 | 文档化限制，Phase 3 持久化 |

---

## 6. 待确认

1. ✅ 压缩摘要模型用 GLM-4.7 Flash（免费）
2. ✅ MEMORY.md 文件大小上限 50KB
3. ✅ /dream 手动触发命令格式 `/dream`
