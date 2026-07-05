# 阶段2 技术方案：EvolveR LLM 语义蒸馏 + GRPO

> 基于阶段1 PRD（验收标准5条），本次方案覆盖5条，无偏离

## 1. 需求回顾

| AC | 方案对应 |
|----|---------|
| AC1: LLM蒸馏≥1条原则 | §2 LLMDistiller |
| AC2: GRPO排序一致性>70% | §3 GRPOScorer |
| AC3: 自动注入，引用率>30% | §4 PromptInjector |
| AC4: ANCHOR拦截100% | 复用现有 AnchorGuard |
| AC5: 覆盖率≥80% | §5 集成 |

## 2. 影响范围

### 新增

| 文件 | 职责 |
|------|------|
| `src/orbit/evolution/llm_distill.py` | LLM语义蒸馏——批量轨迹→原则 |
| `src/orbit/evolution/grpo.py` | GRPO评分——任务成功率→效用调整 |
| `src/orbit/evolution/inject.py` | 高效用原则自动注入 system prompt |

### 修改

| 文件 | 改动 |
|------|------|
| `src/orbit/evolution/__init__.py` | 导出新模块 |
| `src/orbit/evolution/distill.py` | DistillationEngine 添加 LLM 蒸馏回调 |

## 3. 详细设计

### 3.1 LLMDistiller

输入: 3-10条同类轨迹的 TrajectoryCollector export
处理: LLM prompt "这3条审计任务的成功轨迹有什么共同模式？提炼1-3条可复用原则"
输出: StrategyPrinciple 列表 → 存入 DistillationEngine

### 3.2 GRPOScorer

模拟 GRPO: 原则效用 = (应用后成功率 - 基线成功率) / 基线成功率
- 应用后成功率 > 基线 → 效用+0.1
- 应用后成功率 = 基线 → 效用不变
- 应用后成功率 < 基线 → 效用-0.05
自动剪枝: 效用<0.15 且应用≥10次 → 删除

### 3.3 PromptInjector

在 AgentFactory 创建 Agent 时:
- 查询 DistillationEngine.top_principles(min_utility=0.7, limit=5)
- 格式化为 "## 已验证策略\n- {principle}\n..."
- 注入 system prompt 末尾

## 4. 与PRD对照表

| AC | 实现位置 |
|----|---------|
| AC1 | evolution/llm_distill.py:distill_batch() |
| AC2 | evolution/grpo.py:score_principles() |
| AC3 | evolution/inject.py + agents/factory.py |
| AC4 | evolution/anchor.py:check_after_distill() |
| AC5 | 集成后手动评估 |
