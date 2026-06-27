# ADR：Phase 4 胶水集成——架构决策记录

> 日期: 2026-06-27 | 5 条决策

---

## ADR-1：SSE 路由注册——main.py 直接 include vs 独立启动脚本

### 决策

**main.py 直接 `include_router(stream/sse.py)`.**

### 理由

- SSE 端点是核心 API，不是可选组件。放在 main.py 保证每次启动都可用
- 已有模式：WS router 已通过 `ws_router` 注册在 main.py 第 87 行
- 不新建启动脚本——避免多入口维护成本

---

## ADR-2：PermissionEngine 挂载——registry.dispatch() 前置钩子 vs 独立中间件

### 决策

**`tools/registry.py` 的 `dispatch()` 方法内嵌前置 `PermissionEngine.check()`.**

### 理由

- 工具分发是权限检查的唯一位置——所有工具调用都经过 `dispatch()`
- 中间件模式（FastAPI middleware）只能拦截 HTTP 层，Agent 内部工具调用绕不过
- 对标 Claude Code：权限检查在 tool execution 层，不在 HTTP 层
- 向后兼容：未配置 PermissionEngine 时跳过检查（`if self._permission:`）

---

## ADR-3：GoalJudge 注入 ReActAgent——构造函数 vs 循环内创建

### 决策

**构造函数注入，`execute_stream()` 每轮 turn 结束后自动调用。**

### 理由

- GoalJudge 需要 LLMClient——复用 ReActAgent 已有的 LLM 实例（避免重复连接）
- 用户可选——没有 goal 时跳过（GoalJudge 检查 `goal.description` 为空即 pass）
- 对标 MiMo Code：judge 在 `session/prompt.ts` 的 goal gate 中，不在 Agent 构造函数中

---

## ADR-4：Compose 接入 Scheduler——新 API 端点 vs 扩展现有端点

### 决策

**新增 `POST /api/v1/compose/run` 端点，内部调用 `ComposeOrchestrator.run_spec()`。**

### 理由

- Compose 输入是 spec YAML，与现有 `POST /api/v1/tasks`（单任务 PRD）格式不同
- 独立端点——职责清晰，不影响现有 task API
- Scheduler 注入 `compose_orchestrator` 实例，不耦合具体实现

---

## ADR-5：集成测试——pytest vs Playwright

### 决策

**pytest 集成测试（`tests/integration/`）。**

### 理由

- 集成测试目标是模块间通信正确性——Mock LLM + 真实 Agent + 真实 Tool
- Playwright 是 UI E2E——适合验证驾驶舱，不适合验证后端流水线
- 5 个场景覆盖关键链路：流式→编排→权限→Shell→覆盖率
- CI 门禁：`pytest tests/integration/` ≤2min

---

## ADR-6：工具层安全钩子——独立前置调用 vs 统一 dispatch 管线

### 决策

**三层分别在各自 tool 文件前置调用，不在 registry.dispatch() 统一包装。**

### 理由

- `PermissionEngine` ——挂载在 `registry.dispatch()` 入口，所有工具统一经过。对标 ADR-2。
- `BashValidators` ——只在 `shell.py` 的 `exec_command()` 内调用。因为只有 shell 需要命令白名单校验。
- `WorkspaceGuard` ——只在 `filesystem.py` 的 read/write/edit 内调用。因为只有文件操作需要路径守卫。

三者检查粒度不同——Permission 按角色/工具名（所有工具通用），Validators 按命令字符串（仅 shell），Guard 按文件路径（仅 filesystem）。强行统一包装会引入无意义参数。

### 调用顺序

```
registry.dispatch()
  → PermissionEngine.check(role, tool_name)  ← 所有工具
    → shell.exec_command()
      → BashValidators.validate(command)      ← 仅 shell
    → filesystem.write_file()
      → WorkspaceGuard.validate(path)         ← 仅文件操作
```
