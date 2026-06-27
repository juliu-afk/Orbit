# PRD：Phase 4——胶水集成 + 全链路贯通

> 日期: 2026-06-27 | 基于 Phase 1-3 已完成模块 | 收尾阶段

---

## 1. 背景

Phase 1-3 产生了 7 个新模块（stream/gateway-adapters/actors/goal_judge/compose/security/worktree），全部有独立单元测试 + 覆盖率≥80%。但它们之间没有连接——每个模块在真空中正确，合在一起不走通。

**目标**：把所有模块串成一条完整链路——SSE 端点→ReActAgent 流式→子Agent 并发→Goa​​l Judge 自检→Compose 编排→安全权限→Worktree 隔离。

---

## 2. 用户故事

### P0（胶水打通）

- **作为前端开发者**，我希望 `GET /api/v1/agent/{id}/stream` 能真正连接到 ReActAgent，看到实时文本流。
- **作为调度器**，我希望能通过 `ComposeOrchestrator` 接收 spec，自动拆任务分派子Agent 执行。
- **作为安全管理员**，我希望 Agent 调用工具时经过 PermissionEngine 校验，无权工具被拒绝。

### P1（自检闭环）

- **作为用户**，我希望 Agent 每轮 ReAct 循环结束时自动调用 GoalJudge，判断任务是否已完成，完成则停止。
- **作为 Compose 用户**，我希望编排任务时自动创建 Worktree 隔离工作区，完成后自动清理。

### P2（生产就绪）

- **作为运维**，我希望至少 3 个端到端场景能跑通：单Agent 编码、Compose 多Agent 编排、安全权限阻断验证。

---

## 3. 验收标准（拆 3 组）

### 组 A：路由 + 胶水 + 安全挂载（1.5天）

| # | 标准 |
|---|------|
| AC-A1 | `main.py` 注册 `stream/sse.py` 的 router，SSE 端点可访问 |
| AC-A2 | `main.py` 创建 `ActorSpawn` + `ComposeOrchestrator` 实例，注入到 `Scheduler` |
| AC-A3 | `main.py` 启动 `ActorWatchdog` 后台协程（zombie 清理） |
| AC-A4 | PermissionEngine 挂载到 `tools/registry.py` 的 `dispatch()` 前置钩子 |
| AC-A5 | `BashValidators.validate()` 挂载到 `tools/shell.py` 的 `exec_command()` 前置 |
| AC-A6 | `WorkspaceGuard.validate()` 挂载到 `tools/filesystem.py` 的 read/write/edit |
| AC-A7 | ComposeOrchestrator 可通过 `POST /api/v1/compose/run` 触发 |
| AC-A8 | `RoutingStrategy` 集成到 `LLMClient.generate()`——cheapest/fastest/best 生效 |

### 组 B：循环自检 + 编排联动 + Worktree（1.5天）

| # | 标准 |
|---|------|
| AC-B1 | ReActAgent 每轮 turn 结束后调用 GoalJudge.evaluate()，ok=true→停止 |
| AC-B2 | ComposeOrchestrator.run_spec() 接入 ActorSpawn，真实分派子Agent |
| AC-B3 | Compose 子Agent 失败时自动重试（self.MAX_RETRIES） |
| AC-B4 | Compose.run_spec() 在执行前自动创建 Worktree（策略=DELEGATE） |

### 组 C：集成测试（1天）

| # | 标准 |
|---|------|
| AC-C1 | 单Agent 流式执行 E2E：POST /run → SSE stream → FINISH_STEP |
| AC-C2 | Compose spec → 多Agent 执行 → review 门禁通过 |
| AC-C3 | 权限阻断：architect 调用 write_file → 拒绝 |
| AC-C4 | Shell 命令白名单：git status 通过，rm -rf / 拒绝 |
| AC-C5 | 全量覆盖率 ≥80% |

---

## 4. 影响范围

| 文件 | 改动 | 组 |
|------|------|:--:|
| `src/orbit/api/main.py` | 注册 SSE router + 创建 ActorSpawn/ComposeOrchestrator/Watchdog | A |
| `src/orbit/api/routes/compose.py` | **新增**——`POST /api/v1/compose/run` 端点 | A |
| `src/orbit/scheduler/orchestrator.py` | 注入 compose_orchestrator + actor_spawn | A |
| `src/orbit/tools/registry.py` | dispatch() 前置 PermissionEngine.check() 钩子 | A |
| `src/orbit/tools/shell.py` | exec_command() 前置 BashValidators.validate() | A |
| `src/orbit/tools/filesystem.py` | read/write/edit 前置 WorkspaceGuard.validate() | A |
| `src/orbit/agents/react_agent.py` | 每轮 turn 后调用 GoalJudge.evaluate() + 构造函数注入 | B |
| `src/orbit/compose/orchestrator.py` | run_spec() 接入 ActorSpawn + WorktreeManager | B |
| `src/orbit/stream/sse.py` | agent_stream 注入真实 LLM/tools（从 app.state） | A |
| `src/orbit/gateway/client.py` | 旧 `generate_stream()` 也应用 adapter 标准化 | A |
| `tests/integration/test_phase4_e2e.py` | **新增**——5 个集成测试 | C |

---

## 5. 边缘情况

| 场景 | 处理 |
|------|------|
| SSE stream 中途断连 | CancellationToken 取消 → Agent 下轮检测退出 |
| Compose spec 解析失败 | 返回 `{"status": "error"}` 不阻塞 API |
| GoalJudge LLM 超时 | fail-open——ok=true 不困住 Agent |
| PermissionEngine 拒绝工具 | 工具返回错误消息 → Agent 自行调整策略 |
| ActorSpawn 并发上限 | RuntimeError → Compose 重试队列 |

---

## 6. 分组交付

| 组 | 内容 | 时间 | PR |
|---|------|:--:|:--:|
| A | main.py路由+Permission+Shell+FS+Watchdog+Compose端点 (8AC) | 1.5天 | PR-4A |
| B | GoalJudge循环+Compose←ActorSpawn+Worktree (4AC) | 1.5天 | PR-4B |
| C | 集成测试5场景+覆盖率≥80% (5AC) | 1天 | PR-4C |

### 全覆盖验证矩阵

| Phase 3 模块 | 单元测试 | 集成挂载 | Phase 4 AC |
|-------------|:--:|:--:|:--:|
| stream/sse.py | ✅ | 🔲 main.py | A1 |
| stream/cancellation.py | ✅ | 🔲 SSE cancel endpoint | A1 |
| gateway/adapters/ | ✅ | ✅ client.py已集成 | A8 |
| gateway/routing.py | ✅ | 🔲 client.py RoutingStrategy | A8 |
| actors/registry.py | ✅ | 🔲 main.py + Compose | A2 |
| actors/spawn.py | ✅ | 🔲 Compose.run_spec() | B2 |
| actors/watchdog.py | ✅ | 🔲 main.py 后台协程 | A3 |
| goal_judge/judge.py | ✅ | 🔲 ReActAgent 构造注入 | B1 |
| compose/parser.py | ✅ | 🔲 /api/v1/compose/run | A7 |
| compose/orchestrator.py | ✅ | 🔲 ActorSpawn + Worktree | B2/B4 |
| security/guard.py | ✅ | 🔲 filesystem.py | A6 |
| security/validators.py | ✅ | 🔲 shell.py | A5 |
| security/permission.py | ✅ | 🔲 tools/registry.py | A4 |
| worktree/manager.py | ✅ | 🔲 Compose.run_spec() | B4 |
