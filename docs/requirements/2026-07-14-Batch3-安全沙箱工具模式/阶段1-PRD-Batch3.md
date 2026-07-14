# 阶段1-PRD-Batch3

> 需求简称：V15.2 安全沙箱工具模式
> 日期：2026-07-14
> 基于：[调研报告](../../research/WeChat-Articles-Analysis-2026-07-13.md) P1 #5, #8, #9
> 对标：Zerox Agent shellAnalyzer + UE MCP Domain Action 模式

## 用户故事

| # | P | 故事 | 验收 |
|---|----|------|------|
| US-1 | P1 | Agent 执行 shell 命令前，自动扫描危险模式（分号注入、管道注入、rm -rf） | 检测到危险→阻止执行+报警。tree-sitter AST 解析，不靠正则 |
| US-2 | P1 | 沙箱执行失败时返回结构化错误（位置+类型+建议），AI 能基于此自动修正 | 错误含 line/col + error_type + fix_suggestion |
| US-3 | P1 | 工具按领域分组（Domain Action），避免 context 中列出全量工具 | action/params 路由，单 domain 一个 MCP tool |

## 模块

| 模块 | 操作 | 内容 | 预估 |
|------|------|------|------|
| `security/shell_analyzer.py` | **新建** | tree-sitter-bash AST shell 安全分析 | 1d |
| `sandbox/executor.py` | 修改 | 结构化错误响应 | 0.5d |
| `tools/registry/domain.py` | **新建** | DomainActionRouter | 1d |

---

> 阶段1 直接进阶段2+3（小批量，三个独立模块，无需长方案）。
