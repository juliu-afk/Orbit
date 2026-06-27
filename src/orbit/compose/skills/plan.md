---
name: compose:plan
description: 写 specs-driven 实现方案——分析 spec 后输出架构设计
phase: plan
tools: [read_file, grep, glob]
agent_role: architect
---
# compose:plan

## 流程
1. 读取 spec 文件——理解项目目标和约束
2. 分析现有代码结构——read_file + grep + glob 了解上下文
3. 输出架构设计方案：
   - 模块划分
   - 数据流
   - 接口定义
   - 依赖关系
4. 方案保存为 plan.md——供后续技能引用

## 输出格式
```markdown
# 实现方案

## 模块划分
- module_a/: 职责描述
- module_b/: 职责描述

## 数据流
输入 → 处理 → 输出

## 接口
- POST /api/v1/xxx
- function_name(params) → return_type
```
