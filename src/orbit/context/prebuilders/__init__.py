"""角色特定 ContextPrebuilder 子类 (Phase 2 Token节省).

每个子类按 Agent 角色裁剪 context——删除无关字段、截断超大值。
fail-open 设计：异常时返回原始 context，不阻塞 Agent 执行。
"""
