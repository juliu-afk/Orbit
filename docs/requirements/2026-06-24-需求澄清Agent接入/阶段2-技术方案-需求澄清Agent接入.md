# 阶段2-技术方案：需求澄清 Agent 接入

> 基线：`阶段1-PRD-需求澄清Agent接入.md`（已确认）。本文为实现就绪级技术方案，含边界 case 清单。

---

## 一、边界 Case 清单（逐场景，阶段4 验收依据）

### 1.1 chat 端点消息分发（`api/routes/chat.py`）

| # | 场景 | 预期行为 | 不适用理由 |
|---|------|----------|-----------|
| C1 | `type=chat` 首轮（无历史） | ContextMatcher 匹配 → 注入 context → ClarifierAgent.execute() → 返回 clarify 响应 | — |
| C2 | `type=chat` 后续轮（有历史） | 跳过匹配，直接构建 context（历史+项目）→ ClarifierAgent.execute() | — |
| C3 | `type=confirm` 无 modified_prd | 用 Agent 上轮 ready 的 PRD → 重过 V1-V3 → 建任务 | — |
| C4 | `type=confirm` 带 modified_prd | 用用户修改版覆盖 → 重过 V1-V3 → 建任务 | — |
| C5 | `type=confirm` 但 Agent 未 ready | 返回 error"需求尚未明确，请继续对话" | 不允许跳过澄清 |
| C6 | 未知 type | 返回 error"未知消息类型" | — |
| C7 | text 为空 | 返回 error"输入为空" | 现有行为保留 |
| C8 | LLM 熔断（V4 间接） | ClarifierAgent 捕获降级 → 返回"暂时无法分析，请稍后重试" | 不阻断会话 |
| C9 | session_id 不存在 | 返回 error"会话不存在" | SessionRegistry.get() 返回 None |

### 1.2 ClarifierAgent.execute()（`agents/clarifier.py`）

| # | 场景 | 预期行为 |
|---|------|----------|
| A1 | llm=None（mock 模式） | 返回模板回复，status=clarifying，供 CI 测试 |
| A2 | llm 调用成功 | 解析 JSON → V5 结构契约校验 → 通过则返回 AgentOutput |
| A3 | LLM 输出非合法 JSON | V5 失败 → 打回，注入"请输出合法JSON"重试 1 次，再失败返回降级回复 |
| A4 | V4 熵超阈值（HighEntropyError） | 捕获 → 打回重试 1 次，再失败返回降级回复 |
| A5 | Agent 自评 ready | 返回 ready + structured_prd，交由 chat 端点过 V1-V3 |
| A6 | LLM 返回 ready 但 V1-V3 失败 | chat 端点打回，context 注入失败原因，Agent 继续问 |

### 1.3 校验链 validate_prd()（`agents/clarifier.py`）

| # | 场景 | V1 | V2 | V3 | 结果 |
|---|------|----|----|----|----|
| V-1 | 三项完整且一致 | ✓ | ✓ | ✓ | passed=True |
| V-2 | goal="待定" | ✗ | — | — | passed=False, layer=V1, reason="goal 是占位词" |
| V-3 | scope="做后台"（无边界） | ✗ | — | — | passed=False, layer=V1, reason="scope 缺少边界描述" |
| V-4 | acceptance=[] 空列表 | ✗ | — | — | passed=False, layer=V1, reason="acceptance_criteria 为空" |
| V-5 | goal 谈"支付"但 scope/acceptance 无"支付" | — | ✗ | — | passed=False, layer=V2, reason="goal 核心词无呼应" |
| V-6 | acceptance="用户体验好"（无可观测动词） | — | ✗ | — | passed=False, layer=V2, reason="验收标准不可观测" |
| V-7 | goal="降延迟" + acceptance="全量扫描" | — | — | ✗ | passed=False, layer=V3, reason="goal与验收方向冲突" |
| V-8 | 用户部分修改 PRD | 重过 V1-V3 | — | — | 通过则建任务，不通过返回失败原因给前端 |

### 1.4 前端（ChatPanel.vue + chat.ts）

| # | 场景 | 预期行为 |
|---|------|----------|
| F1 | 发送消息 | 连接 /api/v1/chat → 收到 clarify 响应 → 渲染 reply |
| F2 | 收到 acceptance_options | 渲染多选卡片 + "其它"原位输入 |
| F3 | 收到 ready | 渲染 PRD 确认卡片（每条可编辑） |
| F4 | 用户点确认（无修改） | 发 type=confirm |
| F5 | 用户编辑某条后确认 | 发 type=confirm + modified_prd |
| F6 | 收到 task_created | 显示"任务已创建"+task_id |
| F7 | WS 断开 | 输入框置灰 + "连接断开，正在重连" |

---

## 二、文件改动详单（8 文件）

### 文件1：`src/orbit/agents/base.py`（改）

```python
class AgentRole(StrEnum):
    ARCHITECT = "architect"
    DEVELOPER = "developer"
    REVIEWER = "reviewer"
    CONFIG_MANAGER = "config_manager"
    QA = "qa"
    CLARIFIER = "clarifier"  # 新增
```

### 文件2：`src/orbit/agents/clarifier.py`（新建）

```python
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field
from orbit.agents.base import AgentInput, AgentOutput, AgentRole, BaseAgent
from orbit.gateway.schemas import LLMRequest

class StructuredPRD(BaseModel):
    """V5 结构契约——Agent 输出的结构化 PRD schema"""
    goal: str = ""
    scope: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    edge_cases: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    acceptance_options: list[str] = Field(default_factory=list)  # 仅需用户选验收时填

class ClarifierAgent(BaseAgent):
    role = AgentRole.CLARIFIER

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        # 1. 构建 prompt（user消息 + context）
        # 2. self.llm.generate(LLMRequest(system_prompt, prompt))（mock 模式跳过）
        # 3. 解析输出 JSON → StructuredPRD.model_validate_json()（V5）
        # 4. 返回 AgentOutput.result = {reply, clarification_status, structured_prd, missing_fields}
        ...

    def system_prompt(self) -> str:
        return CLARIFIER_SYSTEM_PROMPT  # PRD 定义的全文

def validate_prd(prd: StructuredPRD) -> ValidationResult:
    """V1+V2+V3 纯 Python 校验"""
    # V1: 字段非空、非占位、长度
    # V2: 语义呼应、可观测动词、scope 无字面矛盾
    # V3: goal↔acceptance / scope↔constraints 方向冲突
    ...

class ValidationResult(BaseModel):
    passed: bool
    failed_layer: str = ""  # V1 | V2 | V3 | ""
    reasons: list[str] = Field(default_factory=list)
```

### 文件3：`src/orbit/agents/factory.py`（改）

```python
from orbit.agents.clarifier import ClarifierAgent  # 新增 import

_registry: dict[AgentRole, type[BaseAgent]] = {
    ...
    AgentRole.CLARIFIER: ClarifierAgent,  # 新增
}
```

### 文件4：`src/orbit/gateway/client.py`（改）

```python
class LLMClient:
    async def generate(self, req: LLMRequest, task_id: str) -> LLMResponse:
        # 原有逻辑保留
        ...

    async def generate_stream(self, req: LLMRequest, task_id: str,
                               entropy_monitor=None) -> LLMResponse:
        """新增：流式生成 + V4 熵监控接入。
        litellm.acompletion(stream=True, logprobs=True) 逐 token 喂给 L3EntropyMonitor。
        熵超阈值抛 HighEntropyError。无 monitor 时退化为普通流式。
        """
        ...
```

### 文件5：`src/orbit/api/routes/chat.py`（改）

```python
from orbit.agents.clarifier import ClarifierAgent, validate_prd, StructuredPRD
from orbit.gateway.client import LLMClient  # 仅实例化后注入 Agent，不直接调用

_llm = LLMClient()  # 进程级单例
_clarifier = ClarifierAgent(llm=_llm)

async def chat_endpoint(ws):
    while True:
        raw = await ws.receive_text()
        msg = json.loads(raw)
        if msg["type"] == "chat":
            # 构建 context（历史+项目）→ await _clarifier.execute(input) → 返回
            ...
        elif msg["type"] == "confirm":
            # 取 ready PRD（或 modified_prd）→ validate_prd() → 建任务 → 返回 task_created
            ...
```

### 文件6：`frontend/src/stores/chat.ts`（改）

```typescript
function connectChatWs(sessionId: string, projectName: string) {
  // 连接 ws://host/api/v1/chat（不再连 /ws/dashboard）
  // onmessage → 分发：clarify/ready/task_created/error
}

function send(text: string, sessionId: string, projectName: string) { ... }
function confirm(prd?: StructuredPRD, sessionId: string, projectName: string) { ... }
```

### 文件7：`frontend/src/components/chat/ChatPanel.vue`（改）

- 渲染 agent reply（替代旧的"匹配到N个项目"）
- acceptance_options 渲染为多选 + "其它"原位输入
- ready 时渲染 PRD 确认卡片（每条 goal/scope/acceptance 可编辑输入框）
- task_created 显示结果

### 文件8：`frontend/src/views/DashboardView.vue`（改）

- chat WS 初始化（连 /api/v1/chat）
- 消息分发增加 chat 类型处理

---

## 三、数据流（完整时序）

```
用户输入 → chat.ts.send() → WS /api/v1/chat
  → chat.py: 构建 context（SessionRegistry 历史 + ProjectRegistry 项目信息）
  → ClarifierAgent.execute()
    → system_prompt + user消息 → LLMClient.generate_stream()
      → litellm stream=True → L3EntropyMonitor（V4）
    → 输出 JSON → StructuredPRD.model_validate（V5）
    → 返回 {reply, clarification_status, structured_prd}
  → 若 ready → validate_prd()（V1-V3）
    → 通过 → WS 返回 ready + PRD → 前端渲染确认卡片
    → 不通过 → 注入失败原因 → Agent 继续问
  → 用户确认（可能部分修改）→ chat.ts.confirm()
  → chat.py: validate_prd(最终PRD) → POST /tasks → Scheduler → task_created
```

---

## 四、测试策略

| 层 | 用例数 | 覆盖 |
|----|--------|------|
| validate_prd 单元测试 | 8 | V-1 到 V-8 全场景 |
| ClarifierAgent 单元测试（mock llm） | 4 | A1/A2/A3/A5 |
| chat 端点集成测试 | 6 | C1-C4/C8/C9 |
| 前端 Store 测试 | 4 | F1/F2/F4/F6 |
| 合计 | 22 | |

---

## 五、风险与缓解

| 风险 | 缓解 |
|------|------|
| LLM 输出不稳定 JSON | V5 校验 + 重试 1 次 + 降级回复 |
| V4 流式接入增加延迟 | 无 monitor 时退化为非流式；monitor 纯内存计算零 IO |
| 对话历史 token 膨胀 | 截断最近 10 轮；max_tokens=2048 |
| 用户部分修改后 V1-V3 不过 | 返回具体失败原因，用户可再改 |

---

## 六、实施顺序（阶段3 编码顺序）

1. `agents/base.py` + `agents/clarifier.py` + `agents/factory.py`（后端 Agent 骨架）
2. `gateway/client.py`（流式 + V4）
3. `api/routes/chat.py`（端点接入）
4. 单元测试（validate_prd + ClarifierAgent mock）
5. `frontend`（chat.ts + ChatPanel.vue + DashboardView.vue）
6. 集成测试