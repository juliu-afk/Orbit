# Phase 2 技术方案——黄金圈路由 + 多视角提示

> 基线: 阶段1-PRD-记忆库智能增强.md + ADR-记忆库智能增强.md
> 参考 ADR: #3 (黄金圈内嵌 AgentInput.context)

## 改动文件

| File | Change | Detail |
|------|--------|--------|
| `scheduler/orchestrator.py` | 新增 `_route_by_golden_why()` | Why→初始 Agent 链映射 |
| `agents/factory.py` | ArchitectAgent 增强 system_prompt | 多视角方案生成 |

## 数据流

### 黄金圈路由
```
Task 创建 (via API or compose):
  context.golden_why = "实现新功能" | "修复Bug" | "代码审查" | "重构" | "数据分析"
  context.golden_how = "从零编写" | "修改已有" | "参考实现" | ""
  context.golden_what = "新增文件" | "修改3行" | "跨模块改动" | ""

Scheduler._route_by_golden_why(why):
  "实现新功能" → [ARCHITECT, DEVELOPER]
  "修复Bug"   → [QA, DEVELOPER, REVIEWER]
  "代码审查"  → [REVIEWER]
  "重构"      → [ARCHITECT, DEVELOPER]
  _default     → [DEVELOPER]  # 向后兼容
```

### 多视角提示
```
ArchitectAgent.system_prompt():
  现有: 单视角设计
  改进: 要求生成 ≥2 个方案，从 [可行性/可维护性/性能] 三维度评分选最优
```

## 实现细节

### 1. Scheduler._route_by_golden_why
```python
GOLDEN_ROUTE: dict[str, list[str]] = {
    "实现新功能": ["architect", "developer"],
    "修复Bug":   ["qa", "developer", "reviewer"],
    "代码审查":  ["reviewer"],
    "重构":      ["architect", "developer"],
    "数据分析":  ["developer"],
}
```

### 2. ArchitectAgent.system_prompt
在现有 prompt 末尾追加多视角指令（见实现）。

## 风险
- 路由改变不破坏现有行为——默认回退 developer（原路径）
- 多视角提示增加 token 消耗——仅 ArchitectAgent 受影响，且其 MAX_TURNS=10 已较低
