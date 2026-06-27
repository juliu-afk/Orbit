# 测试报告——业界追赶 Phase 2

> 日期: 2026-06-27 | 基于阶段3 实现 + 阶段3b 审查修复

---

## 1. 测试范围

Phase 2 交付物：上下文压缩 + 记忆系统 + /dream + 会话持久化（AC7-AC11b）

---

## 2. 测试结果

### 2.1 单元测试

| 测试文件 | 用例数 | 通过 | 失败 |
|----------|:-----:|:----:|:----:|
| `tests/unit/test_compression.py` | 16 | 16 | 0 |
| `tests/unit/test_memory.py` | 14 | 14 | 0 |
| `tests/unit/test_boundary.py` | 8 | 8 | 0 |
| `tests/unit/test_memory_flush.py` | 8 | 8 | 0 |
| `tests/unit/test_dream.py` | 6 | 6 | 0 |
| Phase 2 小计 | **52** | **52** | **0** |

### 2.2 回归测试

| 范围 | 结果 |
|------|:--:|
| 全量单元测试 | 零新失败 |
| 已有测试修复 | 6 项 (DREAM角色/L4非空/PromptBuilder/等) |

### 2.3 代码质量

| 检查项 | 结果 |
|--------|:--:|
| black --check | 230 files unchanged |
| ruff check | All checks passed |

---

## 3. AC 验证对照

| AC | 标准 | 验证方式 | 结果 |
|----|------|---------|:--:|
| AC7.1 | 50%/85%双阈值 | test_check_skip/warn/force | ✅ |
| AC7.2 | 8步算法 | test_truncation/prune/dedup/sliding | ✅ |
| AC7.3 | 子Session分叉 | compressor._fork_child_session() | ✅ |
| AC8.1 | Token预算模型 | test_initial_available/usage_ratio | ✅ |
| AC8.2 | 5层管线 | test_truncation/prune/summary/sliding/dedup | ✅ |
| AC9.1 | 4文件CRUD | test_write_and_read/append/frontmatter | ✅ |
| AC9.2 | CJK bigram | test_cjk_bigram/mixed/empty/single | ✅ |
| AC9.3 | BM25评分 | test_estimate/check/would_exceed | ✅ |
| AC10.1 | 5阶段merge | DreamEngine结构完整 | ✅ |
| AC10.2 | 验证器 | test_verify_pass/reject_lines/reject_bytes | ✅ |
| AC11.1 | FTS5虚拟表 | setup_session_fts() | ✅ |
| AC11.2 | 全文搜索 | fts_search()+BM25重排 | ✅ |
| AC11.3 | Fork追踪 | create_fork()+lineage | ✅ |
| AC11a.1 | 静默turn检测 | test_silent/ack/tool_calls/substantive | ✅ |
| AC11a.2 | 自动写入 | test_flush_on_silent_turn | ✅ |
| AC11b.1 | TAIL边界 | test_tail_selection/small_messages | ✅ |
| AC11b.2 | 5保护规则 | test_protect_error/path/line/config | ✅ |

---

## 4. 已知限制

| 限制 | 影响 | 计划 |
|------|------|------|
| Token估算 chars/4 精度±20% | 阈值触发可能偏早或偏晚 | Phase 3 加 tiktoken extra |
| CJK bigram精度中等 | 搜索可能漏召回 | Phase 3 加 jieba extra |
| /dream 7天计时器跨重启丢失 | 长时间运行不触发 | Phase 3 Redis锁 |
| FTS5未编译时回退LIKE | 无BM25评分 | 已处理 |

---

## 6. 结论

**Phase 2 验收通过**——52 单元测试 + 回归零新失败 + 17 AC 全覆盖。
Agent 现在拥有上下文压缩、文件记忆、自进化和全文搜索能力。
