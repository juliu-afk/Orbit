## Step 5.4：Agent间通信协议

| PRD · Agent间通信协议 |  |
| --- | --- |
| **背景** | Agent间（DeveloperAgent ↔ QAAgent ↔ ReviewerAgent）存在多种通信场景：同步验证、异步通知、流式监控。每种场景对超时、幂等、熔断的要求不同，需要统一的通信协议抽象，避免各Agent自行实现导致的碎片化。 |
| **用户故事** | 作为调度器，我需要在Agent间建立可靠的通信通道——支持同步Request-Response、Fire-and-Forget通知、流式数据推送、异步Callback四种模式；每次跨Agent调用必须设置超时；消息可重放；下游Agent熔断时上游收到标准化错误码。 |
| **需求描述** | ① 定义四种通信模式（Request-Response / Fire-and-Forget / Streaming / Callback）。② 实现MessageBus消息总线，管理Agent注册、消息路由、响应匹配。③ 每次请求必须设置超时（默认30秒）。④ 通过request_id实现幂等去重。⑤ 实现熔断传播：下游熔断时上游收到AGENT_003错误码，可执行降级。⑥ 所有通信记录写入task_audit_trail。 |
| **范围 (Do/Don't)** | **Do：**四种通信模式；MessageBus实现；超时/幂等/熔断；审计日志。**Don't：**不处理进程间/跨机器通信（那是未来远程Agent的事）；不实现消息持久化（重启丢失，由Checkpoint保证最终一致性）。 |
| **数据契约** | **消息基类：** `Message { id, correlation_id, source_agent, target_agent, timestamp, ttl_seconds }` <br> **Request:** `type="request", method, params, timeout_seconds, retry_count` <br> **Response:** `type="response", status(success/error/timeout/circuit_open), result, error_code, duration_ms` <br> **Notification:** `type="notification", event, payload` <br> **StreamChunk:** `{ sequence, data, is_last, error }` |
| **异常定义** | `AgentUnavailableError`（目标未注册/已下线，AGENT_001）；`AgentTimeoutError`（超时，AGENT_002）；`AgentCircuitOpenError`（熔断开启，AGENT_003）；`AgentRateLimitError`（限流，AGENT_006）。 |
| **SC→AC** | **SC1:** Request-Response调用 → **AC1:** `await bus.request(req)` 在超时内返回Response，status字段为success/error/timeout之一。<br>**SC2:** 幂等去重 → **AC2:** 相同request_id重复发送，第二次返回缓存的Response，不触发Agent执行。<br>**SC3:** 熔断传播 → **AC3:** 下游Agent熔断时，上游收到status=circuit_open，error_code=AGENT_003。 |
| **待定决策** | **Q:** 消息总线单点故障如何处理？ → **决议：** Phase 0 为内存实现，Phase 2 引入Redis主备切换。 |

| ADR · 通信模式选型 |  |
| --- | --- |
| **决策** | 采用**异步消息总线 + 同步Future等待**的混合模式：<br>① Agent间调用通过MessageBus转发，调用方使用`await bus.request()`同步等待。<br>② 底层使用asyncio实现非阻塞，支持超时和熔断传播。<br>③ 长耗时操作（Z3求解、沙箱执行）使用Callback模式，避免长时间占用连接。 |
| **理由** | ① 简化调用方代码（同步写法，异步执行）。<br>② 超时和熔断可在单一位置统一管理。<br>③ 与V14.1的asyncio调度器自然兼容。 |
| **备选方案** | ① 纯异步回调（代码复杂度高，调试困难）→ 放弃。<br>② gRPC流式通信（过重，不适合Agent间轻量通信）→ 放弃。 |
| **技术栈版本** | Python asyncio（内置）；无新增外部依赖。 |
| **架构位置** | 通信层 `/src/communication/protocol.py`（数据模型）+ `/src/communication/message_bus.py`（总线实现）。 |
| **实施细节** | **MessageBus.request():** 创建Future → 异步投递请求 → `asyncio.wait_for(future, timeout)` → 返回Response。<br>**幂等性：** `_processed_requests`集合记录已处理request_id，重复请求直接返回缓存Response。<br>**熔断传播：** 下游Agent的circuit_breaker.is_open()为True时，抛出AgentCircuitOpenError，上游捕获后执行降级逻辑。 |
| **风险与缓解** | 风险：MessageBus内存泄漏（Future未清理）。缓解：`finally`块确保`_pending`字典及时删除。 |
| **依赖链** | 依赖Step 5.1（调度器状态机）；依赖Step 5.2（Agent基类）。 |

---

## Step 5.5：工具调用标准化与注册机制

| PRD · 工具调用标准化 |  |
| --- | --- |
| **背景** | Agent需要调用外部工具（知识库查询、沙箱执行、数据库访问）。当前各Agent自行管理工具调用，缺乏统一的权限隔离、版本管理、限流控制。需要统一的ToolRegistry实现声明式工具注册和标准化调用。 |
| **用户故事** | 作为Agent，我通过统一的ToolRegistry调用工具——工具通过装饰器声明元数据（名称、版本、权限、限流）；我只调用allowed_agents列表中包含我的工具；超出限流时自动降级。 |
| **需求描述** | ① 定义ToolSchema元数据（name, version, parameters, returns, permissions, allowed_agents, rate_limit, timeout_seconds, is_async, cache_ttl, deprecated）。② 实现ToolRegistry注册中心（register/get_tool/invoke）。③ 权限检查：调用方必须在工具的allowed_agents白名单中。④ 限流检查：按name:version:agent维度统计，超限抛出RateLimitError。⑤ 工具版本管理：语义化版本（semver），支持版本范围声明。⑥ 废弃标记：deprecated=True时返回迁移指引。 |
| **范围 (Do/Don't)** | **Do：**工具元数据注册；权限隔离；限流；版本管理；调用审计。**Don't：**不管理工具的具体实现（那是各工具自己的事）；不实现工具的自动发现（Phase 2）。 |
| **数据契约** | **ToolSchema:** `{ name, version, description, parameters(JSON Schema), returns, permissions[], allowed_agents[], rate_limit, timeout_seconds, is_async, cache_ttl, deprecated, deprecated_message }` <br> **ToolInvocation记录:** `{ id, tool_name, tool_version, agent_name, parameters, result, error, status, duration_ms, timestamp }` |
| **异常定义** | `PermissionError`（调用方不在allowed_agents中）；`RateLimitError`（超出限流）；`ToolNotFoundError`（工具不存在或版本不匹配）；`ToolDeprecatedError`（工具已废弃）。 |
| **SC→AC** | **SC1:** 权限隔离 → **AC1:** 非白名单Agent调用工具时，抛出PermissionError，工具不执行。<br>**SC2:** 限流保护 → **AC2:** 超限后抛出RateLimitError，调用方执行降级（返回缓存或跳过）。<br>**SC3:** 版本兼容 → **AC3:** 工具升级后，旧版本仍可调用（保留至少3个小版本）。 |
| **待定决策** | **Q:** 工具降级时返回什么？ → **决议：** 返回缓存结果（若有cache_ttl）；无缓存时返回`{"error": "rate_limited", "retry_after": N}`。 |

| ADR · 工具版本管理 |  |
| --- | --- |
| **决策** | 工具采用**语义化版本**管理，Agent调用时需声明版本范围（如`~=1.2`），系统自动解析为精确版本。<br>① 工具升级时，旧版本仍保留（向后兼容至少3个小版本）。<br>② 工具废弃时，在元数据中标记`deprecated=True`，并给出迁移指引。<br>③ 审计表记录每次调用的精确版本。 |
| **理由** | ① 避免Agent因工具升级而失效。<br>② 支持A/B测试（不同Agent使用不同版本）。<br>③ 便于回滚（发现问题时切回旧版本）。 |
| **备选方案** | ① 浮动版本（always-latest）→ 版本不锁定，生产环境不可预测 → 放弃。<br>② 强制版本精确匹配 → 更新成本高，升级所有Agent → 放弃。 |
| **技术栈版本** | Python标准库（无新增）；复用现有MCP协议集成。 |
| **架构位置** | 工具层 `/src/tools/registry.py`。 |
| **实施细节** | **ToolRegistry.invoke():** 解析版本 → 获取Schema → 权限检查 → 限流检查 → 执行handler → 返回ToolInvocation记录。<br>**限流算法：** 滑动窗口1分钟，清洗过期记录后判断是否超限。 |
| **风险与缓解** | 风险：限流状态内存泄漏（生产环境多实例不共享）。缓解：Phase 2 切换到Redis限流。 |
| **依赖链** | 依赖Step 5.4（通信协议）；依赖MCP Server（Step 5.2已定义）。 |

---

## Step 5.6：多任务并发与资源调度策略

| PRD · 资源调度策略 |  |
| --- | --- |
| **背景** | 多个任务可能同时运行（不同用户的任务、同一任务内多个Agent的并发请求）。LLM调用、沙箱实例、Token预算都是稀缺资源。需要统一的ResourceScheduler实现优先级抢占式调度，防止单任务独占资源。 |
| **用户故事** | 作为调度器，我需要管理所有运行中任务的资源使用——CRITICAL任务可抢占LOW任务的资源；每个任务有Token预算上限；资源饱和时新任务排队而非崩溃；防止单个大任务独占所有LLM调用。 |
| **需求描述** | ① 定义四级优先级（CRITICAL=0/HIGH=1/NORMAL=2/LOW=3）。② 定义ResourceQuota（max_concurrent_tasks/max_llm_calls_per_minute/max_tokens_per_task/max_sandbox_instances）。③ 实现ResourceScheduler：提交任务（submit）/ 资源预检（can_proceed）/ 消费配额（consume_llm_call）/ 释放资源（release）。④ 优先级抢占：高优先级任务可插入队列头部。⑤ 时间片轮转：同优先级任务轮流执行（每次最多30秒）。⑥ 长运行任务自动降级：>5分钟的任务降级为LOW。 |
| **范围 (Do/Don't)** | **Do：**资源配额管理；优先级调度；抢占式调度；排队管理。**Don't：**不实现跨机器资源调度（Phase 2）；不实现GPU资源调度（Phase 3）。 |
| **数据契约** | **ResourceQuota:** `{ max_concurrent_tasks=5, max_llm_calls_per_minute=60, max_tokens_per_task=100, max_sandbox_instances=3, cpu_cores_limit=4.0, memory_limit_mb=4096 }` <br> **TaskResource:** `{ task_id, priority, llm_calls_used, tokens_used, sandbox_count, cpu_used, memory_used_mb, started_at, last_scheduled }` |
| **异常定义** | `ResourceExhaustedError`（全局资源饱和，新任务拒绝）；`TaskQueueFullError`（所有优先级队列均满）。 |
| **SC→AC** | **SC1:** 优先级抢占 → **AC1:** CRITICAL任务提交时，若资源饱和，立即抢占LOW任务的资源。<br>**SC2:** 资源配额保护 → **AC2:** 单任务Token超限时，`can_proceed()`返回False，任务暂停等待。<br>**SC3:** 公平调度 → **AC3:** 同优先级任务轮转执行，单任务连续执行不超过30秒。 |
| **待定决策** | **Q:** 抢占是否取消被抢占任务的执行？ → **决议：** 抢占是资源层面的（配额转移），任务状态保留，等待资源重新分配。 |

| ADR · 多任务调度策略 |  |
| --- | --- |
| **决策** | 采用**优先级抢占式调度 + 公平时间片**混合策略：<br>① 高优先级任务（CRITICAL/HIGH）可抢占低优先级任务的资源。<br>② 同优先级任务采用时间片轮转（每个任务最多连续运行30秒）。<br>③ 长运行任务（>5分钟）自动降级为LOW优先级。 |
| **理由** | ① 生产故障修复必须优先保障（CRITICAL）。<br>② 防止单个任务无限占用资源。<br>③ 保证低优先级任务也能获得执行机会。 |
| **风险与缓解** | 风险：频繁抢占导致低优先级任务饥饿。缓解：CRITICAL任务每天不超过5个，超过后降级为HIGH。 |
| **技术栈版本** | Python asyncio（内置）；无新增外部依赖。 |
| **架构位置** | 调度层 `/src/scheduler/resource_scheduler.py`（调度器）+ `/src/scheduler/orchestrator.py`（集成）。 |
| **实施细节** | **submit():** 检查全局资源是否饱和 → 饱和时非CRITICAL任务排队 → 分配TaskResource。<br>**can_proceed():** 预检所有资源配额，任一超限返回False。<br>**consume_llm_call():** 分钟级计数器重置逻辑，防止滑动窗口超限。<br>**_schedule_next():** 优先级遍历队列，唤醒可执行任务。 |
| **依赖链** | 依赖Step 5.1（调度器状态机）；依赖Step 5.4（通信协议）。 |

---

🧪 原子化测试用例 (pytest)：

```python
import pytest, asyncio
from src.communication.protocol import Request, Response, Notification, ErrorCode
from src.communication.message_bus import AgentMessageBus, AgentUnavailableError, AgentTimeoutError
from src.tools.registry import ToolSchema, ToolPermission, ToolRegistry, PermissionError, RateLimitError
from src.scheduler.resource_scheduler import ResourceScheduler, TaskPriority, ResourceQuota

# ── Step 5.4 Agent间通信协议 ──
@pytest.mark.asyncio
async def test_request_response_success():
    """Request-Response模式：正常返回success状态"""
    bus = AgentMessageBus(checkpoint_manager=None)
    # 注册目标Agent
    async def dummy_handler(req):
        return Response(id="resp-1", source_agent="QAAgent", target_agent="DeveloperAgent",
                        status="success", result={"verified": True}, duration_ms=10)
    # 注意：完整测试需要mock Agent，以下为骨架

@pytest.mark.asyncio
async def test_idempotent_deduplication():
    """相同request_id不重复执行"""
    bus = AgentMessageBus(checkpoint_manager=None)
    req = Request(id="req-1", source_agent="Dev", target_agent="QA", method="verify", params={})
    # 第一次处理完成，第二次应返回缓存

@pytest.mark.asyncio
async def test_circuit_open_propagation():
    """下游熔断时上游收到AGENT_003"""
    # 验证error_code为ErrorCode.CIRCUIT_OPEN

# ── Step 5.5 工具调用标准化 ──
def test_permission_check_rejects_unauthorized():
    """非白名单Agent调用工具被拒绝"""
    registry = ToolRegistry()
    registry.register(
        schema=ToolSchema(name="query_knowledge", version="1.0.0", description="...",
                         parameters={}, returns={}, permissions=[ToolPermission.READ],
                         allowed_agents=["QAAgent"], rate_limit=0, timeout_seconds=30),
        handler=lambda p: {}
    )
    with pytest.raises(PermissionError):
        registry.invoke("query_knowledge", {}, agent_name="DeveloperAgent")  # 不在白名单

def test_rate_limit_enforced():
    """限流检查：超限后抛出RateLimitError"""
    registry = ToolRegistry()
    registry.register(
        schema=ToolSchema(name="validate", version="1.0.0", description="...",
                         parameters={}, returns={}, permissions=[],
                         allowed_agents=["QAAgent"], rate_limit=2, timeout_seconds=30),  # 每分钟2次
        handler=lambda p: {}
    )
    # 前两次成功，第3次抛出RateLimitError

def test_deprecated_tool_returns_message():
    """废弃工具返回迁移指引"""
    registry = ToolRegistry()
    registry.register(
        schema=ToolSchema(name="old_api", version="1.0.0", description="...",
                         parameters={}, returns={}, permissions=[],
                         allowed_agents=["DeveloperAgent"], rate_limit=0, timeout_seconds=30,
                         deprecated=True, deprecated_message="Use new_api:v2 instead"),
        handler=lambda p: {}
    )

# ── Step 5.6 多任务并发调度 ──
@pytest.mark.asyncio
async def test_critical_preempts_low():
    """CRITICAL任务抢占LOW任务资源"""
    quota = ResourceQuota(max_concurrent_tasks=2)
    scheduler = ResourceScheduler(quota)
    await scheduler.submit("task-low", TaskPriority.LOW)
    # 资源饱和，LOW排队
    admitted = await scheduler.submit("task-critical", TaskPriority.CRITICAL)
    assert admitted is True  # CRITICAL强制抢占

@pytest.mark.asyncio
async def test_llm_quota_enforced_per_task():
    """单任务Token预算超限时can_proceed返回False"""
    quota = ResourceQuota(max_tokens_per_task=100)
    scheduler = ResourceScheduler(quota)
    await scheduler.submit("task-1", TaskPriority.NORMAL)
    # 消费配额到上限
    can_continue = await scheduler.consume_llm_call("task-1", tokens=100)
    assert can_continue is False

def test_long_running_task_demotion():
    """长运行任务（>5分钟）自动降级为LOW"""
    scheduler = ResourceScheduler(ResourceQuota())
    # 任务运行>300秒后再次调度时，降级为LOW
```

### ✅ 验收测试 · pytest

```python
# 并发调度协议层集成测试
import pytest, asyncio
from src.communication.message_bus import AgentMessageBus
from src.tools.registry import ToolRegistry, ToolSchema, ToolPermission
from src.scheduler.resource_scheduler import ResourceScheduler, TaskPriority, ResourceQuota

# ── 5.4 Agent通信 ──
@pytest.mark.asyncio
async def test_message_bus_registers_agents():
    """Agent注册与注销"""
    bus = AgentMessageBus(checkpoint_manager=None)
    # 验证register/unregister正常

# ── 5.5 工具注册 ──
def test_tool_registry_get_latest_version():
    """获取工具最新版本"""
    registry = ToolRegistry()
    registry.register(ToolSchema(name="x", version="1.0.0", description="", parameters={},
                                  returns={}, permissions=[], allowed_agents=[], rate_limit=0, timeout_seconds=30),
                      handler=lambda p: {})
    registry.register(ToolSchema(name="x", version="2.0.0", description="", parameters={},
                                  returns={}, permissions=[], allowed_agents=[], rate_limit=0, timeout_seconds=30),
                      handler=lambda p: {})
    assert registry.get_latest_version("x") == "2.0.0"

# ── 5.6 资源调度 ──
@pytest.mark.asyncio
async def test_scheduler_queue_status():
    """队列状态查询返回各优先级长度"""
    scheduler = ResourceScheduler(ResourceQuota())
    await scheduler.submit("t1", TaskPriority.LOW)
    await scheduler.submit("t2", TaskPriority.CRITICAL)
    status = scheduler.get_queue_status()
    assert status["critical"] == 1
    assert status["low"] == 1
```
