---
name: compose:subagent
description: 按任务分发子Agent 执行——读取 spec 任务列表后逐个分派
phase: implement
tools: [read_file, write_file, edit_file]
agent_role: developer
---
# compose:subagent

## 流程
1. 读取 plan.md——理解实现方案
2. 按 spec tasks 列表顺序分派子Agent：
   - 每个 task 创建一个 ReActAgent 实例
   - 注入对应角色 + 工具权限
   - 设置依赖关系——依赖完成后再启动
3. 收集子Agent 输出——合并到统一结果集

## 并发策略
- 无依赖任务的 tasks——并发执行（最多 4 并行）
- 有依赖的 tasks——等待上游完成
- 任一 task 失败——记录但不阻塞其他 task

## 输出
每个 task 的输出汇总为 tasks.json
