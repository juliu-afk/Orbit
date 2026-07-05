---
name: compose:subagent
description: 按任务分发子Agent——依赖感知的并行调度策略
phase: implement
tools: [read_file, write_file, edit_file]
agent_role: developer
---
# compose:subagent

## 思考框架（必须遵守——依赖感知调度 + 错误隔离）

### 任务分派决策树

收到 spec tasks 列表后，按以下决策树分派:

```
1. 分析依赖关系
   ├── 无依赖 tasks → 并行执行（上限: 4 并发）
   └── 有依赖 tasks → 等待上游完成

2. 对每个 task:
   ├── 有 skill 指定 → 注入对应技能 + 角色
   ├── 有 agent_role 指定 → 注入对应角色
   └── 均无 → 默认 developer 角色

3. 错误处理:
   ├── 单 task 失败 → 记录, 不阻塞其他 task
   ├── 依赖链上游失败 → 下游 task 标记为 blocked（等上游修复后重跑）
   └── 全部失败 → 汇总错误, 返回 FAIL
```

### 并发策略

| 场景 | 策略 | 理由 |
|------|------|------|
| 3 个无依赖 tasks | 全部并行 | 无阻塞关系, 并行最快 |
| 5+ 个无依赖 tasks | 分批并行（每批 ≤4） | 避免 Token/API 速率限制 |
| 链式依赖 A→B→C | 串行（A 完成→B→C） | 上游输出是下游输入 |
| 混合依赖 | Kahn 拓扑排序分层, 层内并行, 层间串行 | 最大化并行度 |

### 错误隔离原则
- **一个 task 失败 ≠ 全部失败**——独立 tasks 互不影响
- **依赖链传播**——上游失败→下游 blocked（保留上游错误上下文, 不丢弃）
- **重试机制**——失败 task 自动重试 1 次（瞬态错误: 网络超时/API 限流）

## 流程
1. 读取 plan.md——理解实现方案和任务依赖
2. 分析 spec tasks 列表——构建依赖 DAG
3. 按决策树分派子Agent:
   - 每个 task 创建独立 Agent 实例
   - 注入对应角色 + 工具权限 + 技能（如指定）
   - 设置依赖关系——Kahn 拓扑排序分层
4. 收集子Agent 输出——合并到统一结果集
5. 汇总——成功数/失败数/阻塞数 + 每个 task 的产物路径

## 输出
```json
{
  "status": "ok|partial|failed",
  "summary": {"total": N, "succeeded": N, "failed": N, "blocked": N},
  "tasks": {
    "task-1": {"status": "ok", "output": "...", "branch": "feat/task-1"},
    "task-2": {"status": "failed", "error": "...", "retry_attempted": true},
    "task-3": {"status": "blocked", "blocked_by": "task-2", "reason": "上游失败"}
  }
}
```
