## Step 5.1：自研调度器核心（状态机+DAG+检查点集成）

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | MVP状态机仅支持串行单一路径，无法表达复杂软件开发任务（如并行代码生成与验证）。需扩展为支持DAG（有向无环图）的任务编排引擎，并深度集成检查点（Step 2.2）实现崩溃恢复，同时引入异步执行提升吞吐。 |
| **用户故事** | 作为调度器，我接收一个`TaskGraph`（节点为Agent执行单元，边为依赖），按拓扑序并发执行无依赖节点，在状态变化时自动保存检查点。若进程崩溃，重启后从最新检查点恢复整个DAG进度。 |
| **需求描述** | ①扩展`TaskState`枚举，增加`PENDING, RUNNING, SUCCESS, FAILED, SKIPPED`；②定义`TaskGraph`类（节点列表+边列表），提供拓扑排序（Kahn算法）；③实现`TaskOrchestrator`，包含`async run(graph)`方法，使用`asyncio.gather`并发执行无依赖节点；④每个节点执行前后调用`CheckpointManager.save()`，保存完整DAG进度（节点状态、中间产物）；⑤实现恢复逻辑：`resume(task_id)`从检查点加载，跳过已完成节点；⑥支持节点超时（可配置，默认30s）和重试（最多2次）。 |
| **范围 (Do/Don't)** | **Do：**支持DAG并行执行，检查点自动保存与恢复，节点超时与重试。**Don't：**不支持动态图（运行时修改拓扑），不支持跨任务依赖（V2）。 |
| **数据契约** | ``代码块-1`` |
| **异常定义** | ``代码块-2`` |
| **成功标准→验收** | **SC1:**拓扑排序正确 →**AC1:**构建DAG（A→B, A→C, B→D, C→D），调度器执行顺序满足依赖（B/C在A后，D在B/C后）。 |
| | **SC2:**并发执行 →**AC2:**两个无依赖节点同时启动，时间差<100ms。 |
| | **SC3:**检查点恢复 →**AC3:**模拟进程崩溃，重启后调用`resume`，已完成的节点不重复执行。 |
| | **SC4:**超时与重试 →**AC4:**节点执行超过30s触发超时，自动重试1次；若再失败则节点状态为FAILED，不影响其他节点。 |
| **待定决策** | **Q1:**节点间数据传递如何实现？ →**决议：**通过`GraphNode.output`写入，后续节点通过`node.input`引用（显式依赖注入）。 |
| | **Q2:**检查点保存频率？ →**决议：**每个节点完成时保存，避免频繁IO；同时每10个节点保存一次（用于长DAG）。 |
| | **Q3:**失败策略：继续还是终止？ →**决议：**默认为“快速失败”（任一节点失败则整个DAG标记FAILED），但可配置为“继续”（用于非关键路径）。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **技术栈版本** | Python 3.11, asyncio (内置), networkx 3.2 (用于拓扑排序和循环检测, 可选), CheckpointManager (Step 2.2), 各Agent实现 (Step 5.2)。 |
| | 位置：`/src/scheduler/orchestrator.py`,`/src/scheduler/graph.py`。 |
| **架构位置** | 调度层核心，负责解析TaskGraph、编排执行、保存检查点。被API层（Step 1.1）调用，调用LLMClient（Step 2.1）、沙箱（MVP-03）、防幻觉（Step 4.1/4.2）、图谱（Step 3.x）。 |
| **实施细节** | **拓扑排序与并发执行：** |
| | ``代码块-3`` |
| **风险与缓解** | 风险1：并发节点过多导致资源耗尽（如同时启动5个LLM调用）。缓解：设置信号量（Semaphore）控制最大并发数（配置`MAX_CONCURRENT_NODES=3`）。 |
| | 风险2：检查点序列化大DAG可能较慢。缓解：仅保存节点状态和关键元数据，不保存大对象（如完整代码），使用`orjson`加速。 |
| | 风险3：节点重试可能引发无限循环。缓解：最大重试2次，超过则标记FAILED。 |
| **需求错位** | 若将来需要支持动态DAG（如条件分支），当前静态拓扑排序无法满足。但当前需求明确为静态图，V2可扩展。 |
| **技术约束** | 必须使用异步（asyncio）实现并发，禁止使用`threading`（避免GIL争用）。节点间数据传递必须通过`GraphNode`对象，不得使用全局变量。 |
| **环境配置** | MAX_CONCURRENT_NODES=3 |
| | NODE_TIMEOUT_SECONDS=30 |
| | MAX_RETRIES_PER_NODE=2 |
| | CHECKPOINT_SAVE_INTERVAL_NODES=10 |
| **依赖链** | TaskOrchestrator → CheckpointManager → AgentFactory → 各具体Agent实现 → LLMClient / Sandbox / 图谱 / 防幻觉。 |

🧪 原子化测试用例 (pytest)：
import pytest
 from src.scheduler.orchestrator import TaskOrchestrator, TaskGraph, GraphNode, NodeStatus

 @pytest.mark.asyncio
 async def test_topological_sort():
 graph = TaskGraph(
 task_id="test",
 nodes=[
 GraphNode(id="A", agent_role="developer"),
 GraphNode(id="B", agent_role="developer"),
 GraphNode(id="C", agent_role="developer"),
 GraphNode(id="D", agent_role="developer"),
 ],
 edges=[("A","B"), ("A","C"), ("B","D"), ("C","D")]
 )
 orch = TaskOrchestrator(MockCheckpointManager())
 order = orch._topological_sort(graph)
 # A必须在B,C之前；B,C在D之前
 assert order.index("A") < order.index("B")
 assert order.index("A") < order.index("C")
 assert order.index("B") < order.index("D")
 assert order.index("C") < order.index("D")

 @pytest.mark.asyncio
 async def test_concurrent_execution():
 # Mock Agent，模拟延迟
 class MockAgent:
 async def execute(self, input):
 await asyncio.sleep(0.1)
 return {"result": "ok"}
 with patch("src.scheduler.orchestrator.AgentFactory.get_agent", return_value=MockAgent()):
 graph = TaskGraph(
 task_id="test2",
 nodes=[
 GraphNode(id="A", agent_role="dev"),
 GraphNode(id="B", agent_role="dev"),
 ],
 edges=[]
 )
 orch = TaskOrchestrator(MockCheckpointManager())
 start = time.time()
 await orch.run(graph)
 elapsed = time.time() - start
 assert elapsed < 0.15 # 并行执行，应接近0.1s

 @pytest.mark.asyncio
 async def test_checkpoint_resume():
 # 模拟崩溃恢复：保存检查点，然后重新加载
 graph = TaskGraph(...)
 orch = TaskOrchestrator(checkpoint_mgr)
 # 执行部分节点后模拟崩溃
 # 然后恢复，检查已完成节点不重复执行
 # (具体实现依赖Mock)
 pass



## Step 5.2：5个Agent角色定义与Prompt工程

| PRD |  |
| --- | --- |
| **背景** | 多Agent协作的核心是职责分离。参考V14.1架构，定义5个核心Agent角色：架构师（系统设计）、开发者（代码实现）、代码审查员（质量检查）、QA验证员（测试与验证）、配置管理员（环境配置）。每个Agent具有独立的System Prompt、输入输出Schema、工具集（可调用图谱、LLM、沙箱等）。 |
| **用户故事** | 作为调度器，我根据`agent_role`实例化对应的Agent，传入`input`字典，获得结构化输出（Pydantic模型），无需关心内部Prompt细节。 |
| **需求描述** | ①定义`AgentRole`枚举（ARCHITECT, DEVELOPER, REVIEWER, QA, CONFIG_MANAGER）；②为每个角色编写System Prompt（使用Jinja2模板，注入上下文，总长度<2K tokens）；③定义每个Agent的输入/输出Pydantic模型（如`DeveloperInput`,`DeveloperOutput`）；④实现`AgentFactory`，根据角色返回具体Agent实例；⑤每个Agent可调用工具（如`call_llm`,`query_graph`,`run_sandbox`），通过依赖注入传入；⑥Agent执行结果必须通过Pydantic校验，非法输出抛出`AgentOutputError`。 |
| **范围 (Do/Don't)** | **Do：**5个角色全覆盖，Prompt模板使用Jinja2，输入输出强类型校验。**Don't：**不支持工具调用链（Agent间内部调用），不支持记忆（对话历史由调度器管理，Agent无状态）。 |
| **数据契约** | ``代码块-4`` |
| **异常定义** | ``代码块-5`` |
| **成功标准→验收** | **SC1:**每个Agent Prompt Token<2K →**AC1:**使用`tiktoken`计算各Prompt总token数。 |
| | **SC2:**输出符合Pydantic模型 →**AC2:**对每个Agent进行单元测试，传入有效输入，输出校验通过。 |
| | **SC3:**开发者Agent生成可执行代码 →**AC3:**输入“设计一个求和函数”，输出代码在沙箱中运行成功。 |
| | **SC4:**架构师Agent输出结构化设计 →**AC4:**输入PRD，输出包含组件列表和数据流描述，非空。 |
| **待定决策** | **Q1:**Prompt模板是否支持多语言？ →**决议：**仅英文（确保LLM理解准确），输出代码可指定语言。 |
| | **Q2:**Agent之间如何传递复杂对象（如代码AST）？ →**决议：**通过`output`/`input`传递JSON可序列化数据，调度器负责转换。 |
| | **Q3:**是否使用Few-shot示例？ →**决议：**在Prompt中包含1-2个示例（developer和qa角色），其余角色Zero-shot。 |

| ADR |  |
| --- | --- |
| **技术栈版本** | Jinja2 3.1.2, Pydantic 2.6, tiktoken 0.6 (用于token计数), 各依赖组件（LLMClient, GraphRepository, Sandbox等）。 |
| | 位置：`/src/agents/`，包含`base.py`,`factory.py`,`architect.py`,`developer.py`,`reviewer.py`,`qa.py`,`config_manager.py`，以及`prompts/`目录下的Jinja2模板。 |
| **架构位置** | 能力层（Agent实现），被TaskOrchestrator（Step 5.1）调用。每个Agent可组合调用LLM、图谱、沙箱等底层能力。 |
| **实施细节** | **基类与工厂：** |
| | ``代码块-6`` |
| | **开发者Agent实现示例：** |
| | ``代码块-7`` |
| | **Prompt模板 (developer.jinja2)：** |
| | ``代码块-8`` |
| **风险与缓解** | 风险1: LLM输出非JSON导致解析失败。缓解：在System Prompt中强制要求输出JSON，并设置`response_format={"type": "json_object"}`（若模型支持）。 |
| | 风险2: Prompt过长导致Token超限。缓解：使用`tiktoken`在渲染后检查，若>2K则截断输入上下文（如code_context）。 |
| | 风险3: Agent间数据不兼容（如Developer输出code但Reviewer期望不同字段）。缓解：通过Pydantic模型严格定义接口，调度器负责适配。 |
| **需求错位** | 若需添加新Agent（如“测试生成器”），需扩展枚举和工厂。当前设计支持灵活扩展。 |
| **技术约束** | 所有Agent必须无状态（不存储会话历史），状态由调度器管理；Agent内部调用LLM必须异步；输出必须JSON可序列化。 |
| **环境配置** | AGENT_PROMPT_DIR=./src/agents/prompts |
| | AGENT_MAX_OUTPUT_TOKENS=4096 |
| | AGENT_FEW_SHOT_ENABLED=true # 开启few-shot示例 |
| **依赖链** | AgentFactory → BaseAgent → 各子类 → LLMClient / GraphRepository / Sandbox → 基础设施。 |

🧪 原子化测试用例 (pytest)：
import pytest
 from src.agents.factory import AgentFactory
 from src.agents.developer import DeveloperAgent, DeveloperInput, DeveloperOutput

 @pytest.mark.asyncio
 async def test_developer_agent_output_schema():
 agent = AgentFactory.get_agent("developer", mock_llm, mock_graph, mock_sandbox)
 # Mock LLM返回有效的JSON
 mock_llm.generate.return_value.content = '{"code": "def add(a,b): return a+b", "language": "python", "dependencies": []}'
 result = await agent.execute({"design": "sum function", "code_context": ""})
 assert "code" in result
 assert result["language"] == "python"

 def test_developer_input_validation():
 # 有效输入
 input_data = {"design": "test", "code_context": ""}
 dev = DeveloperAgent(mock_llm)
 validated = dev._validate_input(input_data)
 assert isinstance(validated, DeveloperInput)

 # 无效输入（缺少必填字段）
 with pytest.raises(ValidationError):
 dev._validate_input({"code_context": ""}) # missing 'design'

 @pytest.mark.asyncio
 async def test_agent_prompt_token_count():
 agent = AgentFactory.get_agent("architect", mock_llm, mock_graph, mock_sandbox)
 prompt = agent.prompt_template.render(prd="Write a system for ...", tech_stack=["Python"], constraints=[])
 tokens = tiktoken.encoding_for_model("gpt-4").encode(prompt)
 assert len(tokens) < 2048 # 确保<2K

 @pytest.mark.asyncio
 async def test_agent_factory_returns_correct_type():
 for role in AgentRole:
 agent = AgentFactory.get_agent(role.value, mock_llm, mock_graph, mock_sandbox)
 assert agent.role == role


**✅ 阶段5 (Step 5.1 & 5.2) 全量交付确认**

本报告完整交付了调度器与Agent协作层的全部规格：

- **Step 5.1**：自研调度器（DAG并行执行、检查点集成、超时与重试），从MVP串行升级为生产级编排引擎。
- **Step 5.2**：5个Agent角色（架构师/开发者/审查员/QA/配置管理员）及其Prompt、输入输出契约、工厂模式实现。

两个步骤紧密配合：调度器通过`AgentFactory`实例化Agent，执行DAG节点，并在每个节点完成时保存检查点。开发人员可并行开发各Agent和调度器核心，通过接口契约解耦。



```
// 代码块-1
from pydantic import BaseModel, Field
    from typing import List, Optional, Dict, Any
    from enum import Enum
    from datetime import datetime

    class NodeStatus(str, Enum):
        PENDING = "pending"
        RUNNING = "running"
        SUCCESS = "success"
        FAILED = "failed"
        SKIPPED = "skipped"

    class GraphNode(BaseModel):
        id: str
        agent_role: str  # 对应Step 5.2的Agent角色
        input: Dict[str, Any]  # 输入数据
        output: Optional[Dict[str, Any]] = None
        status: NodeStatus = NodeStatus.PENDING
        retry_count: int = 0
        max_retries: int = 2
        started_at: Optional[datetime] = None
        finished_at: Optional[datetime] = None
        error: Optional[str] = None

    class TaskGraph(BaseModel):
        task_id: str
        nodes: List[GraphNode]
        edges: List[tuple[str, str]]  # (from_node_id, to_node_id)
        status: str = "pending"  # pending, running, completed, failed

    class OrchestratorSnapshot(BaseModel):
        task_id: str
        graph: TaskGraph
        current_node_ids: List[str]  # 正在运行的节点
        completed_node_ids: List[str]
        updated_at: datetime
```


```
// 代码块-2
class OrchestratorError(Exception):
        pass

    class NodeExecutionError(OrchestratorError):
        def __init__(self, node_id: str, error: str):
            self.node_id = node_id
            super().__init__(f"Node {node_id} failed: {error}")

    class GraphCycleError(OrchestratorError):
        def __init__(self):
            super().__init__("Graph contains cycle")

    class GraphResumeError(OrchestratorError):
        def __init__(self, task_id: str):
            super().__init__(f"Cannot resume task {task_id}: checkpoint not found")
```


```
// 代码块-3
import asyncio
    from collections import deque

    class TaskOrchestrator:
        def __init__(self, checkpoint_manager: CheckpointManager):
            self.checkpoint_mgr = checkpoint_manager
            self._running_tasks = {}

        async def run(self, graph: TaskGraph) -> TaskGraph:
            # 1. 拓扑排序
            order = self._topological_sort(graph)
            # 2. 执行
            pending = set(order)
            running = set()
            completed = set()
            # 使用队列管理就绪节点
            ready_queue = deque([n for n in order if self._is_ready(n, completed)])
            while ready_queue or running:
                # 启动就绪节点
                while ready_queue:
                    node_id = ready_queue.popleft()
                    if node_id in completed or node_id in running:
                        continue
                    running.add(node_id)
                    task = asyncio.create_task(self._execute_node(graph, node_id))
                    self._running_tasks[node_id] = task
                # 等待任一完成
                if running:
                    done, _ = await asyncio.wait(
                        [self._running_tasks[n] for n in running],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        node_id = task.get_name()  # 需在创建时set_name
                        running.remove(node_id)
                        completed.add(node_id)
                        # 更新就绪队列
                        for n in order:
                            if n not in completed and n not in running and self._is_ready(n, completed):
                                ready_queue.append(n)
                    # 保存检查点
                    await self.checkpoint_mgr.save(graph.task_id, self._snapshot(graph))
            return graph

        def _topological_sort(self, graph: TaskGraph) -> List[str]:
            # 使用Kahn算法，检测循环
            in_degree = {n.id: 0 for n in graph.nodes}
            for src, tgt in graph.edges:
                in_degree[tgt] += 1
            queue = deque([n.id for n in graph.nodes if in_degree[n.id] == 0])
            result = []
            while queue:
                node = queue.popleft()
                result.append(node)
                for src, tgt in graph.edges:
                    if src == node:
                        in_degree[tgt] -= 1
                        if in_degree[tgt] == 0:
                            queue.append(tgt)
            if len(result) != len(graph.nodes):
                raise GraphCycleError()
            return result

        def _is_ready(self, node_id: str, completed: set) -> bool:
            # 所有前驱节点都已完成
            for src, tgt in graph.edges:
                if tgt == node_id and src not in completed:
                    return False
            return True

        async def _execute_node(self, graph: TaskGraph, node_id: str):
            node = next(n for n in graph.nodes if n.id == node_id)
            node.status = NodeStatus.RUNNING
            node.started_at = datetime.utcnow()
            try:
                # 根据agent_role调用对应的Agent
                agent = AgentFactory.get_agent(node.agent_role)
                result = await agent.execute(node.input)
                node.output = result
                node.status = NodeStatus.SUCCESS
            except Exception as e:
                node.error = str(e)
                if node.retry_count < node.max_retries:
                    node.retry_count += 1
                    node.status = NodeStatus.PENDING  # 重新调度
                    # 重新入队（由上层调度）
                else:
                    node.status = NodeStatus.FAILED
                    raise NodeExecutionError(node_id, str(e))
            node.finished_at = datetime.utcnow()
            # 保存检查点
            await self.checkpoint_mgr.save(graph.task_id, self._snapshot(graph))

        def _snapshot(self, graph: TaskGraph) -> OrchestratorSnapshot:
            return OrchestratorSnapshot(
                task_id=graph.task_id,
                graph=graph,
                current_node_ids=[n.id for n in graph.nodes if n.status == NodeStatus.RUNNING],
                completed_node_ids=[n.id for n in graph.nodes if n.status == NodeStatus.SUCCESS],
                updated_at=datetime.utcnow()
            )
```


```
// 代码块-4
from pydantic import BaseModel, Field
    from typing import List, Optional, Dict, Any
    from enum import Enum

    class AgentRole(str, Enum):
        ARCHITECT = "architect"
        DEVELOPER = "developer"
        REVIEWER = "reviewer"
        QA = "qa"
        CONFIG_MANAGER = "config_manager"

    # 各角色输入/输出示例
    class ArchitectInput(BaseModel):
        prd: str
        tech_stack: Optional[List[str]] = None
        constraints: Optional[List[str]] = None

    class ArchitectOutput(BaseModel):
        architecture_design: str  # 架构描述文本
        components: List[str]     # 组件列表
        data_flow: str            # 数据流描述

    class DeveloperInput(BaseModel):
        design: str               # 来自Architect的架构设计
        code_context: Optional[str] = None  # 已有代码片段

    class DeveloperOutput(BaseModel):
        code: str
        language: str = "python"
        dependencies: List[str] = Field(default_factory=list)

    class ReviewerInput(BaseModel):
        code: str
        standards: Optional[List[str]] = None

    class ReviewerOutput(BaseModel):
        passed: bool
        comments: List[str]
        severity: str  # "critical", "warning", "info"

    class QAInput(BaseModel):
        code: str
        test_cases: Optional[List[Dict]] = None

    class QAOutput(BaseModel):
        tests_passed: bool
        test_report: str
        coverage: Optional[float] = None

    class ConfigManagerInput(BaseModel):
        env_type: str  # "dev", "test", "prod"
        desired_changes: Optional[Dict[str, str]] = None

    class ConfigManagerOutput(BaseModel):
        config_files_updated: List[str]
        drift_detected: bool
```


```
// 代码块-5
class AgentError(Exception):
        pass

    class AgentOutputError(AgentError):
        def __init__(self, role: str, errors: List[str]):
            self.role = role
            self.errors = errors
            super().__init__(f"Agent {role} output validation failed: {', '.join(errors)}")

    class AgentExecutionError(AgentError):
        def __init__(self, role: str, error: str):
            self.role = role
            super().__init__(f"Agent {role} execution failed: {error}")
```


```
// 代码块-6
from abc import ABC, abstractmethod
    from typing import Any, Dict
    from src.llm.client import LLMClient
    from src.graph.repository import GraphRepository

    class BaseAgent(ABC):
        def __init__(self, llm_client: LLMClient, graph_repo: Optional[GraphRepository] = None, sandbox: Optional[DockerSandbox] = None):
            self.llm = llm_client
            self.graph = graph_repo
            self.sandbox = sandbox
            self.prompt_template = self._load_prompt()

        @abstractmethod
        def _load_prompt(self) -> str:
            pass

        @abstractmethod
        def _validate_input(self, input_data: Dict) -> Any:
            pass

        @abstractmethod
        def _validate_output(self, output_data: Dict) -> Any:
            pass

        async def execute(self, input_data: Dict) -> Dict:
            # 1. 校验输入
            validated_input = self._validate_input(input_data)
            # 2. 渲染Prompt
            prompt = self.prompt_template.render(**validated_input.dict())
            # 3. 调用LLM
            response = await self.llm.generate(prompt=prompt, system_prompt=self.system_prompt)
            # 4. 解析输出（假设LLM返回JSON）
            try:
                parsed = json.loads(response.content)
            except json.JSONDecodeError:
                raise AgentOutputError(self.role, ["LLM response not valid JSON"])
            # 5. 校验输出
            validated_output = self._validate_output(parsed)
            return validated_output.dict()
```


```
// 代码块-7
class DeveloperAgent(BaseAgent):
        role = AgentRole.DEVELOPER
        system_prompt = "You are a senior software engineer. Generate clean, well-documented Python code."

        def _load_prompt(self):
            env = Environment(loader=FileSystemLoader("src/agents/prompts"))
            return env.get_template("developer.jinja2")

        def _validate_input(self, data):
            return DeveloperInput(**data)

        def _validate_output(self, data):
            return DeveloperOutput(**data)
```


```
// 代码块-8
Design: {{ design }}
    Code context: {{ code_context }}
    Please generate Python code that implements the design. Return JSON with fields: code, language, dependencies.
```


# 多Agent自循环系统 · 阶段6 前端与集成测试 (Step 6.1 & 6.2) · 编码就绪级PRD/ADR

Vue3 实时驾驶舱 ｜ E2E 测试与质量门禁

**交付声明：**本报告为阶段6（W11-W12）的终极细化文档。Step 6.1实现可视化驾驶舱（任务拓扑、Token流速、熵曲线），Step 6.2建立端到端测试体系（含性能基准与混沌实验）。两个Step与已交付的所有后端组件（调度器、LLM客户端、图谱引擎、防幻觉体系）无缝集成，确保系统可观测、可验证。



## Step 5.3：动态任务分片与降级

| PRD (产品需求文档) |  | 
| --- | --- | 
| **背景** | 当单个任务规模超过LLM上下文窗口或Token预算上限时（如大仓库重构、超长代码生成），系统需自动将大任务拆分为可管理的子任务，并按预算约束降级执行策略。 | 
| **用户故事** | 作为调度器，当我检测到任务规模超出阈值时，自动触发任务分片，将大任务切分为多个小任务队列，并按降级策略执行（减少模型、简化验证）。 | 
| **需求描述** | ①实现任务规模评估（Token计数 + AST节点数）；②定义分片策略（按文件、按模块、按函数层级）；③实现降级执行链（满血→降级→极限降级→拒绝）；④在调度器（Step 5.1）中集成触发逻辑。 | 
| **范围 (Do/Don't)** | **Do：**Token/行数双维度评估，自动分片，降级执行链，调度器集成。**Don't：**不支持跨语言分片（V2），不支持动态重分片（运行中调整）。 | 
| **数据契约** | 输入：`TaskScaleInput = {token_count: int, ast_nodes: int, complexity: float}`；输出：`ShardPlan = {shards: list[Shard], strategy: str, budget_tier: str}`。 | 
| **异常定义** | `ScaleExceedsLimitError`：任务规模超出系统处理能力；`ShardFailedError`：某个分片执行失败。 | 
| **成功标准→验收** | **SC1:**分片触发 →**AC1:**输入5000 Token任务，检测到超阈值，自动触发分片，输出2个以上分片。 | 
| | **SC2:**降级执行 →**AC2:**预算耗尽时自动降级（gpt-4→gpt-4o-mini），验证降级前后结果一致性80%以上。 | 
| | **SC3:**分片并行 →**AC3:**分片之间无依赖时并行调度，总时间小于串行时间的60%。 | 
| **待定决策** | **Q1:**分片大小以什么为单位？ →**决议：**以Token数为首选单位（行数为辅助），因为LLM有明确Token限制。 | 

| ADR (架构决策记录) |  | 
| --- | --- | 
| **技术栈版本** | Python 3.11, tiktoken 0.6, ast (内置), asyncio。 | 
| | 位置：`/src/scheduler/scaler.py`（任务规模评估）、`/src/scheduler/sharding.py`（分片策略）、`/src/scheduler/degradation.py`（降级链）。 | 
| **架构位置** | 调度层（Step 5.1）上游，接收任务后判断是否需要分片/降级，决定是否进入调度器。 | 
| **实施细节** | **任务规模评估：** | 
| | ```python | 
| | class TaskScaler: | 
| |     def __init__(self, token_limit: int = 128000, node_limit: int = 5000): | 
| |         self.token_limit = token_limit | 
| |         self.node_limit = node_limit | 
| |     def evaluate(self, task_input: dict) -> tuple: | 
| |         tokens = self._count_tokens(task_input) | 
| |         ast_nodes = self._count_ast_nodes(task_input) | 
| |         needs_sharding = tokens > self.token_limit | 
| |         needs_degradation = tokens > self.token_limit * 0.8 | 
| |         if not needs_sharding: | 
| |             return ShardPlan(shards=[Shard(id=0, input=task_input)], strategy="none"), needs_degradation | 
| |         shards = self._create_shards(task_input) | 
| |         budget_tier = self._compute_budget_tier(tokens) | 
| |         return ShardPlan(shards=shards, strategy="file_boundary", budget_tier=budget_tier), needs_degradation | 
| | ``` | 
| | **降级执行链：** | 
| | ```python | 
| | class DegradationChain: | 
| |     TIERS = [ | 
| |         ("gpt-4o", 1.0, 0.8),   # model, cost_factor, quality_threshold | 
| |         ("gpt-4o-mini", 0.3, 0.75), | 
| |         ("gpt-3.5-turbo", 0.1, 0.65), | 
| |     ] | 
| |     def __init__(self, budget_pct: float): | 
| |         self.budget_pct = budget_pct | 
| |     def get_tier(self) -> str: | 
| |         for model, cost_factor, quality in self.TIERS: | 
| |             if self.budget_pct >= cost_factor * 100: | 
| |                 return model | 
| |         return "reject" | 
| | ``` | 
| | **分片调度集成：** | 
| | 在TaskOrchestrator（Step 5.1）的submit方法中，判断是否需要分片；若需要，将多个Shard作为独立TaskGraph节点提交。 | 
| **风险与缓解** | 风险1：分片后函数/类被切断（跨文件引用）。缓解：按文件边界分片，函数级分片仅用于无导入场景。 | 
| | 风险2：降级后质量不可接受。缓解：质量阈值低于0.65时拒绝执行，而非继续降级。 | 
| **需求错位** | 若任务规模远超系统能力（如百万行代码库），当前分片策略可能产生数百个分片。V2可考虑增量分片。 | 
| **技术约束** | 分片操作必须在调度器外部完成；降级决策由`DegradationChain`统一管理。 | 
| **环境配置** | TASK_SCALE_TOKEN_LIMIT=128000 | 
| | TASK_SCALE_NODE_LIMIT=5000 | 
| | DEGRADATION_BUDGET_PCT=100 | 
| | MAX_SHARDS_PER_TASK=50 | 
| **依赖链** | TaskScaler → DegradationChain → TaskOrchestrator → AgentFactory。 | 

| 🧪 原子化测试用例 (pytest)： | 
| ```python | 
| import pytest | 
| from src.scheduler.scaler import TaskScaler, ScaleExceedsLimitError | 
| from src.scheduler.degradation import DegradationChain | 
| 
| def test_task_scaler_under_limit(): | 
|     scaler = TaskScaler(token_limit=1000) | 
|     plan, needs_deg = scaler.evaluate({"text": "short task"}) | 
|     assert len(plan.shards) == 1 | 
|     assert plan.strategy == "none" | 
|     assert not needs_deg | 
| 
| def test_task_scaler_triggers_sharding(): | 
|     scaler = TaskScaler(token_limit=100) | 
|     plan, needs_deg = scaler.evaluate({"text": "x" * 500}) | 
|     assert len(plan.shards) > 1 | 
|     assert plan.strategy == "file_boundary" | 
| 
| def test_degradation_chain_full_budget(): | 
|     chain = DegradationChain(budget_pct=100) | 
|     assert chain.get_tier() == "gpt-4o" | 
| 
| def test_degradation_chain_low_budget(): | 
|     chain = DegradationChain(budget_pct=20) | 
|     assert chain.get_tier() == "gpt-3.5-turbo" | 
| 
| def test_degradation_chain_reject(): | 
|     chain = DegradationChain(budget_pct=5) | 
|     assert chain.get_tier() == "reject" | 
| ```

## Step 5.4：Agent间通信协议与契约
### 1.1 设计原则
- 异步优先：Agent间调用以异步消息为主，避免同步阻塞导致调度器卡死。
- 超时必设：每次跨Agent调用必须设置超时，默认30秒，可配置。
- 幂等性保障：消息可重放，下游必须支持幂等处理（通过request_id去重）。
- 熔断传播：下游Agent熔断时，上游Agent收到标准化错误码，可执行降级策略。
- 审计完备：所有通信记录写入task_audit_trail，支持全链路追踪。
### 1.2 通信模式
| 模式 | 说明 | 适用场景 |
| --- | --- | --- |
| Request-Response | Agent A发送请求，阻塞等待Agent B返回结果 | DeveloperAgent → QAAgent（验证代码） |
| Fire-and-Forget | Agent A发送消息，不等待响应 | 审计日志记录、指标上报 |
| Streaming | Agent B分块返回结果 | L3熵监控（流式Token分析） |
| Callback | Agent A提供回调URL，Agent B完成后异步通知 | 长时间运行的验证任务（Z3求解、沙箱执行） |
### 1.3 数据契约
```
# /src/communication/protocol.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Literal
from datetime import datetime
from uuid import uuid4
# === 消息基类 ===
class Message(BaseModel):
id: str = Field(default_factory=lambda: str(uuid4()))
correlation_id: Optional[str] = None  # 用于Request-Response配对
source_agent: str  # DeveloperAgent / QAAgent / ReviewerAgent
target_agent: str
timestamp: datetime = Field(default_factory=datetime.utcnow)
ttl_seconds: int = 30  # 消息有效期
# === Request-Response ===
class Request(Message):
type: Literal["request"] = "request"
method: str  # verify_code, execute_sandbox, query_graph
params: Dict[str, Any]
timeout_seconds: int = 30
retry_count: int = 0
max_retries: int = 2
class Response(Message):
type: Literal["response"] = "response"
status: Literal["success", "error", "timeout", "circuit_open"]
result: Optional[Any] = None
error_code: Optional[str] = None
error_message: Optional[str] = None
duration_ms: float
# === Fire-and-Forget ===
class Notification(Message):
type: Literal["notification"] = "notification"
event: str  # checkpoint_saved, token_consumed, entropy_triggered
payload: Dict[str, Any]
# === Streaming ===
class StreamChunk(BaseModel):
sequence: int
data: Any
is_last: bool = False
error: Optional[str] = None
# === 标准错误码 ===
class ErrorCode:
TARGET_UNAVAILABLE = "AGENT_001"      # 目标Agent不可用
TIMEOUT = "AGENT_002"                 # 超时
CIRCUIT_OPEN = "AGENT_003"            # 目标熔断
INVALID_REQUEST = "AGENT_004"         # 请求参数错误
INTERNAL_ERROR = "AGENT_005"          # 目标内部错误
RATE_LIMITED = "AGENT_006"            # 限流
```
### 1.4 异常定义
```
class AgentCommunicationError(Exception):
"""通信层基类异常"""
pass
class AgentUnavailableError(AgentCommunicationError):
"""目标Agent不可用（未注册/已下线）"""
def __init__(self, agent_name: str):
self.agent_name = agent_name
super().__init__(f"Agent '{agent_name}' is not available")
class AgentTimeoutError(AgentCommunicationError):
"""请求超时"""
def __init__(self, agent_name: str, timeout_seconds: int):
self.agent_name = agent_name
self.timeout_seconds = timeout_seconds
super().__init__(f"Request to '{agent_name}' timed out after {timeout_seconds}s")
class AgentCircuitOpenError(AgentCommunicationError):
"""目标Agent熔断器开启"""
def __init__(self, agent_name: str):
self.agent_name = agent_name
super().__init__(f"Circuit breaker for '{agent_name}' is open")
class AgentRateLimitError(AgentCommunicationError):
"""目标Agent限流"""
def __init__(self, agent_name: str, retry_after: int):
self.agent_name = agent_name
self.retry_after = retry_after
super().__init__(f"Rate limited by '{agent_name}', retry after {retry_after}s")
```
### 1.5 通信层实现
```
# /src/communication/message_bus.py
import asyncio
from typing import Dict, Optional, List
from src.communication.protocol import Request, Response, Notification
class AgentMessageBus:
"""Agent间异步消息总线"""
def __init__(self, checkpoint_manager):
self._agents: Dict[str, 'Agent'] = {}  # 注册的Agent
self._pending: Dict[str, asyncio.Future] = {}  # 等待响应的请求
self._checkpoint = checkpoint_manager
def register(self, agent_name: str, agent_instance: 'Agent'):
"""注册Agent到消息总线"""
self._agents[agent_name] = agent_instance
def unregister(self, agent_name: str):
if agent_name in self._agents:
del self._agents[agent_name]
async def request(self, request: Request) -> Response:
"""发送同步请求，等待响应"""
# 检查目标Agent是否可用
if request.target_agent not in self._agents:
raise AgentUnavailableError(request.target_agent)
# 检查目标Agent熔断器状态
if self._agents[request.target_agent].circuit_breaker.is_open():
raise AgentCircuitOpenError(request.target_agent)
# 创建Future等待响应
future = asyncio.Future()
self._pending[request.id] = future
try:
# 异步转发请求
asyncio.create_task(
self._deliver(request)
)
# 等待响应（带超时）
response = await asyncio.wait_for(
future,
timeout=request.timeout_seconds
)
return response
except asyncio.TimeoutError:
self._pending.pop(request.id, None)
raise AgentTimeoutError(request.target_agent, request.timeout_seconds)
finally:
self._pending.pop(request.id, None)
async def _deliver(self, request: Request):
"""实际投递请求到目标Agent"""
try:
target = self._agents[request.target_agent]
response = await target.handle_request(request)
# 记录通信审计
await self._checkpoint.record_communication(request, response)
# 唤醒等待的Future
if request.id in self._pending:
self._pending[request.id].set_result(response)
except Exception as e:
# 异常情况：返回错误响应
error_response = Response(
id=str(uuid4()),
correlation_id=request.id,
source_agent=request.target_agent,
target_agent=request.source_agent,
status="error",
error_code=ErrorCode.INTERNAL_ERROR,
error_message=str(e),
duration_ms=0
)
if request.id in self._pending:
self._pending[request.id].set_result(error_response)
def notify(self, notification: Notification):
"""发送单向通知（Fire-and-Forget）"""
asyncio.create_task(self._deliver_notification(notification))
async def _deliver_notification(self, notification: Notification):
if notification.target_agent in self._agents:
target = self._agents[notification.target_agent]
await target.handle_notification(notification)
def get_agent_status(self, agent_name: str) -> Dict:
"""查询Agent状态"""
if agent_name not in self._agents:
return {"status": "unavailable"}
return self._agents[agent_name].get_status()
# === 幂等性去重 ===
_processed_requests: set = set()
async def is_duplicate(self, request_id: str) -> bool:
"""检查请求是否已处理（幂等性保障）"""
if request_id in self._processed_requests:
return True
self._processed_requests.add(request_id)
# 定期清理（生产环境用Redis TTL）
return False
```
### 1.6 ADR：通信模式选型
| ADR · Agent间通信模式 |
| --- |
| 决策 | 采用异步消息总线 + 同步Future等待的混合模式：
① Agent间调用通过MessageBus转发，调用方使用await bus.request()同步等待。
② 底层使用asyncio实现非阻塞，支持超时和熔断传播。
③ 长耗时操作（Z3、沙箱）使用Callback模式，避免长时间占用连接。 |
| 理由 | ① 简化调用方代码（同步写法，异步执行）。② 超时和熔断可在单一位置统一管理。③ 与V14.1的asyncio调度器自然兼容。 |
| 备选方案 | ① 纯异步回调（代码复杂度高，调试困难）→ 放弃。② gRPC流式通信（过重，不适合Agent间轻量通信）→ 放弃。 |



## Step 5.5：工具调用标准化与注册机制
### 2.1 设计原则
- 声明式注册：工具通过装饰器或配置文件声明，支持动态加载。
- 权限隔离：每个工具定义allowed_agents，只有授权Agent可调用。
- 版本兼容：工具支持语义化版本，Agent调用时指定版本范围。
- 可观测性：每次工具调用记录到审计表（含入参、出参、耗时）。
- 优雅降级：工具不可用时，系统自动降级（如返回缓存结果或跳过）。
### 2.2 工具注册与元数据
```
# /src/tools/registry.py
from pydantic import BaseModel, Field
from typing import Callable, List, Dict, Any, Optional
from enum import Enum
from datetime import datetime
class ToolPermission(str, Enum):
READ = "read"
WRITE = "write"
ADMIN = "admin"
class ToolSchema(BaseModel):
"""工具元数据定义"""
name: str
version: str  # 语义化版本，如 "1.2.3"
description: str
parameters: Dict[str, Any]  # JSON Schema格式
returns: Dict[str, Any]  # 返回格式
permissions: List[ToolPermission]
allowed_agents: List[str]  # 白名单
rate_limit: int = 0  # 每分钟调用上限，0表示不限
timeout_seconds: int = 30
is_async: bool = True
cache_ttl: Optional[int] = None  # 缓存TTL（秒）
deprecated: bool = False
deprecated_message: Optional[str] = None
class ToolInvocation(BaseModel):
"""工具调用记录"""
id: str
tool_name: str
tool_version: str
agent_name: str
parameters: Dict[str, Any]
result: Optional[Any] = None
error: Optional[str] = None
status: Literal["pending", "success", "error", "timeout"]
duration_ms: float
timestamp: datetime = Field(default_factory=datetime.utcnow)
```
### 2.3 工具注册中心
```
# /src/tools/registry.py (续)
import asyncio
from typing import Dict, Optional, List
from collections import defaultdict
import time
class ToolRegistry:
"""工具注册中心 - 管理所有工具的生命周期"""
def __init__(self):
self._tools: Dict[str, Dict[str, ToolSchema]] = {}  # name -> version -> schema
self._handlers: Dict[str, Dict[str, Callable]] = {}  # name -> version -> handler
self._rate_limiter: Dict[str, Dict[str, List[float]]] = defaultdict(dict)
def register(
self,
schema: ToolSchema,
handler: Callable
) -> None:
"""注册工具"""
if schema.name not in self._tools:
self._tools[schema.name] = {}
self._handlers[schema.name] = {}
self._tools[schema.name][schema.version] = schema
self._handlers[schema.name][schema.version] = handler
def get_tool(self, name: str, version: str) -> Optional[ToolSchema]:
"""获取工具元数据"""
if name in self._tools and version in self._tools[name]:
return self._tools[name][version]
return None
def get_latest_version(self, name: str) -> Optional[str]:
"""获取最新版本"""
if name in self._tools:
return max(self._tools[name].keys())
return None
async def invoke(
self,
name: str,
params: Dict[str, Any],
agent_name: str,
version: Optional[str] = None
) -> ToolInvocation:
"""调用工具"""
# 1. 解析版本（默认最新）
if not version:
version = self.get_latest_version(name)
if not version:
raise ValueError(f"Tool '{name}' not found")
# 2. 获取工具定义
schema = self.get_tool(name, version)
if not schema:
raise ValueError(f"Tool '{name}:{version}' not found")
# 3. 权限检查
if agent_name not in schema.allowed_agents:
raise PermissionError(f"Agent '{agent_name}' not allowed to call '{name}'")
# 4. 限流检查
if schema.rate_limit > 0:
if not self._check_rate_limit(name, version, agent_name, schema.rate_limit):
raise RateLimitError(f"Rate limit exceeded for '{name}'")
# 5. 执行工具
start_time = time.time()
try:
handler = self._handlers[name][version]
if schema.is_async:
result = await handler(params)
else:
result = handler(params)
status = "success"
error = None
except asyncio.TimeoutError:
status = "timeout"
result = None
error = f"Tool '{name}' timed out after {schema.timeout_seconds}s"
except Exception as e:
status = "error"
result = None
error = str(e)
duration_ms = (time.time() - start_time) * 1000
# 6. 返回调用记录
return ToolInvocation(
id=str(uuid4()),
tool_name=name,
tool_version=version,
agent_name=agent_name,
parameters=params,
result=result,
error=error,
status=status,
duration_ms=duration_ms
)
def _check_rate_limit(self, name: str, version: str, agent: str, limit: int) -> bool:
"""检查限流"""
key = f"{name}:{version}:{agent}"
now = time.time()
if key not in self._rate_limiter:
self._rate_limiter[key] = []
# 过滤1分钟内的记录
self._rate_limiter[key] = [
t for t in self._rate_limiter[key] if now - t = limit:
return False
self._rate_limiter[key].append(now)
return True
def is_deprecated(self, name: str, version: str) -> bool:
"""检查工具是否已废弃"""
schema = self.get_tool(name, version)
return schema.deprecated if schema else False
def get_deprecation_message(self, name: str, version: str) -> Optional[str]:
schema = self.get_tool(name, version)
return schema.deprecated_message if schema else None
```
### 2.4 工具声明示例
```
# /src/tools/declarations.py
from src.tools.registry import ToolSchema, ToolPermission, ToolRegistry
# 在系统启动时注册工具
registry = ToolRegistry()
# 注册 "query_knowledge" 工具
registry.register(
schema=ToolSchema(
name="query_knowledge",
version="2.0.0",
description="查询领域知识图谱",
parameters={
"type": "object",
"properties": {
"domain": {"type": "string", "enum": ["accounting", "finance", "law"]},
"concept": {"type": "string"},
"mode": {"type": "string", "enum": ["exact", "semantic"]}
},
"required": ["domain", "concept"]
},
returns={"type": "object", "properties": {"nodes": "array"}},
permissions=[ToolPermission.READ],
allowed_agents=["DeveloperAgent", "QAAgent", "ReviewerAgent"],
rate_limit=100,
timeout_seconds=10,
is_async=True,
cache_ttl=300  # 5分钟缓存
),
handler=query_knowledge_handler
)
# 注册 "validate_compliance" 工具（敏感操作）
registry.register(
schema=ToolSchema(
name="validate_compliance",
version="1.0.0",
description="验证代码是否符合法规",
parameters={...},
permissions=[ToolPermission.READ, ToolPermission.WRITE],
allowed_agents=["QAAgent"],  # 仅QA可调用
rate_limit=10,  # 每分钟仅10次
timeout_seconds=60,
is_async=True
),
handler=validate_compliance_handler
)
```
### 2.5 ADR：工具调用的版本管理
| ADR · 工具版本管理 |
| --- |
| 决策 | 工具采用语义化版本管理，Agent调用时需声明版本范围（如~=1.2），系统自动解析为精确版本。
① 工具升级时，旧版本仍保留（向后兼容至少3个小版本）。
② 工具废弃时，在元数据中标记deprecated=True，并给出迁移指引。
③ 审计表记录每次调用的精确版本。 |
| 理由 | ① 避免Agent因工具升级而失效。② 支持A/B测试（不同Agent使用不同版本）。③ 便于回滚（发现问题时切回旧版本）。 |



## Step 5.6：多任务并发与资源调度策略
### 3.1 设计原则
- 优先级分层：任务分为CRITICAL/HIGH/NORMAL/LOW四级，高优先级抢占资源。
- 资源配额：按任务/团队/全局三级设置资源配额（LLM调用、沙箱实例、Token预算）。
- 公平调度：防止单个大任务独占资源，引入时间片轮转。
- 背压控制：资源不足时，新任务排队或拒绝，而非崩溃。
### 3.2 任务优先级与资源配额
```
# /src/scheduler/resource_scheduler.py
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Optional
from collections import deque
import asyncio
class TaskPriority(Enum):
CRITICAL = 0  # 最高（生产故障修复）
HIGH = 1      # 重要功能开发
NORMAL = 2    # 常规任务
LOW = 3       # 探索性任务
@dataclass
class ResourceQuota:
"""资源配额定义"""
max_concurrent_tasks: int = 5
max_llm_calls_per_minute: int = 60
max_tokens_per_task: int = 100
max_sandbox_instances: int = 3
cpu_cores_limit: float = 4.0
memory_limit_mb: int = 4096
@dataclass
class TaskResource:
"""任务资源使用情况"""
task_id: str
priority: TaskPriority
llm_calls_used: int = 0
tokens_used: int = 0
sandbox_count: int = 0
cpu_used: float = 0.0
memory_used_mb: int = 0
started_at: Optional[float] = None
last_scheduled: Optional[float] = None
```
### 3.3 资源调度器核心实现
```
# /src/scheduler/resource_scheduler.py (续)
import time
from typing import List, Optional
import asyncio
class ResourceScheduler:
"""统一资源调度器"""
def __init__(self, global_quota: ResourceQuota):
self.global_quota = global_quota
self._queues = {
TaskPriority.CRITICAL: deque(),
TaskPriority.HIGH: deque(),
TaskPriority.NORMAL: deque(),
TaskPriority.LOW: deque(),
}
self._running: Dict[str, TaskResource] = {}
self._quota_usage = {
"concurrent_tasks": 0,
"llm_calls_per_minute": 0,
"sandbox_instances": 0,
"cpu_cores": 0,
"memory_mb": 0,
}
self._last_reset = time.time()
self._lock = asyncio.Lock()
async def submit(
self,
task_id: str,
priority: TaskPriority = TaskPriority.NORMAL,
requested_resources: Optional[Dict] = None
) -> bool:
"""提交任务到调度队列"""
async with self._lock:
# 检查全局资源是否饱和
if self._quota_usage["concurrent_tasks"] >= self.global_quota.max_concurrent_tasks:
# 除非是CRITICAL任务，否则排队
if priority != TaskPriority.CRITICAL:
self._queues[priority].append(task_id)
return False
# 分配资源
self._quota_usage["concurrent_tasks"] += 1
self._running[task_id] = TaskResource(
task_id=task_id,
priority=priority,
started_at=time.time(),
last_scheduled=time.time()
)
return True
async def can_proceed(self, task_id: str) -> bool:
"""检查任务是否可以继续执行（资源预检）"""
if task_id not in self._running:
return False
resource = self._running[task_id]
# 检查各项资源限制
checks = [
resource.llm_calls_used  bool:
"""消费LLM调用配额"""
async with self._lock:
if task_id not in self._running:
return False
resource = self._running[task_id]
# 重置分钟计数器
if time.time() - self._last_reset > 60:
self._quota_usage["llm_calls_per_minute"] = 0
self._last_reset = time.time()
# 检查LLM调用限流
if self._quota_usage["llm_calls_per_minute"] >= self.global_quota.max_llm_calls_per_minute:
return False
# 检查任务Token预算
if resource.tokens_used + tokens > self.global_quota.max_tokens_per_task:
return False
# 扣减配额
self._quota_usage["llm_calls_per_minute"] += 1
resource.llm_calls_used += 1
resource.tokens_used += tokens
return True
async def release(self, task_id: str):
"""释放任务资源"""
async with self._lock:
if task_id in self._running:
self._quota_usage["concurrent_tasks"] -= 1
# 释放其他资源...
del self._running[task_id]
# 从队列中取出下一个任务（抢占式）
await self._schedule_next()
async def _schedule_next(self):
"""调度下一个任务（抢占式优先级调度）"""
for priority in [TaskPriority.CRITICAL, TaskPriority.HIGH,
TaskPriority.NORMAL, TaskPriority.LOW]:
if self._queues[priority]:
next_task = self._queues[priority].popleft()
# 重新提交（递归）
await self.submit(next_task, priority)
def get_queue_status(self) -> Dict:
"""获取队列状态"""
return {
"critical": len(self._queues[TaskPriority.CRITICAL]),
"high": len(self._queues[TaskPriority.HIGH]),
"normal": len(self._queues[TaskPriority.NORMAL]),
"low": len(self._queues[TaskPriority.LOW]),
"running": len(self._running),
"quota": {
"concurrent_tasks": self._quota_usage["concurrent_tasks"],
"llm_calls_per_minute": self._quota_usage["llm_calls_per_minute"],
"sandbox_instances": self._quota_usage["sandbox_instances"],
}
}
```
### 3.4 与调度器状态机的集成
```
# /src/scheduler/orchestrator.py (集成片段)
class TaskOrchestrator:
def __init__(self, scheduler: ResourceScheduler):
self.resource_scheduler = scheduler
async def execute(self, task: Task):
# 1. 提交任务到调度器
priority = self._determine_priority(task)
if not await self.resource_scheduler.submit(task.id, priority):
# 排队等待
task.state = TaskState.QUEUED
return
try:
# 2. 执行主流程（每个LLM调用前检查资源）
while task.state != TaskState.DONE:
# 资源预检
if not await self.resource_scheduler.can_proceed(task.id):
# 资源不足，挂起等待
task.state = TaskState.PAUSED_RESOURCE
await asyncio.sleep(5)
continue
# 执行下一步（如CODING）
await self._execute_step(task)
finally:
# 3. 释放资源
await self.resource_scheduler.release(task.id)
def _determine_priority(self, task: Task) -> TaskPriority:
"""根据任务类型和上下文确定优先级"""
if task.context.get("is_hotfix"):
return TaskPriority.CRITICAL
if task.context.get("is_production_issue"):
return TaskPriority.CRITICAL
if task.context.get("is_feature"):
return TaskPriority.HIGH
if task.context.get("is_exploration"):
return TaskPriority.LOW
return TaskPriority.NORMAL
```
### 3.5 ADR：抢占式调度 vs 公平调度
| ADR · 多任务调度策略 |
| --- |
| 决策 | 采用优先级抢占式调度 + 公平时间片混合策略：
① 高优先级任务（CRITICAL/HIGH）可抢占低优先级任务的资源。
② 同优先级任务采用时间片轮转（每个任务最多连续运行30秒）。
③ 长运行任务（>5分钟）自动降级为LOW优先级。 |
| 理由 | ① 生产故障修复必须优先保障（CRITICAL）。② 防止单个任务无限占用资源。③ 保证低优先级任务也能获得执行机会。 |
| 风险与缓解 | 风险：频繁抢占导致低优先级任务饥饿。缓解：CRITICAL任务每天不超过5个，超过后降级为HIGH。 |



## Step 5.7：Agent拉起机制
### 核心概念澄清

> **核心声明：在 V14.1 中，Agent 不是独立微服务、不是容器、不是进程，而是 调度器进程内的一个 Python 异步协程（asyncio Task）。**
#### 1.1 “调用 Agent”的两种语义
| 语义 | 含义 | V14.1 的实现 |
| --- | --- | --- |
| A2A 通信 | Agent A 请求 Agent B 执行某任务或提供信息 | 通过 A2A 协议（结构化消息）实现 Agent 间通信 |
| 系统拉起 Agent | 调度器将 Agent 实例化并开始执行 | 调度器的状态机通过 asyncio.create_task() 拉起 Agent 协程 |
用户的问题“怎么调用 Agent”属于第二种语义：系统如何将 Agent 实例化并启动执行。

### Agent 的实现形态

```
# Agent 的本质是一个异步协程类
class DeveloperAgent:
def __init__(self, llm_client, graph_repo, sandbox, checkpoint_mgr):
self.llm = llm_client
self.graph = graph_repo
self.sandbox = sandbox
self.checkpoint = checkpoint_mgr
async def run(self, context: TaskContext) -> AgentResult:
# 思考 → 行动 → 观察 循环
while not self.should_stop():
thought = await self.think(context)        # 调用 LLM
action = await self.act(thought)           # 执行工具（通过 MCP）
observation = await self.observe(action)   # 收集结果
context = self.update_context(context, observation)
return AgentResult(...)
```
#### 2.1 关键特征
- 进程内执行：所有 Agent 运行在同一个进程中，无进程间通信开销。
- 协程隔离：每个 Agent 是一个独立的 asyncio Task，由事件循环调度。
- 状态隔离：Agent 间不直接共享内存，通过调度器的 Session/Checkpoint 传递经过验证的数据。
- 私有工作记忆（L4）：每个 Agent 有独立的局部工作记忆，不跨 Agent 共享。
- 拉起速度：协程创建为微秒级，远快于容器启动（秒级）。

### 系统拉起 Agent 的完整流程

#### 3.1 第1步：用户触发（外部入口）
```
# API 入口
@router.post("/api/v1/tasks")
async def create_task(req: TaskCreateRequest):
task = Task(prd=req.prd, state=TaskState.IDLE)
await scheduler.submit(task)  # ← 提交给调度器
return {"task_id": task.id}
```
用户调用的不是 Agent，而是调度器的 API 入口。
#### 3.2 第2步：调度器状态机驱动
```
# Step 5.1 调度器状态机（核心逻辑）
class SchedulerStateMachine:
async def run(self, task: Task):
while task.state != TaskState.DONE:
if task.state == TaskState.IDLE:
task.state = TaskState.PARSING
result = await self._run_agent(ParserAgent, task)
elif task.state == TaskState.PARSING:
task.state = TaskState.PLANNING
result = await self._run_agent(ArchitectAgent, task)
elif task.state == TaskState.PLANNING:
task.state = TaskState.CODING
# 🔴 关键：拉起 DeveloperAgent
result = await self._run_agent(DeveloperAgent, task)
# ... 依次类推
```
#### 3.3 第3步：拉起 Agent 协程（核心）
```
# 实际拉起 Agent 的方法
async def _run_agent(self, agent_class, task: Task) -> AgentResult:
# 1. 构建 Agent 的上下文（注入 L1-L5）
context = TaskContext(
l1=SYSTEM_PROMPTS[agent_class.__name__],       # 协作宪法
l2=await self._query_graphs(task),             # 四图谱事实
l3=self._build_task_context(task),             # 任务状态
l4={},                                         # 私有工作记忆（空）
l5=await self._retrieve_memories(task)         # 长期记忆
)
# 2. 实例化 Agent（依赖注入）
agent = agent_class(
llm_client=self.llm_client,
graph_repo=self.graph_repo,
sandbox=self.sandbox,
checkpoint_mgr=self.checkpoint_mgr
)
# 3. 🔴 拉起 Agent 协程（本质是异步函数调用）
result = await agent.run(context)
# 4. 将结果写入检查点（供下游 Agent 使用）
await self.checkpoint_mgr.save(task.id, result)
return result
```
#### 3.4 第4步：Agent 执行循环
```
class DeveloperAgent:
async def run(self, context: TaskContext) -> AgentResult:
for iteration in range(self.max_iterations):
# 思考：调用 LLM
thought = await self.think(context)
# 行动：执行工具调用（通过 MCP）
action = await self.act(thought)
# 观察：收集结果
observation = await self.observe(action)
# 更新上下文（L4 私有工作记忆）
context.l4["last_action"] = action
context.l4["last_observation"] = observation
# 终止条件判断
if self.should_stop(observation):
break
return AgentResult(success=True, output=context.l4["final_output"])
```

### 与 MCP/A2A 的抽象分层

在 V14.1 中，MCP 和 A2A 服务于不同的抽象层级，而“系统拉起 Agent”是另一个独立的层级。
> **┌─────────────────────────────────────────────────────────────┐
│              💻 外部系统（用户 / CI/CD / 其他服务）         │
└──────────────────────────┬──────────────────────────────────┘
│ HTTP / WebSocket
▼
┌─────────────────────────────────────────────────────────────┐
│              🌐 API 网关层（Step 1.1）                     │
│  POST /api/v1/tasks   →  提交任务                         │
│  GET /api/v1/tasks/{id} →  查询状态                       │
└──────────────────────────┬──────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────┐
│              🎯 调度器（Orchestrator）                     │
│  • 状态机驱动（Step 5.1）                                 │
│  • 🔴 通过 asyncio.create_task() 拉起 Agent 协程          │
│  • 通过 Checkpoint 管理状态（Step 2.2）                   │
│  • 通过 Audit 记录决策链（Step 1.2 补丁）                 │
└──────────────┬─────────────────────────────────────────────┘
│ await agent.run()
▼
┌─────────────────────────────────────────────────────────────┐
│              🧠 Agent 协程（DeveloperAgent / ArchitectAgent）│
│  • 思考→行动→观察 循环（Step 5.1）                        │
│  • 🔽 通过 MCP 调用工具（向下）                           │
│  • ↔️ 通过 A2A 与其他 Agent 通信（水平）                  │
└─────────────────────────────────────────────────────────────┘**
#### 4.1 三层调用关系
| 层级 | 用途 | 协议/方式 | 调用方向 |
| --- | --- | --- | --- |
| 系统 → Agent | 调度器实例化并驱动 Agent 协程 | asyncio.create_task() + await agent.run() | 向上驱动 |
| Agent → 工具 | Agent 调用外部工具/资源（四图谱、沙箱、数据库） | MCP（Model Context Protocol） | 向下调用 |
| Agent → Agent | Agent 之间协作通信（任务分发、审查、仲裁） | A2A（Agent-to-Agent Protocol） | 水平通信 |
#### 4.2 与现有协议的定位
- MCP 不在“拉起 Agent”层：MCP 是 Agent 已经运行后用来调用工具的协议。它不负责 Agent 的启动或生命周期管理。
- A2A 不在“拉起 Agent”层：A2A 是 Agent 之间已经运行后用来相互通信的协议。它也不负责 Agent 的启动。
- “拉起 Agent”是调度器的职责：通过 asyncio 协程直接实例化和驱动，是 V14.1 自研调度器的核心能力。

### PRD/ADR 规格

#### 5.1 PRD · Agent 拉起机制
| PRD · Agent 拉起机制 |
| --- |
| 背景 | 外部系统需要通过调度器驱动多智能体协作。Agent 不是预先部署的微服务，而是由调度器按需实例化的异步协程。 |
| 用户故事 | 作为调度器，我根据状态机的进度，在合适的时机await agent.run()拉起对应的 Agent 协程，执行完成后将结果写入检查点。 |
| 需求描述 | ① Agent 定义为异步协程类，实现 run(context: TaskContext) -> AgentResult 方法。
② 调度器通过 asyncio.create_task() 拉起 Agent。
③ 拉起时注入 L1-L5 上下文（L1 协作宪法、L2 四图谱事实、L3 任务状态、L4 私有记忆、L5 长期记忆）。
④ Agent 执行完成后，结果写入检查点（Checkpoint），供下游 Agent 使用。
⑤ 外部系统通过 API 调用调度器，不直接调用 Agent。 |
| 范围 | Do：进程内协程拉起；依赖注入；上下文构建；结果持久化。
Don't：不通过 HTTP/gRPC 远程调用 Agent；不将 Agent 部署为独立容器。 |
| 数据契约 | ```
class TaskContext(BaseModel):
task_id: str
l1: str  # System Prompt（协作宪法）
l2: Dict[str, Any]  # 四图谱查询结果
l3: Dict[str, Any]  # 任务状态（PRD摘要、DAG进度）
l4: Dict[str, Any]  # Agent私有工作记忆
l5: List[Dict[str, Any]]  # 长期记忆（检索结果）
class AgentResult(BaseModel):
success: bool
output: Any
error: Optional[str] = None
duration_ms: float
``` |
| SC→AC | SC1: Agent 拉起成功 → AC1: 状态机触发 CODING 状态时，调用 _run_agent(DeveloperAgent, task) 返回 AgentResult。
SC2: 上下文注入完整 → AC2: Agent 的 run() 方法中 context.l1、context.l2 非空且包含预期内容。
SC3: 结果持久化 → AC3: Agent 执行完成后，检查点中存在对应 task_id 的记录。 |
| 待定决策 | Q: Agent 执行超时如何处理？ → 决议：在 _run_agent() 中包装 asyncio.wait_for(agent.run(), timeout=300)，超时后取消协程并标记 FAILED。 |
#### 5.2 ADR · Agent 实现形态
| ADR · Agent 实现形态 |
| --- |
| 决策 | Agent 实现为进程内异步协程，而非独立微服务或容器。
① 所有 Agent 运行在调度器同一进程中。
② 通过 asyncio 事件循环调度。
③ 通过依赖注入传递外部依赖（LLM 客户端、图谱仓库、沙箱）。
④ 通过 Checkpoint 实现状态跨 Agent 传递。 |
| 理由 | ① 无网络开销：协程间通信为零延迟。② 极速拉起：协程创建为微秒级。③ 共享内存：Checkpoint 直接读取，无需序列化传递。④ 简化运维：无需部署多个微服务。⑤ 与 V14.1 的 asyncio 调度器自然兼容。 |
| 备选方案 | ① 独立微服务（HTTP/gRPC 拉起）→ 网络延迟高，资源消耗大，不适合密集 Agent 协作。② 独立容器（Docker 拉起）→ 启动慢（秒级），资源隔离过度。 |

### 与现有 Step 的映射

| Step | 原有内容 | Agent 拉起机制的补充 |
| --- | --- | --- |
| Step 5.1调度器状态机 | 定义了状态转换（IDLE→PARSING→PLANNING→CODING→...） | 需补充 在状态转换中增加 _run_agent() 方法的实现，明确如何拉起 Agent 协程 |
| Step 5.2Agent 角色与 Prompt | 定义了 5 个 Agent 的 System Prompt 和职责 | 需补充 每个 Agent 类必须实现 run(context: TaskContext) -> AgentResult 接口 |
| Step 2.2检查点持久化 | Redis + PostgreSQL 双层存储 | 需补充 Agent 执行完成后，结果通过 CheckpointManager 写入检查点，供下游 Agent 使用 |
| Step 5.4Agent 间通信 | 定义了 A2A 协议的结构化消息格式 | 无修改 该 Step 处理的是 Agent 间通信，与“系统拉起 Agent”是不同层级 |
| Step 3.1-3.4四图谱 | 代码/数据库/配置/知识图谱 | 无修改 Agent 通过 MCP 调用图谱查询，与拉起机制无关 |

### 代码示例

#### 7.1 调度器拉起 Agent 的完整实现
```
# /src/scheduler/orchestrator.py
import asyncio
from typing import Type, Dict, Any
from src.agents.base import BaseAgent
from src.agents.developer import DeveloperAgent
from src.agents.architect import ArchitectAgent
from src.agents.parser import ParserAgent
from src.scheduler.context import TaskContext
class TaskOrchestrator:
"""任务编排器 - 负责拉起 Agent 并驱动执行"""
# Agent 类名 → 对应 System Prompt 的映射
_AGENT_PROMPTS = {
"ParserAgent": "你是一个需求解析器...",
"ArchitectAgent": "你是一个架构师...",
"DeveloperAgent": "你是一个开发者...",
"ReviewerAgent": "你是一个代码审查员...",
"QAAgent": "你是一个QA验证员..."
}
def __init__(self, llm_client, graph_repo, sandbox, checkpoint_mgr):
self.llm_client = llm_client
self.graph_repo = graph_repo
self.sandbox = sandbox
self.checkpoint_mgr = checkpoint_mgr
async def _run_agent(
self,
agent_class: Type[BaseAgent],
task: Task
) -> AgentResult:
"""拉起 Agent 协程的核心方法"""
try:
# 1. 构建上下文（L1-L5）
context = await self._build_context(task)
# 2. 实例化 Agent
agent = agent_class(
llm_client=self.llm_client,
graph_repo=self.graph_repo,
sandbox=self.sandbox,
checkpoint_mgr=self.checkpoint_mgr
)
# 3. 🔴 拉起 Agent 协程（带超时）
result = await asyncio.wait_for(
agent.run(context),
timeout=300  # 5分钟超时
)
# 4. 写入检查点
await self.checkpoint_mgr.save(
task.id,
CheckpointData(
task_id=task.id,
state=task.state,
context={"agent_output": result.output}
)
)
return result
except asyncio.TimeoutError:
return AgentResult(
success=False,
error=f"Agent {agent_class.__name__} timed out after 300s"
)
async def _build_context(self, task: Task) -> TaskContext:
"""构建 Agent 上下文（L1-L5）"""
return TaskContext(
task_id=task.id,
l1=self._AGENT_PROMPTS[agent_class.__name__],
l2=await self._query_graphs(task),
l3={
"prd": task.prd[:500],
"dag_progress": self._get_progress(task),
"upstream_output": await self._get_upstream_output(task)
},
l4={},  # Agent 私有工作记忆（初始为空）
l5=await self._retrieve_memories(task)
)
```
#### 7.2 外部系统调用调度器的 API
```
# /src/api/routes/tasks.py
from fastapi import APIRouter, Depends
from src.scheduler.orchestrator import TaskOrchestrator
router = APIRouter(prefix="/api/v1")
@router.post("/tasks")
async def create_task(
req: TaskCreateRequest,
orchestrator: TaskOrchestrator = Depends(get_orchestrator)
):
"""外部系统通过此 API 提交任务，调度器将拉起 Agent"""
task = Task(prd=req.prd, state=TaskState.IDLE)
# 提交到调度器，调度器内部会驱动状态机并拉起 Agent
await orchestrator.submit(task)
return {"task_id": task.id}
@router.get("/tasks/{task_id}")
async def get_task_status(
task_id: str,
orchestrator: TaskOrchestrator = Depends(get_orchestrator)
):
"""外部系统通过此 API 查询任务状态"""
task = await orchestrator.get_task(task_id)
return {"task_id": task.id, "state": task.state}
```
#### 7.3 Agent 基类定义
```
# /src/agents/base.py
from abc import ABC, abstractmethod
from src.scheduler.context import TaskContext
class BaseAgent(ABC):
"""所有 Agent 的基类"""
def __init__(self, llm_client, graph_repo, sandbox, checkpoint_mgr):
self.llm_client = llm_client
self.graph_repo = graph_repo
self.sandbox = sandbox
self.checkpoint_mgr = checkpoint_mgr
@abstractmethod
async def run(self, context: TaskContext) -> AgentResult:
"""Agent 的执行入口，由调度器调用"""
pass
@abstractmethod
async def think(self, context: TaskContext) -> Thought:
"""思考阶段：调用 LLM"""
pass
@abstractmethod
async def act(self, thought: Thought) -> Action:
"""行动阶段：执行工具调用"""
pass
@abstractmethod
async def observe(self, action: Action) -> Observation:
"""观察阶段：收集执行结果"""
pass
```
> **✅ Agent 拉起机制交付确认
核心概念澄清：区分“系统拉起 Agent”与“Agent 间通信（A2A）”两种语义
Agent 实现形态：进程内 asyncio 协程，而非独立微服务
拉起流程：外部 API → 调度器状态机 → asyncio.create_task() → Agent 协程
抽象分层：系统→Agent（协程拉起）、Agent→工具（MCP）、Agent→Agent（A2A）
PRD/ADR：完整的规格定义，含数据契约、SC→AC、备选方案对比
与现有 Step 映射：Step 5.1/5.2 需补充，Step 5.4/3.1-3.4 无修改
代码示例：调度器拉起实现、外部 API 调用、Agent 基类定义
下一步：可将本报告中的代码示例和 PRD/ADR 规格合并到 Step 5.1（调度器状态机）和 Step 5.2（Agent 角色与 Prompt）中。**
— V14.1 开发计划 · Agent 拉起机制 · 2026年6月22日 —
