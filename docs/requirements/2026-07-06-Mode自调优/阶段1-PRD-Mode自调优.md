# 阶段1-PRD-Mode自调优.md

> 基于 `docs/requirements/2026-07-06-Grill交互协议层/阶段1-PRD-Grill交互协议层.md` G6 需求。
> 前提：PR #214 Mode File 系统已落地，mode.yaml 可加载可注入可生效。

## 一、问题陈述

### 当前状态

PR #214 完成后，Agent 行为通过 `src/orbit/modes/*/mode.yaml` 可配置。
但存在三个问题：

1. **mode 参数调优靠猜**。用户不知道 `max_questions_per_branch: 20` 对当前任务是太多还是太少
2. **没有反馈回路**。任务做完了，不知道是 mode 配置好还是需求本身简单
3. **用户不会改 YAML**。大多数用户不知道 `question_strategy` 是什么、文件在哪

### 用户问题

- "能不能根据我的反馈自动调？"
- "我怎么知道当前的 mode 配置好不好？"
- "能不能我在聊天里说句话，Orbit 就自动帮我调？"

## 二、目标

### 本次迭代（1 个 PR）

1. **三维度任务质量评分** — 每次任务完成时自动评分，写入 `task_audit_trail`
2. **对话驱动 mode 调优** — 用户在聊天中说"/mode fast"或自然语言表达，Orbit 自动修改 mode.yaml

### 下次迭代

- G6 自扩展模式生成器（从高分任务轨迹自动生成新 mode）

## 三、用户角色

| 角色 | 场景 |
|------|------|
| Orbit 用户 | 正常使用，任务完成后想看评分；偶尔想调 mode |
| Orbit 管理员 | 看团队整体的 mode 效果统计 |

## 四、用户故事

### P0（本次实现）

**US1: 任务完成自动评分**
> 作为 Orbit 用户，我希望每次任务完成后系统自动评估质量，
> 以便我知道这次交互效果好不好，以及当前的 mode 配置是否合适。

验收标准：
- 任务 state=DONE 时，自动计算三维度评分（用户反馈/会话质量/交付结果）
- 评分存入 `task_audit_trail`（复用现有表结构）
- 用户反馈从 chat history 中自动提取（正面/负面关键词）
- 会话质量复用 V1-V3 `validate_prd()` 结果
- 交付结果读 `task_runner` 终态

**US2: 对话驱动 mode 调优**
> 作为 Orbit 用户，我希望在聊天中自然地说"问快点"或"/mode fast"，
> 就能自动调整 mode 参数，不需要手动编辑 YAML 文件。

验收标准：
- 用户在 chat 中说话 → Orbit 检测到 mode 调整意图 → 自动修改 mode.yaml → 回复确认
- 支持三种预设：`/mode fast`（加速）、`/mode deep`（深入）、`/mode reset`（默认）
- 支持自然语言：检测"快点"/"别问那么多"/"问细点"/"太慢了"等
- mode 写入后立即生效（下次 Agent 调度时读取）

### P1（下次迭代）

**US3: 评分驱动的策略推荐** — 对比不同 mode 配置的历史评分，推荐最优配置

## 五、解决方案概述

### 三维度评分引擎

```python
class TaskQualityScorer:
    def score(
        task_id: str,
        chat_history: list,      # 维度1 数据源
        clarifier_result: dict,  # 维度2 数据源
        task_outcome: str,       # 维度3 数据源: DONE/FAILED
        review_passed: bool,     # 维度3 数据源
    ) -> TaskQualityScore:
        dim1 = self._user_satisfaction(chat_history)   # 0-1
        dim2 = self._session_quality(clarifier_result)  # 0-1
        dim3 = self._delivery_outcome(task_outcome, review_passed)  # 0-1
        return TaskQualityScore(
            user_satisfaction=dim1,
            session_quality=dim2,
            delivery_outcome=dim3,
            total=0.3*dim1 + 0.3*dim2 + 0.4*dim3,  # 交付权重最高
        )
```

### 对话驱动 mode 调优

```
用户: "问快点，别太啰嗦"
  → ClarifierAgent._detect_mode_intent(message)
    → 匹配: "快点" → preset="fast"
      → ModeLoader.update_mode("clarify", preset="fast")
        → 写回 mode.yaml:
            max_questions_per_branch: 20 → 8
            question_strategy: depth_first → breadth_first
        → 回复: "已调整。后续提问会加快节奏，每分支最多 8 个问题。"
```

三种预设：

| 预设 | 参数调整 | 适用场景 |
|------|---------|---------|
| `fast` | max_questions_per_branch=8, strategy=breadth_first | 简单 CRUD / 原型开发 |
| `deep` | max_questions_per_branch=30, strategy=depth_first | 核心模块改动 / 架构设计 |
| `reset` | 恢复 mode.yaml 原始默认值 | 想回到起点 |

## 六、成功指标

| 指标 | 目标 |
|------|------|
| 评分写入 | 每次 DONE 任务都有评分记录 |
| 评分可用 | TaskQualityScorer 纯函数，零 LLM 调用 |
| mode 调优响应 | <1 秒（YAML 写回操作） |
| 不破坏现有 | 453 测试全绿 |

## 七、Non-Goals

- ❌ G6 自扩展模式生成器（需要累计 50+ 评分数据后再做）
- ❌ 评分驱动的自动策略推荐
- ❌ mode 效果统计面板

## 八、验收标准汇总

| # | 标准 | 对应 US |
|---|------|--------|
| AC1 | TaskQualityScorer 计算三维度分 | US1 |
| AC2 | 任务 DONE 时自动调用 scorer 并写入 audit | US1 |
| AC3 | 用户反馈从 chat 自动提取（正面/负面关键词） | US1 |
| AC4 | `/mode fast` 修改 mode.yaml 并回复确认 | US2 |
| AC5 | `/mode deep` 修改 mode.yaml 并回复确认 | US2 |
| AC6 | `/mode reset` 恢复默认 mode.yaml | US2 |
| AC7 | 自然语言检测"快点"/"别问了"/"问细点" | US2 |
| AC8 | 现有测试全绿 | 回归 |
| AC9 | 新增 scorer + mode_tuner 单元测试 ≥10 条 | 覆盖率 |

---

> 8 条验收标准，1 个 PR。等待确认后进入阶段2。
