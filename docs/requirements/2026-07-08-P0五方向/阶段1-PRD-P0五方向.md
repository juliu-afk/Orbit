# 阶段1 PRD —— P0 五方向合集

> 基线：`docs/research/√Orbit-理论提升空间分析.html` 方向 2/13/8/16/20
> 创建日期：2026-07-08

## 一、背景

理论提升空间分析报告识别了 6 个 P0 即时方向。方向 1（因果推理）已在 PR #239 交付。剩余 5 个方向独立可并行，合并为一个 PR 交付。

## 二、方向概览

| # | 方向 | 改动规模 | 核心产出 |
|---|------|---------|---------|
| 2 | Bandit 路由 | +150行 | API 成本 -20% |
| 13 | PID 控制器 | +220行 | CRITICAL 告警 -70% |
| 8 | 类型导向合成 | +180行 | 类型错误 -67% |
| 16 | 共形预测 | +200行 | 输出带数学置信度 |
| 20 | 变点检测 | +200行 | 急变检测延迟 -70% |

---

## 三、方向 2：Bandit 路由

### 问题
`router/agent.py::RouterAgent` 用固定权重（ScoreWeights）选模型层级。权重不随实际结果更新——是 open-loop 决策。

### 用户故事
> 作为系统，我希望模型选择基于历史成功/失败自动调整，而非固定权重，以便 API 成本持续优化。

### 验收标准
1. `router/` 新增 `bandit.py`——Thompson Sampling 多臂 Bandit 路由器
2. Bandit 每任务更新 Beta 后验（成功=α+1，失败=β+1）
3. RouterAgent 可选启用 Bandit 模式（环境变量 `ORBIT_ROUTER_BANDIT=1`）
4. 收敛后模型选择最优率从 ~65% 提升到 ~90%

### Non-Goals
- 不替换现有固定权重路由（并行跑，开关控制）
- 不做上下文 Bandit（仅多臂，不建模任务特征）

---

## 四、方向 13：PID 控制器

### 问题
Monitor 输出 CRITICAL → HITL。这是 bang-bang 控制——小的目标漂移被无视，等积累到 CRITICAL 时已偏离太远。

### 用户故事
> 作为 Monitor 模块，我希望用连续矫正信号替代二元告警，在早期微调 Agent 行为，减少 CRITICAL 告警频率。

### 验收标准
1. `metacognition/` 新增 `pid_controller.py`
2. PID 输入：GoalDriftDetector 的漂移分数 + RepetitionDetector 的重复次数
3. PID 输出：矫正 guidance 文本，注入 Agent 下轮 system prompt
4. 四级矫正：subtle(<0.3) / gentle(0.3-0.6) / firm(0.6-0.9) / urgent(>0.9)
5. CRITICAL 告警频率下降 60-80%

### Non-Goals
- 不替换 Monitor（Monitor 继续做二元告警，PID 做连续调节）
- 不自动调 PID 参数（Kp/Ki/Kd 默认值，后续自调优）

---

## 五、方向 8：类型导向合成

### 问题
L4 TypeValidator 在生成后检查类型错误。类型签名包含 Wadler "free theorems" 信息，本发明可以在生成时利用。

### 用户故事
> 作为 Agent 代码生成器，我希望能从类型签名中推导约束，在生成前缩小搜索空间，减少类型错误。

### 验收标准
1. `hallucination/l4_type.py` 新增 `TypeDirectedSynthesizer` 类
2. 从函数类型签名推导约束（多态→free theorem，参数类型→必要导入）
3. 约束注入 Agent system prompt（生成前而非生成后）
4. L4 类型错误检出率从 ~15% 降到 ~5%

### Non-Goals
- 不做完整的程序合成（不生成代码骨架）
- 不做 Djinn 风格的实现推导

---

## 六、方向 16：共形预测

### 问题
GEPA 用全局 utility 评分原则。RouterAgent 选模型。两者给出点估计——无置信区间。

### 用户故事
> 作为系统，我希望每个 Agent 输出都带有数学保证的置信度，以便自动化决策时有质量闸门。

### 验收标准
1. `testing/` 新增 `conformal.py`——Inductive Conformal Prediction
2. 校准集：历史 (task, code, outcome) 三元组的非一致性评分分布
3. 预测：给定新任务 + N 个候选代码，返回 1-α 置信预测集
4. GEPA 原则选择用共形 p-value 替代硬阈值 utility > 0.6
5. Ensemble 用共形预测选可靠子集

### Non-Goals
- 不做 online conformal（仅 inductive）
- 不做自适应 α（固定 0.05）

---

## 七、方向 20：变点检测

### 问题
Bandit 适应慢漂移（~50 次失败才收敛）。LLM provider 变更是急变——成功率一次从 90% 跌到 50%。需要统计检测。

### 用户故事
> 作为系统，我希望检测 LLM 模型行为急变，在变点触发模型重评估，减少因静默更新导致的连续失败。

### 验收标准
1. `observability/` 新增 `drift_detector.py`——CUSUM 变点检测
2. 监控三元组：成功率、延迟、输出长度
3. CUSUM 阈值 h=5（ARL₀≈148，检测延迟 ~15 次）
4. 变点触发 → RouterAgent 该模型 Beta 后验重置为先验
5. 与 Bandit 互补——Bandit 慢适应 + CUSUM 急检测

### Non-Goals
- 不做多变量联合 CUSUM（独立监控各 metric）
- 不做贝叶斯变点检测（CUSUM 够用）

---

## 八、汇总

| 方向 | 新文件 | 修改文件 | 新依赖 |
|------|--------|---------|--------|
| 2. Bandit | `router/bandit.py` | `router/agent.py` | 无 |
| 13. PID | `metacognition/pid_controller.py` | `metacognition/monitor.py` | 无 |
| 8. 类型合成 | 无 | `hallucination/l4_type.py` | 无 |
| 16. 共形 | `testing/conformal.py` | `evolution/gepa.py` | 无 |
| 20. 变点 | `observability/drift_detector.py` | `router/agent.py` | 无 |
| **合计** | **4 新文件** | **5 修改** | **0 新依赖** |

## 九、Non-Goals（整体）

- 五个方向并行开发，互不依赖
- 不改调度器状态机
- 不改图谱引擎
- 不改沙箱
