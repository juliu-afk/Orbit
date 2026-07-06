# 阶段 1 PRD —— 代码质量 6 项修复

## 背景

对 Orbit 代码库进行多维评估后，发现以下代码质量问题。经逐项排查确认根因和方案，本批修复 5 项（第 1 项 dream/scheduler.py 已删除，无需处理）。

## 用户故事

| 优先级 | 作为 | 我希望 | 以便 |
|:--:|------|------|------|
| P0 | 开发者 | 异常发生时看到具体日志而非静默跳过 | 调试时能快速定位问题根因 |
| P0 | 维护者 | clarifier.py 按职责拆分 | 修改 Prompt 模板时不碰 Agent 调度逻辑 |
| P0 | 项目 | CI 自动跑 pytest | 覆盖率不会在无感知情况下恶化 |
| P1 | 开发者 | 核心链路异常被分层处理 | 已知可恢复异常触发重试，未知崩溃不丢失 |
| P2 | 类型安全 | 可消除的 type: ignore 被清理 | 类型检查工具能捕获真正的类型错误 |

## 验收标准

### AC1: except:pass 加日志（6 处）
- **AC1.1**: `react_agent.py:238` prompt 增强失败 → WARNING 日志含 `exc_info`
- **AC1.2**: `react_agent.py:371` PreAct 预测失败 → DEBUG 日志（fail-open 是设计意图）
- **AC1.3**: `wiring.py:240,248` MonitorAgent/MCTSPlanner 构造失败 → WARNING 日志
- **AC1.4**: `task_runner.py:286` 蒸馏调度失败 → WARNING 日志
- **AC1.5**: `task_runner.py:830` 通用接线失败 → WARNING 日志含 `method` 字段
- **AC1.6**: `schedule.py:125` 紧急任务回调异常 → WARNING 日志含 `exc_info`
- **AC1.7**: 日志不包含栈追踪中的敏感信息（API key 等）

### AC2: clarifier.py 拆分（986行 → 4文件）
- **AC2.1**: 拆为 `agent.py` / `prompts.py` / `intent_parser.py` / `decision_tree.py`
- **AC2.2**: `__init__.py` 保持 `from orbit.agents.clarifier.agent import ClarifierAgent`
- **AC2.3**: 现有调用方（`factory.py`、`chat.py`、`task_runner.py`）import 路径不变
- **AC2.4**: 现有 clarifier 相关测试全部通过

### AC3: CI 加 pytest job
- **AC3.1**: `.github/workflows/pr-review.yml` 新增 `test` job
- **AC3.2**: 执行 `pytest tests/unit/ tests/integration/ --cov=src/orbit --cov-fail-under=69 -q`
- **AC3.3**: lint-typecheck 和 test 并行执行
- **AC3.4**: Python 版本 3.11（与 pyproject.toml 约束一致）

### AC4: P0 核心链路异常分层（15 处）
- **AC4.1**: `task_runner.py` / `gateway/client.py` / `checkpoint/manager.py` 中区分可恢复异常 vs 未知异常
- **AC4.2**: 可恢复异常：SandboxExecutionError / LLMTimeoutError / CheckpointConflictError → WARNING + 重试
- **AC4.3**: 未知异常 → CRITICAL + `exc_info=True` + raise

### AC5: type:ignore 消除（16 处可消）
- **AC5.1**: 7 处字符串→枚举转换（chat.py role / offpeak_scheduler status 等）
- **AC5.2**: 5 处加 Optional 属性声明（_mode / _compose_orchestrator / _monitor_queue / db_path）
- **AC5.3**: 4 处 assert 窄化 Optional 类型（redis/pg/llm）
- **AC5.4**: 22 处必要保留的不动
- **AC5.5**: mypy src/ 通过

## Non-Goals

- 不修改任何业务逻辑（除异常分层可能 expose 隐藏 bug）
- 不新增测试文件（测试单独跟进）
- 不拆分 task_runner.py / registry.py / offpeak_scheduler.py（本文档范围外）
- 不收紧 P1/P2 层的 except Exception（仅 P0 核心链路 15 处）
- 不处理 context/builders/ 覆盖率（用户单独做）

## 风险

| 风险 | 概率 | 影响 | 缓解 |
|------|:--:|------|------|
| AC4 raise 未知异常导致任务中断率上升 | 中 | 低 | raise 后上层有全局异常处理 + audit 记录 |
| AC2 拆分引入 import 循环 | 低 | 中 | 拆出的文件不反向 import agent.py |
| AC3 CI pytest 首次运行暴露隐藏失败 | 中 | 低 | 门禁设 69（当前值），不高于现状 |
