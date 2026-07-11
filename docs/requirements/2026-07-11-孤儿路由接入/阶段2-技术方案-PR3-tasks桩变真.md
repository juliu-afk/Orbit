# PR3 技术设计：tasks 桩变真——HTTP 端点接真实调度器

> 日期：2026-07-11
> 性质：**核心调度模块改动**，实现时必须走 `/ce-code-review`
> 调研来源：Scheduler/TaskRunner/CheckpointManager/chat.py 源码精读

## 一、问题

`tasks.py` HTTP 端点是 mock（进程内 `_mock_store`），POST 从不调度、GET/cancel 只读写 dict。真实调度器 `Scheduler`（`scheduler/orchestrator.py`）完整实现但和 HTTP 端点脱节——只有 chat.py 直接调 `_scheduler.run_task`。用户要真数据。

## 二、关键调研结论（file:line）

| 项 | 结论 |
|----|------|
| Scheduler 实例 | 模块级 `_scheduler`（`api/main.py:291-299`），未挂 app.state。**建议加 `app.state.scheduler = _scheduler`**（main.py:556 附近），路由用 `request.app.state.scheduler` |
| run_task | `Scheduler.run_task(task_id, prd)`（`orchestrator.py:108`）async，**阻塞至任务终态**。task_id 由调用方生成（`generate_task_id()` orchestrator.py:180）。chat.py 用 `asyncio.create_task(...)` 包成后台任务（chat.py:421） |
| 状态读取 | **无内存 dict**。唯一持久化=`CheckpointManager.load(task_id)`（`checkpoint/manager.py:113`）→ CheckpointData{task_id,state,progress,context,updated_at}。**checkpoint 只在状态转换时写**（runner.py:190） |
| 缺失字段 | session_id/project_name/created_at **不在 checkpoint**——需单独存储或塞进 `context` dict |
| 取消 | **无 cancel(task_id) 方法**。Scheduler 不追踪 asyncio.Task。现只有 CancelledError 传播（不写 CANCELLED checkpoint） |
| 双重执行风险 | chat.py `_create_task`(写mock) + 显式 `run_task`。若 create_task 也调度→双跑。**create_task 必须保持 record-only** |

## 三、会破坏的现有测试

- `tests/unit/test_task_api.py::test_create_task`（:68）断言 `state=="IDLE"`——若 POST 改为调度会变 PARSING
- `tests/e2e/test_e2e_normal.py::test_e2e_api_task_create_and_query`（:37）同上
- 404/409/边界测试（cancel/not_found/prd_boundary）只要保留契约即通过

## 四、分阶段实现（每阶段独立可交付）

### 阶段 3a — 取消机制（核心，最高价值）
1. Scheduler 加 `self._active_tasks: dict[str, asyncio.Task] = {}`
2. 加 `spawn_task(task_id, prd) -> asyncio.Task`：`create_task(run_task)` 存入 registry，完成回调清理
3. 加 `cancel_task(task_id)`：查 registry → `.cancel()` → 写 CANCELLED checkpoint（用 checkpoint version 乐观锁防竞态）
4. `POST /tasks/{id}/cancel` 调 `request.app.state.scheduler.cancel_task(id)`
5. chat.py 的 `asyncio.create_task(run_task)` 改用 `scheduler.spawn_task`
6. 前端 Dashboard DAG 节点加"取消"按钮 → POST cancel
7. main.py 加 `app.state.scheduler = _scheduler`

### 阶段 3b — GET 读真实状态
1. `get_task` 从 `scheduler.checkpoint.load(task_id)` 读 state/progress
2. session_id/project_name/created_at 存 `_task_records` 轻量 dict（或 checkpoint context）
3. 合并返回 TaskStatusResponse；checkpoint 无则 404

### 阶段 3c — POST 真实调度（最高风险）
1. create_task record-only（不调度），保留 IDLE 返回契约 OR 新增 `POST /tasks/{id}/run` 显式触发
2. 更新 test_task_api / test_e2e_normal 期望
3. chat.py 协调，确保无双跑

## 五、必须保留的契约
- TaskCreateRequest 校验（prd 10-5000、language 枚举、session_id 格式）
- UUID task_id 格式（31 hex 无连字符）
- 404 体 `{detail:{error_code:TASK_NOT_FOUND}}`、409 终态不可取消

## 六、风险
1. 长 LLM 调用（CODING 超时 180s）→ GET 返回 CODING+0.6，刷新慢
2. 取消竞态——任务自然完成同时写 CANCELLED，靠 checkpoint version 乐观锁
3. chat.py 依赖 tasks.create_task，改签名要同步

## 七、建议
阶段 3a（取消）先做——最高价值、最可测、契约影响小。3c（POST 调度）风险最高，单独审查。全程 `/ce-code-review`（触核心调度）。
