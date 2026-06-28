# PR #2 Type Safety — 阶段1 PRD

> 日期: 2026-06-28 | 分支: fix/phase4-type-safety | 参考: 总结-业界追赶.md §6

## 背景

Phase 4 代码审查发现 2 类类型安全问题：
1. `ActorSpawn._create_agent()` 回退路径 `type: ignore[attr-defined]`
2. 5 个文件 `Any` 类型未收敛，mypy 静态分析失效

## 用户故事

| # | 优先级 | 描述 | AC |
|---|:--:|------|-----|
| 3 | P1 | `SpawnedAgent` 不再需要 `type: ignore` | `_create_agent()` 无 `type: ignore` 注释 |
| 5 | P1 | 核心 Agent 模块 `Any`→具体类型 | `react_agent.py`, `factory.py`, `spawn.py`, `compose/orchestrator.py`, `scheduler/orchestrator.py` 参数使用具体类型 |

## Non-Goals

- 不修复 mypy `--strict` 模式下的所有预存错误
- 不重构类层次结构（BaseAgent/ReActAgent 继承关系不变）
- 不添加新依赖

## 待确认

无——类型映射已有明确对应关系。
