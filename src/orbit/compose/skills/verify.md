---
name: compose:verify
description: 验证工作流——跑全量测试+覆盖率检查确认交付质量
phase: verify
tools: [exec_command, read_file]
agent_role: qa
---
# compose:verify

## 流程
1. 跑全量单元测试——pytest tests/unit/ -q
2. 跑集成测试——pytest tests/integration/ -q
3. 检查覆盖率——--cov-fail-under=80
4. 跑 lint——ruff check
5. 汇总验证报告

## 门禁
- 单元测试 100% 通过
- 集成测试 100% 通过
- 覆盖率 >= 80%
- lint 0 错误
- 任一不通过 → 返回 FAIL，标注原因
