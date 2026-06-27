---
name: compose:review
description: 代码审查——读取变更后检查正确性、安全、性能
phase: review
tools: [read_file, grep, glob]
agent_role: reviewer
---
# compose:review

## 流程
1. 读取变更文件——git diff 或 file list
2. 逐文件审查：
   - 正确性——逻辑是否正确
   - 安全性——SQL注入/XSS/命令注入/硬编码密钥
   - 性能——O(n²) 循环/缺失索引/N+1 查询
   - 风格——命名/注释/三行相似不抽象
3. 输出审查报告——每行 severity-tagged

## 审查报告格式
```
path:line: <emoji> <severity>: <问题>. <建议修复>.
```
