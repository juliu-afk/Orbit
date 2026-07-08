# 阶段1 PRD —— 因果推理引擎

> 基线：`docs/research/√Orbit-理论提升空间分析.html` 方向 1
> 创建日期：2026-07-08 &nbsp;|&nbsp; 修订：2026-07-08（用户反馈——4 项待确认决议更新）

## 一、背景

### 用户问题
Orbit 的 Monitor 检测 Agent 执行异常（目标漂移、重复动作、延迟超标），VIGIL 尝试自动修复。但 VIGIL 的 heal 策略是**规则驱动**——"重试 / 降级模型 / 换 Agent 角色"——不追问**根因**。同一任务失败 3 次后 VIGIL 放弃——因为它不知道是 Agent 角色选错了，还是 Prompt 原则有误，还是模型层级不够。

### 当前状态（代码验证）
- `src/orbit/metacognition/monitor.py`：规则引擎（GoalDriftDetector + RepetitionDetector + LatencyWatchdog），输出 Alert（CRITICAL/WARNING）
- `src/orbit/metacognition/vigil.py`：基于 Alert.type 选择 heal 动作（重试/降级/换模型）
- `src/orbit/observability/trajectory.py`：`TrajectoryCollector` 结构化记录每条任务轨迹（agent_role, steps, final_outcome, quality_score, total_turns）
- **空缺**：无因果推理代码——`src/orbit/` 下搜索 `causal|do_calculus|pearl|counterfactual|PC_algorithm` 返回 0 条结果

### ⚠️ 阻塞前置条件：model_tier 未持久化

TrajectoryCollector 当前**不记录模型层级**。RouterAgent 在 `src/orbit/router/agent.py` 中决策 T1/T2/T3，但这个信息没有写入轨迹表。

| 因果变量 | 轨迹表字段 | 状态 |
|---------|-----------|------|
| agent_role | `trajectories.agent_role` | ✅ 已有 |
| task_outcome (Y) | `trajectories.final_outcome` | ✅ 已有 |
| tool_error_rate | `trajectory_steps.outcome` | ✅ 可计算 |
| latency (Z) | `trajectories.completed_at - started_at` | ✅ 可计算 |
| **model_tier** | **无对应字段** | ⚠️ **阻塞** |

**解决方案**：在 `trajectories` 表加 `model_tier TEXT DEFAULT ''` 列。RouterAgent 决策后通过 EventBus 推送 tier 到 TrajectoryCollector。改动量：`trajectory.py` +5 行，`router/agent.py` +3 行。

### 为什么现在做
- 审计链路已有（`TrajectoryCollector` SQLite），数据源就绪（`model_tier` 列补齐后）
- VIGIL heal 成功率估算 ~40%（基于规则猜测），有 30%+ 提升空间
- GEPA 进化依赖失败原因识别——当前用全局 utility，不区"原则差"vs"运气差"
- DoWhy-GCM（MIT 许可证）提供了开箱即用的根因归因 API——`gcm.attribute_anomalies()`

---

## 二、用户故事

### P0 — 失败根因定位
> 作为 VIGIL 自动修复模块，当任务失败时，我希望知道"哪个变量是根因"（Agent 角色？模型层级？Prompt 原则？），以便选择定向 heal 动作而非盲目重试。

**验收标准：**
1. 任务失败后，`causal.root_cause(task_id)` 返回概率排序的根因列表（≥1 个候选）
2. 根因包含"变量名 + 异常分数 + 反事实解释"（如："agent_role=developer 贡献了 72% 的异常——若换 architect，预期成功率 +23%±5%"）
3. VIGIL 的 `diagnose_causal()` 调用 `root_cause()` 后选择 heal 动作
4. 不增加任务执行延迟（因果查询是离线/异步的）

### P1 — 因果图 + LLM 解释 + 驾驶舱面板
> 作为系统运维者，我希望：① Orbit 从历史轨迹中学习因果图结构（或从领域知识构建+数据校准）；② 根因输出附带人类可读的解释；③ 在驾驶舱中看到因果图可视化。

**验收标准：**
1. 因果 DAG 从领域知识构建（agent_role → outcome, model_tier → latency, tool_seq → error_rate），DoWhy 数据校准边权重
2. 根因查询返回 LLM 生成的解释文本（如："这次失败主要是因为选了 developer 角色来处理需要架构设计的任务。developer 缺少全局视角，导致工具调用序列效率低。"）
3. 驾驶舱面板展示交互式因果图（Cytoscape.js 或 ECharts 力导向图），点击节点看到因果效应详情
4. 支持手动修正边方向（运维确认/纠正）

### P2 — GEPA 因果解耦
> 作为 GEPA 进化引擎，我希望用因果效应替代全局 utility 来评分原则的好坏，以消除"原则差但运气好"的混淆。

**验收标准：**
1. `GEPAEngine._mutate()` 的 `failure_reason` 参数从因果分析而非全局统计获取
2. 原则的效用更新从 `+0.1/-0.05` 改为因果效应加权的增量

---

## 三、验收标准总表

| # | 验收标准 | 优先级 | 验证方式 |
|---|---------|-------|---------|
| AC0 | `trajectories` 表新增 `model_tier` 列，RouterAgent 推送 tier | 阻塞 | 集成测试：执行任务→查询轨迹表→model_tier 不为空 |
| AC1 | `root_cause(task_id)` 返回包含异常分数的根因列表 | P0 | 集成测试：5 个已知失败模式的任务，根因定位 top-1 准确率 ≥70% |
| AC2 | VIGIL shadow mode——因果诊断与规则诊断并行，结果对比记录 | P0 | 集成测试：10 次失败→对比因果 heal vs 规则 heal→因果 ≥ 规则 |
| AC3 | 因果 DAG 构建 + DoWhy 数据校准 | P1 | 单元测试：DAG 结构正确（agent_role→outcome, model_tier→latency, tool_seq→error_rate） |
| AC4 | LLM 生成根因解释文本 | P1 | 单元测试：解释文本包含具体变量名 + 反事实建议 |
| AC5 | 驾驶舱因果图面板 | P1 | E2E：面板展示交互式因果图—点击节点看详情 |
| AC6 | GEPA 用因果效应更新 utility（P2） | P2 | 单元测试：`_mutate()` 接收的 failure_reason 来自 causal 而非规则 |
| AC7 | 增量更新（新轨迹追加后更新因果模型，不重学全量） | P1 | 单元测试：追加 10 条轨迹后仅更新受影响边的权重 |

---

## 四、成功指标

| 指标 | 当前基线 | 目标 |
|------|---------|------|
| VIGIL heal 成功率 | ~40%（规则猜测） | ≥70%（因果定向） |
| 根因定位 top-1 accuracy | N/A | ≥70% |
| 因果图边方向 accuracy | N/A | ≥90%（人工构建+数据校准） |
| 每次因果查询延迟 | N/A | ≤100ms（离线预计算） |
| GEPA 进化每代 utility 增速 | ~2%/代 | ≥5%/代（P2） |

---

## 五、待确认问题（已决议）

| # | 问题 | 决议 | 理由 |
|---|------|------|------|
| 1 | 因果库选型 | **DoWhy + GCM**（MIT 许可证） | `gcm.attribute_anomalies()` 精确命中根因归因场景；AWS 维护 + JMLR 2024 发表；内置 Shapley 对称化归因；causal-learn 侧重结构发现而我们 DAG 可从领域知识构建 |
| 2 | 存储格式 | **SQLite 主存储 + JSON 导出** | SQLite 与 TrajectoryCollector 同库，支持 SQL 查询 + 增量更新；JSON 导出供驾驶舱可视化 + git 追踪图演化史 |
| 3 | VIGIL 集成策略 | **Shadow mode 并行** | 因果 heal vs 规则 heal 并行跑 1 周 → 数据驱动决策替换时机 |
| 4 | LLM 参与层 | **P1 含 LLM 解释** | PC/SCM 是纯统计，LLM 仅做根因的人类可读解释——不参与因果计算，避免幻觉污染因果链 |
| 5 | 阻塞前置条件 | **先补齐 model_tier 持久化** | 详见 §一·阻塞前置条件——`trajectories` 加列 + RouterAgent 推送 |

---

## 六、边缘情况

| 场景 | 预期行为 |
|------|---------|
| 轨迹数据不足（<50 条） | DoWhy GCM 拟合失败 → 降级为 Spearman 相关排序，标记 `confidence=low` |
| model_tier 为空（旧轨迹） | 跳过该变量，在 DAG 中标记 `missing_variables=["model_tier"]` |
| 任务进行中即调用 root_cause | 返回错误 `"任务未完成，因果分析需完整轨迹"` |
| 所有节点异常分数低于阈值（<0.3） | 返回 `"无显著根因"` + 建议人工介入 |
| 两个变量异常分数几乎相等（差 <5%） | 并列返回，标记 `tie=true` |
| LLM 解释生成失败 | 降级为数值报告（不含解释文本），标记 `explanation_failed=true` |
| GEPA 无失败轨迹可用 | 跳过因果解耦，用原 utility 评分 |

---

## 七、Non-Goals

- **不**做实时因果干预（不拦截 Agent 动作）——本轮仅离线分析
- **不**替换 Monitor——Monitor 继续做实时告警，因果做离线根因分析
- **不**生成反事实代码（counterfactual code generation）——不生成"如果当时选了 architect，代码会是什么样"
- **不**改调度器状态机
- **不**改防幻觉 L1-L8 pipeline
- **不**自动修改因果图结构（运维确认后才能改边方向）
