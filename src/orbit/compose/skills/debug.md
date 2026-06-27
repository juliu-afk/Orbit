---
name: compose:debug
description: 根因优先系统调试——分析错误日志后定位根因并修复
phase: implement
tools: [read_file, grep, exec_command]
agent_role: developer
---
# compose:debug

## 流程
1. 收集错误信息——读取日志/测试输出
2. 定位根因——grep 搜索相关代码
3. 提出修复方案——最小改动原则
4. 执行修复——edit_file
5. 验证——exec_command(pytest)

## 原则
- 根因优先——不要修复症状
- 最小改动——改动越小风险越低
- 验证通过——修复后必须跑测试
