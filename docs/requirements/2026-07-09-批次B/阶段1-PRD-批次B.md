# 阶段1 PRD —— 批次B：信息瓶颈+最优传输+MDP+抽象解释

> 基线：理论提升空间分析 方向4/11/17/22 | 日期：2026-07-09

## 一、方向概览

| # | 方向 | 新文件 | 改动 | 核心产出 |
|---|------|--------|------|---------|
| 4 | 信息瓶颈压缩 | `compression/ib_compressor.py` | +200 | IB聚类→给定预算形式化最优上下文 |
| 11 | 最优传输分配 | `context/ot_matcher.py` | +180 | Sinkhorn算法→Wasserstein最优上下文分配 |
| 17 | MDP形式化 | `agents/mdp.py` | +200 | Bellman gap量化→策略偏离度量 |
| 22 | 抽象解释 | `hallucination/abstract_interp.py` | +180 | Galois连接→防幻觉管道可靠上近似 |
| **合计** | | **4新+4改** | **~760** | |

## 二、D4 信息瓶颈压缩

**问题**：compression/用启发式截断。给定Token预算下无法保证信息保真度最优。

**验收标准**：
1. `compression/ib_compressor.py`——IB聚类上下文片段为K个原型
2. 给定预算B→0-1背包选最大MI原型子集
3. 替换compressor.py截断策略（环境变量开关）

## 三、D11 最优传输分配

**问题**：ContextPrebuilder用关键词匹配。多Agent竞争同一上下文时无全局最优分配。

**验收标准**：
1. `context/ot_matcher.py`——Sinkhorn算法快速OT
2. 上下文嵌入为源分布→Agent需求为靶分布→Wasserstein最优映射
3. Token预算作为容量约束

## 四、D17 MDP形式化

**问题**：Agent循环从未被形式化建模。无法回答"离最优有多远"。

**验收标准**：
1. `agents/mdp.py`——状态/动作/奖励/转移的形式化定义
2. Bellman gap计算→量化策略偏离最优程度
3. 离线分析层——不替换ReAct循环

## 五、D22 抽象解释

**问题**：HallucinationPipeline按顺序跑L1-L8。L1失败后L2-L7是否必然也失败——当前靠经验判断。

**验收标准**：
1. `hallucination/abstract_interp.py`——Galois连接抽象域
2. 层级间依赖图——L1失败→哪些层必然受影响
3. 可靠上近似（不漏报假阴性）

## 六、汇总

**16 AC | 0 新依赖 | ~760行**
