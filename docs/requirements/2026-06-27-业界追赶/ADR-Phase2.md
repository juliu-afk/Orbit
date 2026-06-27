# ADR：业界追赶 Phase 2——架构决策记录

> 日期: 2026-06-27 | 对应 PRD: `阶段1-PRD-Phase2.md`

---

## ADR-01: Token 估算方案选择

**背景**: 需要在每次 LLM 调用前估算上下文 token 数，但不想引入重量级依赖。

**选项**:
| 方案 | 精度 | 依赖 | 延迟 |
|------|:--:|------|:--:|
| A: tiktoken | ±5% | `tiktoken` 包 (~1MB) | ~1ms |
| B: chars/4 | ±20% | 无 | ~0ms |
| C: litellm token_counter | ±10% | 已有 litellm | ~5ms |

**决议**: **B (chars/4) 默认 + A (tiktoken) 可选 extra**。

**理由**:
- chars/4 零依赖零延迟，适合高频调用
- ±20% 误差在 128K 窗口下安全（50% 阈值实际在 40-60%）
- tiktoken 作为 `pip install orbit[accurate]` extra，按需启用
- 不选 C——litellm token_counter 需要额外 API 调用

---

## ADR-02: 记忆存储后端选择

**背景**: 需要持久化 Agent 记忆（经验、决策、教训），支持全文搜索。

**选项**:
| 方案 | 搜索 | 并发 | 复杂度 |
|------|:--:|:--:|:--:|
| A: Markdown 文件 + FTS5 | SQLite FTS5 | 文件锁 | 低 |
| B: SQLite 表 + FTS5 | SQLite FTS5 | WAL 并发 | 中 |
| C: PostgreSQL + pg_trgm | GIN 索引 | ACID | 高 |

**决议**: **A (Markdown 文件 + FTS5 虚拟表)**。

**理由**:
- Markdown 文件人可读，符合 MiMo Code 设计
- FTS5 已在 Python stdlib sqlite3 中编译
- 文件锁处理并发（Phase 2 范围），Phase 3 可升到 SQLite 表
- 不选 B——纯表结构失去人类可读性
- 不选 C——PG 引入运维复杂度，Phase 3+ 才考虑

---

## ADR-03: 压缩摘要模型选择

**背景**: 5 层压缩管线中的 summary 层需要 LLM 摘要。用哪个模型？

**选项**:
| 方案 | 成本 | 延迟 | 质量 |
|------|:--:|:--:|:--:|
| A: GLM-4.7 Flash (免费) | $0 | ~500ms | 中等 |
| B: 主力模型 (DeepSeek V4 Pro) | $0.0004/1K | ~800ms | 高 |
| C: 不用 LLM，纯规则摘要 | $0 | ~50ms | 低 |

**决议**: **A (GLM-4.7 Flash)** 用于力模式，**C (纯规则)** 用于软模式。

**理由**:
- 力模式（≥85% 阈值）：必须压缩才能继续，用免费模型不死循环
- 软模式（50-85% 阈值）：后台异步摘要，主力模型不阻塞
- 不选 B——消耗宝贵的主力模型 token 做压缩是浪费
- 纯规则摘要在 50-85% 时先用，等后台 LLM 摘要完成再替换

---

## ADR-04: CJK 分词策略

**背景**: BM25 搜索需要分词，中文无空格分隔。

**选项**:
| 方案 | 精度 | 依赖 | 复杂度 |
|------|:--:|------|:--:|
| A: Bigram (2-gram) | 中等 | 无 | ~30行 |
| B: jieba 分词 | 高 | `jieba` 包 | ~5行 |
| C: ICU 分词 | 高 | `PyICU` (>10MB) | ~20行 |

**决议**: **A (Bigram) 默认，B (jieba) 可选 extra**。

**理由**:
- Bigram 零依赖，效果对 FTS5 snippet 搜索足够
- 中文技术文档以 2-gram 为主（函数名、变量名、关键词）
- jieba 作为 `pip install orbit[cjk]` extra
- 不选 C——ICU 10MB+ 对桌面应用太重

---

## ADR-05: /dream 触发机制

**背景**: /dream 需要自动定期执行，也需要手动触发。

**选项**:
| 方案 | 持久化 | 精度 | 复杂度 |
|------|:--:|:--:|:--:|
| A: asyncio.create_task + sleep 循环 | 否（重启丢失） | 秒级 | 低 |
| B: APScheduler + Redis 锁 | 是 | 秒级 | 中 |
| C: 外部 cron + CLI 命令 | 是 | 分钟级 | 中 |

**决议**: **A (asyncio 循环) + C (CLI 手动) 互补**。

**理由**:
- asyncio 循环零配置，进程内运行
- 7 天周期长，重启丢失不是严重问题（用户下次启动会重新计时）
- CLI 命令 `/dream` 供手动触发
- 不选 B——APScheduler 引入新依赖
- Phase 3 考虑 Redis 锁保证多进程安全

---

## ADR-06: 子 Session 分叉策略

**背景**: 当压缩后仍超过 85% 上下文窗口，需创建子 Session 继续。

**选项**:
| 方案 | 状态传递 | 回滚 | 复杂度 |
|------|:--:|:--:|:--:|
| A: 摘要 + 引用（原消息序列化） | 摘要 | 冷存储恢复 | 低 |
| B: 完整消息复制到子 Session | 完整 | 自然回滚 | 中 |
| C: 不分叉，拒绝继续 | 无 | 无 | 最低 |

**决议**: **A (摘要传递 + cold storage)**。

**理由**:
- 子 Session 以摘要开始，包含已完成工作的关键信息
- 原消息序列化到 checkpoint 供审计/回溯
- `sessions.parent_session_id` 记录 lineage
- 不选 B——复制完整消息解决不了窗口问题
- 不选 C——拒绝继续是糟糕的用户体验

---

## 依赖决策总表

| 决策 | 选择 | 新依赖 |
|------|------|:--:|
| Token 估算 | chars/4 + tiktoken extra | 否 |
| 记忆存储 | Markdown 文件 + FTS5 | 否 |
| 压缩摘要模型 | GLM-4.7 Flash | 否（已有） |
| CJK 分词 | Bigram + jieba extra | 否 |
| /dream 触发 | asyncio 循环 + CLI | 否 |
| 子 Session 分叉 | 摘要传递 + cold storage | 否 |

**Phase 2 零新依赖。**
