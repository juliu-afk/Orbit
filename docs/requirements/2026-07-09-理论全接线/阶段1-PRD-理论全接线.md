# 阶段1 PRD —— 19个理论模块全接入生产

> 基线：P0已接线，P1+P2 19模块零调用 | 日期：2026-07-09

## 接线方案

| 生命周期钩子 | 接入模块 | 说明 |
|-------------|---------|------|
| `on_task_start` | PACBound | 自适应SCOPE阈值 |
| `on_task_end` | AgentMDP, BFTGuard, FreeEnergy | Bellman gap + 操作审计 + ΔF |
| `on_model_tier_decided` | PACBound | 记录评估样本数 |
| `enhance_prompt` | IBCompressor, OTMatcher, SpectralAnalyzer, ProgramSlicer, EffectTracker, TypeDirected | 6模块注入 |
| `maybe_distill` | Shapley, MDL, InfoGeometry, FreeEnergy, VCG | 5模块离线管线 |
| `pipeline` hook | AbstractPipeline, L9Temporal, L10Separation, DPGuard, TDA, Bisimulation | 6模块验证层 |
| `_get_*` lazy | 全部19模块 | 懒初始化 |

## 验收标准

1. wiring.py新增19个`_get_*()`懒getter
2. 每个生命周期钩子调用对应模块
3. fail-open——任何模块异常不阻塞主流程
4. 19个模块各≥1个生产调用点（grep验证）
5. 测试全通过
