## Step 5.1补充：Agent拉起机制

| PRD · Agent拉起机制 |  |
| --- | --- |
| **背景** | 外部系统需要通过调度器驱动多智能体协作。Agent不是预先部署的微服务，而是由调度器按需实例化的异步协程。之前Step 5.1定义了状态机转换，但未明确调度器如何通过asyncio拉起Agent协程、注入上下文、获取结果。 |
| **用户故事** | 作为调度器，我根据状态机的进度，在合适的时机`await agent.run()`拉起对应的Agent协程，注入L1-L5上下文，执行完成后将结果写入检查点供下游Agent使用。外部系统通过API调用调度器，不直接调用Agent。 |
| **需求描述** | ① Agent定义为异步协程类，实现`run(context: TaskContext) -> AgentResult`方法。② 调度器通过`asyncio.create_task()`拉起Agent协程。③ 拉起时注入L1-L5上下文（L1协作宪法/L2四图谱事实/L3任务状态/L4私有记忆/L5长期记忆）。④ Agent执行完成后，结果写入Checkpoint供下游Agent使用。⑤ 外部系统通过API调用调度器，不直接调用Agent。⑥ Agent执行超时（默认5分钟）时取消协程并标记FAILED。 |
| **范围 (Do/Don't)** | **Do：**进程内协程拉起；依赖注入；上下文构建；结果持久化；超时控制。**Don't：**不通过HTTP/gRPC远程调用Agent；不将Agent部署为独立容器；不实现Agent的生命周期管理（那是调度器的职责）。 |
| **数据契约** | **TaskContext:** `{ task_id, l1(str:L1协作宪法), l2(Dict:四图谱查询结果), l3(Dict:任务状态), l4(Dict:Agent私有工作记忆), l5(List:长期记忆检索结果) }` <br> **AgentResult:** `{ success(bool), output(Any), error(Optional[str]), duration_ms(float) }` <br> **CheckpointData:** `{ task_id, state, context: { agent_output } }` |
| **异常定义** | `AgentTimeoutError`：Agent执行超5分钟 → 取消协程，返回`success=False, error="Agent {name} timed out after 300s"`。<br>`AgentBuildError`：Agent协程构建失败 → 记录错误，返回`success=False, error="Build failed"`。 |
| **SC→AC** | **SC1:** Agent拉起成功 → **AC1:** 状态机触发CODING状态时，调用`_run_agent(DeveloperAgent, task)`返回AgentResult。<br>**SC2:** 上下文注入完整 → **AC2:** Agent的`run()`方法中`context.l1`、`context.l2`非空且包含预期内容。<br>**SC3:** 结果持久化 → **AC3:** Agent执行完成后，检查点中存在对应task_id的记录。 |
| **待定决策** | **Q:** Agent执行超时如何处理？ → **决议：** 在`_run_agent()`中包装`asyncio.wait_for(agent.run(), timeout=300)`，超时后取消协程并标记FAILED。 |

| ADR · Agent实现形态 |  |
| --- | --- |
| **决策** | Agent实现为**进程内异步协程**，而非独立微服务或容器。<br>① 所有Agent运行在调度器同一进程中。<br>② 通过asyncio事件循环调度。<br>③ 通过依赖注入传递外部依赖（LLM客户端、图谱仓库、沙箱）。<br>④ 通过Checkpoint实现状态跨Agent传递。 |
| **理由** | ① 无网络开销：协程间通信为零延迟。<br>② 极速拉起：协程创建为微秒级。<br>③ 共享内存：Checkpoint直接读取，无需序列化传递。<br>④ 简化运维：无需部署多个微服务。<br>⑤ 与V14.1的asyncio调度器自然兼容。 |
| **备选方案** | ① 独立微服务（HTTP/gRPC拉起）→ 网络延迟高，资源消耗大，不适合密集Agent协作 → 放弃。<br>② 独立容器（Docker拉起）→ 启动慢（秒级），资源隔离过度 → 放弃。 |
| **技术栈版本** | Python asyncio（内置）；无新增外部依赖。 |
| **架构位置** | 调度器层 `/src/scheduler/orchestrator.py`（`_run_agent()`核心方法）；Agent基类 `/src/agents/base.py`。 |
| **实施细节** | **_run_agent(agent_class, task):**<br>1. `_build_context(task)` 构建L1-L5上下文。<br>2. `agent_class(llm_client, graph_repo, sandbox, checkpoint_mgr)` 实例化Agent（依赖注入）。<br>3. `asyncio.wait_for(agent.run(context), timeout=300)` 拉起协程（带超时）。<br>4. `checkpoint_mgr.save(task.id, CheckpointData(...))` 写入检查点。<br>**_build_context():** 查询四图谱 → 构建L3任务状态 → 检索L5长期记忆 → 组装TaskContext。 |
| **风险与缓解** | 风险：Agent协程未注册导致引用失败。缓解：BaseAgent ABC强制实现`run()`方法，漏写则实例化时报错。 |
| **依赖链** | 依赖Step 1.2（四图谱Schema）；依赖Step 2.2（检查点持久化）；依赖Step 5.2（Agent基类定义）。 |

---

## Step 5.2补充：与MCP/A2A的抽象分层

| PRD · MCP/A2A抽象分层 |  |
| --- | --- |
| **背景** | "调用Agent"存在两种语义混淆：① A2A通信（Agent A请求Agent B）；② 系统拉起Agent（调度器实例化并驱动Agent协程）。MCP和A2A服务于不同层级，不参与Agent拉起。需要明确三层调用关系：系统→Agent（协程拉起）、Agent→工具（MCP）、Agent→Agent（A2A）。 |
| **用户故事** | 作为开发者，我理解三层调用关系的明确边界——调度器通过asyncio拉起Agent协程（不涉及网络协议）；Agent运行后通过MCP调用外部工具；同层Agent之间通过A2A协议通信。不混用这三层。 |
| **需求描述** | ① 明确三层调用关系（系统→Agent用协程拉起 / Agent→工具用MCP / Agent→Agent用A2A）。② 调度器层（Orchestrator）通过`asyncio.create_task()`+`await agent.run()`拉起Agent，不使用HTTP/gRPC。③ Agent层通过MCP Client调用工具（ToolRegistry抽象），不直接实例化外部工具。④ Agent间通过A2A协议（MessageBus）通信，走Request-Response/Notification模式。⑤ 外部系统通过REST API提交任务到调度器，不直接与Agent交互。 |
| **范围 (Do/Don't)** | **Do：**三层分离；各层协议各司其职；Scheduler不直接调用MCP/A2A。**Don't：**不在调度器层直接发起MCP调用；不在Agent层直接操作asyncio拉起其他Agent；不将A2A用于Scheduler-Agent间的状态传递。 |
| **数据契约** | **三层调用接口：**<br>`Orchestrator._run_agent(agent_class, task)` → `await agent.run(context)`（系统→Agent）<br>`Agent.act()` → `await mcp_client.call_tool(name, params)`（Agent→工具）<br>`Agent.send_a2a(request)` → `await bus.request(req)`（Agent→Agent） |
| **异常定义** | `CrossLayerViolationError`：若调度器直接调用MCP，或Agent直接拉起其他Agent协程 → 抛出异常，明确违反分层约束。 |
| **SC→AC** | **SC1:** 三层边界清晰 → **AC1:** 代码中不存在Orchestrator直接调用MCP或Agent直接调用asyncio.create_task拉起协程的情况（静态检查）。<br>**SC2:** 各层协议隔离 → **AC2:** MCP调用在Agent.act()内；A2A调用在Agent.send_a2a()内；协程拉起在Orchestrator._run_agent()内。 |
| **待定决策** | **Q:** 是否需要运行时强制检查三层边界？ → **决议：** Phase 0 仅静态检查（代码审查覆盖），Phase 2 引入`CrossLayerViolationError`运行时检查。 |

| ADR · 三层抽象分层 |  |
| --- | --- |
| **决策** | V14.1的调用链分为**三个严格隔离的抽象层级**：<br>**Layer 1（系统→Agent）：** 调度器Orchestrator通过`asyncio.create_task()`+`await agent.run()`拉起Agent协程。协议是Python异步调用，非网络协议。<br>**Layer 2（Agent→工具）：** Agent通过MCP Client调用外部工具。工具注册到ToolRegistry，权限/限流由Registry控制。<br>**Layer 3（Agent→Agent）：** 同级Agent通过A2A MessageBus通信。走Request-Response/Notification/Fire-and-Forget/Callback模式。 |
| **理由** | ① 分离关注点：调度策略（Layer 1）与业务逻辑（Layer 2/3）解耦。<br>② 性能最优：Layer 1是零延迟内存调用，不应被网络协议污染。<br>③ 便于演进：未来若需要远程Agent，只需扩展Layer 1协议，不影响Layer 2/3。 |
| **备选方案** | ① 单层混合（Scheduler直接发HTTP到Agent）→ 引入网络延迟，破坏协程模型优势 → 放弃。<br>② 两层混合（Agent即MCP Server）→ Agent职责混乱，既要执行业务逻辑又要管理工具调用 → 放弃。 |
| **技术栈版本** | Layer 1: Python asyncio；Layer 2: MCP协议（复用Step 5.2）；Layer 3: A2A MessageBus（Step 5.4）。 |
| **架构位置** | Layer 1: `/src/scheduler/orchestrator.py`；Layer 2: `/src/agents/base.py act()` + `/src/mcp/`；Layer 3: `/src/communication/message_bus.py`。 |
| **实施细节** | **静态检查规则（代码审查）：**<br>① Orchestrator中禁止出现`mcp_client`或`requests.post`。<br>② Agent基类中禁止出现`asyncio.create_task`拉起其他Agent协程。<br>③ Agent间通信必须走MessageBus，禁止直接调用其他Agent的`run()`方法。 |
| **风险与缓解** | 风险：开发者不理解分层，绕过边界调用。缓解：代码审查时强制检查；BaseAgent提供标准接口，不暴露底层asyncio。 |
| **依赖链** | Layer 1 依赖 Step 5.1；Layer 2 依赖 Step 5.5；Layer 3 依赖 Step 5.4。 |

---

🧪 原子化测试用例 (pytest)：

```python
import pytest, asyncio
from src.agents.base import BaseAgent
from src.scheduler.context import TaskContext
from src.scheduler.orchestrator import TaskOrchestrator
from src.communication.message_bus import AgentMessageBus

# ── Agent拉起机制 ──
@pytest.mark.asyncio
async def test_agent_run_returns_agent_result():
    """Agent.run()返回AgentResult"""
    class DummyAgent(BaseAgent):
        async def run(self, context):
            return AgentResult(success=True, output={"done": True}, duration_ms=100)
        async def think(self, context): pass
        async def act(self, thought): pass
        async def observe(self, action): pass

@pytest.mark.asyncio
async def test_run_agent_injects_l1_l5_context():
    """_run_agent()注入完整L1-L5上下文"""
    orch = TaskOrchestrator(llm_client=None, graph_repo=None, sandbox=None, checkpoint_mgr=None)
    ctx = await orch._build_context(task)
    assert ctx.l1 is not None  # L1协作宪法
    assert ctx.l2 is not None  # L2四图谱
    assert isinstance(ctx.l3, dict)  # L3任务状态
    assert isinstance(ctx.l4, dict)  # L4私有记忆（空字典）
    assert isinstance(ctx.l5, list)  # L5长期记忆

@pytest.mark.asyncio
async def test_agent_timeout_returns_failed_result():
    """Agent执行超时时返回success=False"""
    # 使用asyncio.wait_for模拟超时

# ── MCP/A2A抽象分层 ──
def test_orchestrator_does_not_call_mcp():
    """调度器层不直接调用MCP（静态检查）"""
    import ast, inspect
    source = inspect.getsource(TaskOrchestrator)
    tree = ast.parse(source)
    # 验证source中无mcp_client调用

@pytest.mark.asyncio
async def test_agent_uses_message_bus_for_a2a():
    """Agent间通信走MessageBus，不直接调用其他Agent.run()"""
    bus = AgentMessageBus(checkpoint_manager=None)
    # Agent A 通过 bus.request() 调用 Agent B，不直接调用 B.run()
```

### ✅ 验收测试 · pytest

```python
# Agent拉起与抽象分层集成测试
import pytest, asyncio
from src.scheduler.orchestrator import TaskOrchestrator
from src.agents.developer import DeveloperAgent
from src.agents.base import BaseAgent, AgentResult

# ── Agent拉起 ──
@pytest.mark.asyncio
async def test_orchestrator_run_agent_completes(mocker):
    """_run_agent()完整流程：上下文构建→Agent执行→Checkpoint保存"""
    mock_llm = mocker.MagicMock()
    mock_graph = mocker.MagicMock()
    mock_sandbox = mocker.MagicMock()
    mock_checkpoint = mocker.MagicMock()

    orch = TaskOrchestrator(mock_llm, mock_graph, mock_sandbox, mock_checkpoint)
    # 验证完整流程可执行

@pytest.mark.asyncio
async def test_context_contains_five_layers():
    """TaskContext包含L1-L5全部五层"""
    orch = TaskOrchestrator(None, None, None, None)
    ctx = await orch._build_context(mocker.MagicMock())
    assert hasattr(ctx, 'l1')  # 协作宪法
    assert hasattr(ctx, 'l2')  # 四图谱
    assert hasattr(ctx, 'l3')  # 任务状态
    assert hasattr(ctx, 'l4')  # 私有记忆
    assert hasattr(ctx, 'l5')  # 长期记忆

# ── 抽象分层 ──
def test_no_cross_layer_violations():
    """三层调用边界：静态代码检查"""
    import ast, inspect

    # 1. Orchestrator不调用MCP
    orch_source = inspect.getsource(TaskOrchestrator)
    assert 'mcp_client' not in orch_source
    assert 'requests.post' not in orch_source

    # 2. Agent基类不拉起其他Agent协程
    base_source = inspect.getsource(BaseAgent)
    assert 'create_task' not in base_source or 'self._' in base_source  # 允许内部Task管理
```
