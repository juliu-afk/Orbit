# Context Engineering——追上业界方案

> 参考源: MiMo Code, Hermes, Claude Code, OpenClaw

---

## 一、业界最佳实践

### MiMo Code：5 层记忆系统（最强）

```
MEMORY.md          ← 项目级知识/规则/架构决策（长期）
checkpoint.md      ← 会话检查点（自动维护，checkpoint-writer 子Agent）
tasks/*/progress.md ← 任务进度跟踪
notes.md           ← Agent 临时笔记区
SQLite FTS5        ← 全文搜索兜底
```

**/dream 命令**——记忆自进化（每 7 天自动触发）：
1. 独立 Agent 读取历史会话 + 现有记忆文件
2. 执行合并、去重、验证路径有效性、压缩
3. 将分散记忆收敛为紧凑的当前状态
4. 更新全局 MEMORY.md

**上下文重建**——窗口接近上限时不从零拼接：
```
checkpoint.md + MEMORY.md 摘要 + 近期消息 → 结构化重建 → "干净简报"
```
主 Agent 基于"干净简报"继续工作，不读全量历史。

### Claude Code：5 层压缩管线

```
Layer 1: Tool Output Truncation — 大输出取头尾 + 摘要
Layer 2: Message Pruning      — 保留最近 N 条，旧的摘要
Layer 3: Conversation Summary  — 定期摘要替换原始历史
Layer 4: Context Window Sliding — 近窗口上限时滑动
Layer 5: Semantic Dedup        — 去重工具调用结果
```

~200K token 预算分配：
- System prompt: ~2K
- Conversation history: ~150K
- Tool results: ~30K
- Response buffer: ~18K

### Hermes：子会话压缩（独特设计）

```
触发: >50% 上下文窗口 (preflight) 或 >85% (gateway 自动)
方法: 辅助 LLM 摘要中间轮次
保护: 最后 20 条消息保留；tool call/result 配对不拆分
预算: 摘要预算 = 被压缩内容的 ~20% (最小 2K, 最大 12K)
Lineage: 压缩创建子会话 (parent-child link)，不重写原文
```

### OpenClaw：极简双文件

```
memory/YYYY-MM-DD.md  ← 追加式每日上下文（log layer）
MEMORY.md             ← 持久事实/偏好/决策（long-term layer）
检索: 向量嵌入语义搜索 + BM25 关键词匹配 + 时间衰减 + MMR 重排序
存储: SQLite
```

> "Persistent memory is Markdown files on disk. Not every agent system needs a complex memory strategy." — Peter Steinberger

---

## 二、Orbit 当前状态

```
TaskContext L1-L5 (每会话重建，无持久化):
  L1: 协作宪法——硬编码字符串 "遵循小企业会计准则..."
  L2: 图谱查询结果——dict 占位
  L3: 任务状态——state + prd
  L4: 私有记忆——dict 占位
  L5: 长期记忆——空 list
```

**问题**：
- 会话之间零记忆——每次都是全新开始
- 无上下文压缩——LLM 调用全量传 TaskContext
- 无 token 预算——可能撑爆窗口
- L1-L5 大部分是占位符，实际未填充

---

## 三、实施方案

### Phase 1：MiMo 式文件记忆（对标 MiMo·3天）

```python
# src/orbit/memory/store.py
class MemoryStore:
    MEMORY_PATH = "MEMORY.md"           # 项目级持久记忆
    CHECKPOINT_PATH = ".orbit/checkpoint.md"  # 会话检查点
    NOTES_PATH = ".orbit/notes.md"      # Agent 临时笔记
    TASKS_DIR = ".orbit/tasks/"         # 任务进度跟踪

    async def save_checkpoint(self, task_id: str, summary: str):
        """checkpoint-writer 子Agent 维护"""
        ...

    async def load_context(self, task_id: str) -> str:
        """结构化重建——不读全量历史"""
        checkpoint = await self._read_checkpoint(task_id)
        memory_summary = await self._summarize_memory()
        recent = await self._recent_messages(task_id, limit=10)
        return f"{memory_summary}\n\n{checkpoint}\n\n{recent}"
```

### Phase 2：上下文压缩（对标 Hermes·2天）

```python
# src/orbit/memory/compressor.py
class ContextCompressor:
    COMPRESSION_THRESHOLD = 0.5   # 50% 窗口触发
    TAIL_KEEP = 20                 # 保留最后 20 条
    SUMMARY_BUDGET_RATIO = 0.2    # 摘要预算 20%

    async def compress(self, messages: list, max_tokens: int) -> list:
        if self._usage_ratio(messages, max_tokens) < self.COMPRESSION_THRESHOLD:
            return messages  # 不需要

        tail = messages[-self.TAIL_KEEP:]
        to_summarize = messages[:-self.TAIL_KEEP]
        budget = int(len(str(to_summarize)) * self.SUMMARY_BUDGET_RATIO)

        summary = await self._summarize(to_summarize, budget)
        return [{"role": "system", "content": f"历史摘要: {summary}"}] + tail
```

### Phase 3：/dream 自进化（对标 MiMo·3天）

```python
# src/orbit/memory/dream.py
class DreamAgent:
    """每周自动触发，独立 Agent 扫描历史，合并记忆。"""

    async def dream(self) -> str:
        sessions = await self._scan_recent_sessions(days=7)
        existing_memory = await self._read_memory()

        # 调 LLM 做合并/去重/压缩
        prompt = self._build_dream_prompt(sessions, existing_memory)
        new_memory = await self.llm.generate(prompt)

        await self._write_memory(new_memory)
        return new_memory
```

---

## 四、参考源码位置

| 项目 | 关键文件 | 行数 |
|------|---------|------|
| MiMo Code | `packages/opencode/src/memory/service.ts` (FTS5 search+BM25) | ~115 |
| MiMo Code | `packages/opencode/src/memory/reconcile.ts` (双向同步) | ~120 |
| MiMo Code | `packages/opencode/src/memory/fts.sql.ts` (FTS schema) | ~25 |
| MiMo Code | `packages/opencode/src/memory/fts-query.ts` (CJK token builder) | ~45 |
| MiMo Code | `session/compaction.ts` (token-budgeted tail selection) | ~300 |
| MiMo Code | `session/checkpoint.ts` (checkpoint boundary algorithm) | ~500 |
| Hermes | `session/compressor.py` (lineage-based compression) | ~300 |
| Claude Code | `context/compression.ts` (leaked, 5-layer pipeline) | ~600 |
| OpenClaw | `memory/` dir (dual MD files + vector + BM25) | ~200 |

---

## 五、MiMo Code 源码补充：FTS5 记忆引擎 + 检查点边界算法

### FTS5 Schema（可直接复用）

```sql
-- MiMo Code memory_fts 表结构
CREATE TABLE memory_fts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,       -- 文件路径
    scope TEXT NOT NULL,             -- global | projects | sessions
    scope_id TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL,              -- memory | checkpoint | progress | notes
    body TEXT NOT NULL,              -- 全文内容
    fingerprint TEXT NOT NULL,       -- stat.size + "-" + stat.mtimeMs
    last_indexed_at INTEGER NOT NULL
);
CREATE INDEX idx_memory_scope ON memory_fts(scope, scope_id);
CREATE INDEX idx_memory_type ON memory_fts(type);
```

### 双向同步（reconcile.ts）

```python
# Orbit 适配版
class MemoryReconciler:
    async def reconcile(self, root: Path) -> None:
        # Direction A: 新文件/变更文件 → 索引
        for md_file in root.rglob("*.md"):
            fingerprint = f"{md_file.stat().st_size}-{md_file.stat().st_mtime_ns}"
            existing = await self.db.get_fingerprint(md_file)
            if existing != fingerprint:
                body = md_file.read_text()
                await self.db.upsert(md_file, body, fingerprint)

        # Direction B: 已删除文件 → 清理索引
        for row in await self.db.all_rows():
            if not Path(row.path).exists():
                await self.db.delete(row.path)
```

### CJK 分词查询（fts-query.ts）

MiMo 的 FTS 查询构建器处理中英文混合：
```python
# 正则: [\p{L}\p{N}_]+ 匹配 Unicode 字母/数字/下划线（含中文）
tokens = re.findall(r'[\w]+', query, re.UNICODE)
# 每个 token 用双引号包裹 + OR 连接
fts_query = " OR ".join(f'"{t}"' for t in tokens)
```

### 检查点边界算法（checkpoint.ts）

MiMo 的 checkpoint 算法保留 `[10K, 20K]` token 的尾部上下文：
- TAIL_MIN_TOKENS = 10K
- TAIL_MAX_TOKENS = 20K
- TAIL_MIN_TEXT_BLOCK_MESSAGES = 5
- 压缩可压缩工具（read, bash, grep 等）的结果
- checkpoint-writer 子Agent 写入 `checkpoint.md`

---

## 附录 A：Hermes 上下文压缩原始研究

> 来源：`NousResearch/hermes-agent` `agent/context_compressor.py` (2683行) + `hermes_state.py` (5351行)

### 压缩触发阈值（精确到行号）

| 参数 | 值 | 位置 |
|------|-----|------|
| `threshold_percent` | **0.50** (50%) | `__init__` 行783 |
| `_MIN_CTX_TRIGGER_RATIO` | **0.85** (85%) | 退化阈值 |
| `MINIMUM_CONTEXT_LENGTH` | **64000** tokens | 最小上下文 |
| `protect_first_n` | **3** | 保护前N条消息 |
| `protect_last_n` | **20** | 保护最后N条消息 |
| `summary_target_ratio` | **0.20** (20%) | 摘要预算占比 |
| `_MIN_SUMMARY_TOKENS` | **2000** | 摘要下限 |
| `_SUMMARY_TOKENS_CEILING` | **12000** | 摘要上限 |

### 压缩 8 步骤（`compress()` 行号 2372）

1. **工具输出修剪** (`_prune_old_tool_results`, 行990) — 去重+摘要替换旧结果
2. **找 head 边界** — 保护前3条消息（system prompt + 初始交换）
3. **token 预算向后遍历找 tail** (`_find_tail_cut_by_tokens`, 行2094) — 20%预算
4. **LLM 摘要** (`_generate_summary`, 行1453) — 辅助模型，结构化模板
5. **组装 head + summary + tail**
6. **边界对齐** — `_align_boundary_forward()` / `_align_boundary_backward()` 确保不拆 tool_call/result 对
7. **用户消息锚定** — `_ensure_last_user_message_in_tail()` 防止活跃任务丢失
8. **会话分叉** — 创建子会话，记录 parent-child lineage

### 防抖动机制

- `_ineffective_compression_count >= 2` → 退避，不再压缩
- 摘要前缀：`[CONTEXT COMPACTION — REFERENCE ONLY] ... latest message WINS`

### 会话管理 (`hermes_state.py`)

- **双 FTS5 索引**：
  ```sql
  CREATE VIRTUAL TABLE messages_fts USING fts5(content);
  CREATE VIRTUAL TABLE messages_fts_trigram USING fts5(content, tokenize='trigram');
  ```
- **WAL 模式 + NFS 回退** (`apply_wal_with_fallback`, 行244)
- **损坏 DB 修复** (`repair_state_db_schema`, 行457) — FTS 索引原地重建，失败则 drop+rebuild
- **Schema version 16**，54 个 session 列
- **FTS 搜索** (`search_messages`, 行3691) — BM25 排序 + 片段生成 + source/role 过滤

---

## 附录 B：MiMo Code 记忆系统原始研究

> 来源：`XiaomiMiMo/MiMo-Code` `packages/opencode/src/memory/` (6文件)

### 文件与行数

| 文件 | 行数 | 职责 |
|------|:--:|------|
| `memory/service.ts` | 115 | FTS5 search + BM25 ranking + score floor filtering |
| `memory/reconcile.ts` | 120 | 双向同步（disk→FTS 索引 + prune 已删除） |
| `memory/fts.sql.ts` | 25 | FTS5 DDL schema |
| `memory/fts-query.ts` | 45 | CJK token builder（Unicode `\p{L}\p{N}_` 正则） |
| `memory/paths.ts` | 110 | 路径解析器 + scope/type 提取 + CC frontmatter 类型 |
| `memory/index.ts` | — | 模块导出 |

### 记忆文件布局（6 种类型）

```
memory/global/MEMORY.md              ← 跨项目用户偏好
memory/projects/<pid>/MEMORY.md      ← 每项目持久知识
memory/sessions/<sid>/checkpoint.md  ← 会话检查点
memory/sessions/<sid>/notes.md       ← 自由格式笔记
memory/sessions/<sid>/tasks/<TID>/progress.md ← 每任务进度
~/.claude/projects/<slug>/memory/**/*.md ← CC 互操作
```

### 双向同步算法 (`reconcile.ts`)

```
Direction A: 遍历磁盘 *.md → 读 body → 算 fingerprint(size+mtime) → FTS upsert
Direction B: 遍历 FTS rows → 检查磁盘 path 是否存在 → 不存在则 DELETE
```

### BM25 搜索 (`service.ts`)

- **Token 级 FTS5 查询**：标点剥离 → 每 token 双引号包裹 → OR 连接
- **Score floor**: 相对比例（top hit 的 0.15），过滤常见词噪声
- **Over-fetch**: 3x 请求量（上限 50），供 score floor 削峰

### CJK 分词 (`fts-query.ts`)

```python
# 正则: [\p{L}\p{N}_]+ 匹配 Unicode 字母/数字/下划线（含中文）
tokens = re.findall(r'[\w]+', query, re.UNICODE)
fts_query = " OR ".join(f'"{t}"' for t in tokens)
```

### 检查点边界算法 (`session/checkpoint.ts` ~500行)

| 参数 | 值 |
|------|-----|
| TAIL_MIN_TOKENS | 10000 |
| TAIL_MAX_TOKENS | 20000 |
| TAIL_MIN_TEXT_BLOCK_MESSAGES | 5 |
| 压缩目标 | 可压缩工具结果（read, bash, grep 等） |
| 输出 | checkpoint.md（checkpoint-writer 子Agent 维护） |

### 上下文压缩 (`session/compaction.ts` ~300行)

- `select()` — token 预算尾部选择
- `prune()` — 旧工具输出擦除
- `process()` — LLM 摘要（模板：Goal + Instructions + Discoveries + Accomplished + Relevant files）

### /dream 命令——记忆自进化

5 阶段 LLM 驱动的合并流程：
1. Phase 0 - Locate Data: 搜索记忆文件，定位 SQLite DB
2. Phase 1 - Orient: 读 MEMORY.md + notes.md + checkpoints
3. Phase 2 - Gather: 从检查点/进度/笔记提取候选事实
4. Phase 3 - Verify: 只读 SQLite 查询交叉验证
5. Phase 4 - Consolidate: 编辑 MEMORY.md（预定义章节）
6. Phase 5 - Prune: 保持 <200 行/10KB，验证路径/命名

**自动触发**: 每 7 天（dream）/ 30 天（distill），`session/auto-dream.ts` ~120行
