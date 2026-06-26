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
| MiMo Code | `memory/` dir (MEMORY.md + checkpoint + tasks + SQLite) | ~800 |
| Hermes | `session/compressor.py` (lineage-based compression) | ~300 |
| Claude Code | `context/compression.ts` (leaked, 5-layer pipeline) | ~600 |
| OpenClaw | `memory/` dir (dual MD files + vector + BM25) | ~200 |
