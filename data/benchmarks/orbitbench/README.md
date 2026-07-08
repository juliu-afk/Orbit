# OrbitBench — Orbit 能力基准测试集

Orbit 模块效能评估框架的 L2 效能测量数据集。包含不同复杂度、语言、领域的任务样本，每样本附带 ground truth 实现和验证脚本。

## 目录结构

```
orbitbench/
├── README.md              # 本文件
├── L0_syntax_fix/         # L0: 语法修复 (目标 50 样本, ≥100% 成功率)
├── L1_single_file/        # L1: 单文件功能 (目标 100 样本, ≥90% 成功率)
├── L2_multi_file/         # L2: 多文件改动 (目标 60 样本, ≥80% 成功率)
├── L3_cross_module/       # L3: 跨模块重构 (目标 30 样本, ≥60% 成功率)
├── L4_new_feature/        # L4: 新功能开发 (目标 20 样本, ≥50% 成功率)
└── L5_system_level/       # L5: 系统级任务 (目标 10 样本, ≥30% 成功率)
```

## 样本格式

每个样本为一个目录，包含:
- `task.md` — 任务描述（用户看到的输入）
- `context/` — 项目上下文（git snapshot）
- `ground_truth.py` — 正确实现
- `verify.py` — 验证脚本（pytest 可执行）

## 维护规则

- 每个迭代添加 10+ 新案例
- 基准数据集不用于训练/进化——仅用于评估
- 发现新的失败模式时优先添加对应样本
