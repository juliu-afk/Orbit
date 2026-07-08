# 阶段1 PRD —— 批次A：频谱分析+博弈论+PAC+程序切片

> 基线：理论提升空间分析 方向3/9/14/24 | 日期：2026-07-09

## 一、方向概览

| # | 方向 | 新文件 | 改动规模 | 核心产出 |
|---|------|--------|---------|---------|
| 3 | 图谱频谱分析 | `graph/spectral.py` | +250 | 拉普拉斯特征分解→模块边界量化 |
| 9 | 博弈论协调 | `compose/mechanism.py` | +200 | VCG机制→Agent诚实报价 |
| 14 | PAC泛化保证 | `evolution/pac_bounds.py` | +150 | 泛化误差上界→GEPA自适应 |
| 24 | 程序切片 | `graph/engines/slicer.py` | +200 | AST→PDG→前向/后向切片 |
| **合计** | | **4新+4改** | **~800** | **0新依赖** |

## 二、D3 图谱频谱分析

**问题**：元图谱12种关系是离散边，无连续谱分析。模块边界判断靠人工。

**验收标准**：
1. `graph/spectral.py`——对代码图邻接矩阵做拉普拉斯特征分解
2. Fiedler向量做模块二分——自动建议拆分点
3. 谱半径量化变更传播最坏范围
4. 驾驶舱"Spectral View"热力图（Fiedler向量）

**Non-Goals**：不做联合谱嵌入（多图谱），不做增量特征分解

## 三、D9 博弈论协调

**问题**：ComposeOrchestrator用固定GOLDEN_ROUTE分配子任务。Agent不能诚实申报能力。

**验收标准**：
1. `compose/mechanism.py`——VCG机制，Agent对子任务报价
2. 分配使诚实报价是占优策略
3. 降级：无Agent报价→GOLDEN_ROUTE兜底
4. 与现有ComposeOrchestrator可选集成（开关控制）

**Non-Goals**：不做多轮竞标，不做预算约束

## 四、D14 PAC泛化保证

**问题**：GEPA进化3代→utility上升，但无法回答"泛化到新任务吗？"。SCOPE的UPGRADE_THRESHOLD=3是拍出来的。

**验收标准**：
1. `evolution/pac_bounds.py`——计算泛化误差上界 ε=√(ln|H|+ln(1/δ))/2m
2. GEPA每代输出泛化误差上界
3. 界宽时自动停止进化+建议更多评估数据
4. SCOPE UPGRADE_THRESHOLD用PAC指导替代硬编码3

**Non-Goals**：不做VC维分析（假设空间复杂），不做Rademacher复杂度

## 五、D24 程序切片

**问题**：CodeGraph追踪调用关系但不做数据依赖。"改第47行影响哪些输出？"

**验收标准**：
1. `graph/engines/slicer.py`——AST→PDG→前向/后向切片
2. 前向切片：第N行变量影响哪些输出行
3. 后向切片：输出X依赖哪些行
4. 配合L1 GraphValidator——精确标定错误影响范围

**Non-Goals**：不做过程间切片（inter-procedural），不做动态切片

## 六、汇总

| 方向 | 验收标准 | 优先级 | 依赖 |
|------|---------|-------|------|
| D3 频谱 | 4 | P1 | scipy（已有） |
| D9 博弈 | 4 | P1 | 无 |
| D14 PAC | 4 | P1 | 无 |
| D24 切片 | 4 | P1 | 无 |
| **合计** | **16 AC** | | **0新依赖** |
