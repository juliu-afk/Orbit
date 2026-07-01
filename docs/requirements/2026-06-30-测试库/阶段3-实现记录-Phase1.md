# 阶段3 实现记录 — Phase 1 (mocks + 基础 factories)

> 2026-07-01 | 分支: `feat/test-lib-phase1`

## 方案引用

基于阶段2 技术方案 §2.1-§2.2、§11 Phase 1 范围。
严格按方案实现，无偏离。

## 改动清单

| 文件 | 行数 | 改动 | 说明 |
|------|------|------|------|
| `tests/lib/__init__.py` | 11 | 新增 | 模块说明 |
| `tests/lib/mocks/__init__.py` | 23 | 新增 | 7 Mock 导出 |
| `tests/lib/mocks/llm_client.py` | 216 | 新增 | 流式+工具调用+失败序列+延迟+熵值；迁移增强自 `tests/e2e/mock_llm.py` |
| `tests/lib/mocks/sandbox.py` | 139 | 新增 | 超时/OOM/权限拒绝/非零退出 |
| `tests/lib/mocks/checkpoint.py` | 143 | 新增 | Redis/PG降级+版本冲突 |
| `tests/lib/mocks/circuit_breaker.py` | 123 | 新增 | CLOSED→OPEN→HALF_OPEN 状态机 |
| `tests/lib/mocks/knowledge.py` | 116 | 新增 | 命中率+预设结果 |
| `tests/lib/mocks/event_bus.py` | 112 | 新增 | 队列满丢弃+订阅追踪 |
| `tests/lib/mocks/tool_registry.py` | 156 | 新增 | 限流+Doom Loop+dispatch/invoke 双API |
| `tests/lib/factories/__init__.py` | 22 | 新增 | 工厂导出 |
| `tests/lib/factories/llm.py` | 109 | 新增 | LLMRequest/Response/Usage |
| `tests/lib/factories/checkpoint.py` | 47 | 新增 | CheckpointData |
| `tests/lib/factories/agent.py` | 68 | 新增 | AgentInput/Output |

**总计**: 13 文件, 1,285 行。零生产文件修改。零新依赖。

## 偏差说明

严格按方案实现，无偏离。

技术方案 Phase 1 范围：mocks/ 全部 (7 文件) + factories/ 基础 (3 文件: llm/checkpoint/agent)。实际交付 7 mock + 3 factory = 10 核心文件 + 3 个 `__init__.py` = 13 文件。

## 回溯对照

| PRD AC | 方案设计 | 代码实现 |
|--------|---------|---------|
| AC-2 Mock 100% 兼容原接口 | §2.2 每个 Mock 接口签名 | `llm_client.py:154 generate(req, task_id, agent_name, router_decision, routing_strategy)` |
| AC-8 零新依赖 | §10.2 仅用 pytest+pydantic+stdlib | grep 确认无新 import |
| US-2 可配置 Mock | §2.2 链式配置 API | `.with_failures(3).with_response(...)` 链式方法 |
