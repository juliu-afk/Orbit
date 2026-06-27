---
name: compose:tdd
description: 测试驱动开发——先写测试再写实现直到绿灯
phase: implement
tools: [write_file, edit_file, exec_command]
agent_role: developer
---
# compose:tdd

## 流程
1. 读 spec——理解功能需求
2. RED: 写失败测试——覆盖核心路径 + 边缘情况
3. GREEN: 写最小实现——让测试通过
4. REFACTOR: 重构——消除重复，改善可读性
5. 循环直到 spec 所有验收标准覆盖

## 原则
- 测试先行——先看到红灯
- 最小实现——只写让测试通过的代码
- 持续重构——每次绿灯后检查
