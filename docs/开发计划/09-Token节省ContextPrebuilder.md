# 09 - Token 节省 ContextPrebuilder 体系

> 日期: 2026-07-05 | 状态: 设计阶段 | 关联: [06-减熵体系](06-减熵体系.md) | [01-上下文与Prompt](01-上下文与Prompt.md)
> 来源: [Token节省落地执行报告 §11 Phase 2](file:///C:/Users/Administrator/OneDrive/Desktop/Token节省落地执行报告_2026-06-26.md)
> 详细报告: [Token节省Phase2——Orbit Agent层上下文预构建方案.html](file:///D:/Orbit docs/Token节省Phase2——Orbit Agent层上下文预构建方案.html)

## 核心原则

**确定性工具做筛选、定位、摘要 → LLM 只处理需要判断的部分。**

Orbit 已有反应式压缩（循环中 L1-L5 管线），缺前置预处理——Agent 看到数据之前，确定性脚本已完成筛选。

## 5 大可学点

| # | 学点 | 改造 | 新增模块 |
|---|------|------|---------|
| 1 | Pre-dispatch Context Builder per Role | TaskRunner dispatch 前按角色裁剪 context | `context/prebuilder.py` + 5 子类 |
| 2 | "不含完整 diff"原则下沉 | TaskContext max_chars_per_field + Agent 间消息约束 | 修改 `agents/context.py` + `communication/message_bus.py` |
| 3 | 7 个 Phase 2 脚本 → Context Builder | 确定性脚本替代 LLM 扫描 | `context/builders/` 7 文件 |
| 4 | 确定性预扫描器 | 不用 LLM 判断——脚本给出结论 | `context/scanners/` 5 文件 |
| 5 | 变更范围感知 → 测试粒度 | SCOPING 状态 + DiffScope 规则引擎 | 修改 `scheduler/task_runner.py` |

## 目标 Token 节省

- 单任务链（5 Agent 调用）：~40,000 → ~22,500 token（-44%）
- Agent 间消息：-20~30%
- QA Agent 测试执行：-50~70%

## 实施阶段

- Phase A（第 1 周）：基座——ContextPrebuilder 基类 + Scanner + TaskRunner 集成
- Phase B（第 2 周）：角色适配——5 子类 + 7 Builder + 3 Scanner + MessageBus 约束
- Phase C（第 3 周）：Scoping + 验收——SCOPING 状态 + 真实 PR 验收 + Token 基准测试

## 新增文件

```
src/orbit/context/
├── prebuilder.py              # 基类 + 接口
├── prebuilders/               # 5 个角色子类
├── builders/                  # 7 个 Context Builder
└── scanners/                  # 5 个确定性预扫描器
```
