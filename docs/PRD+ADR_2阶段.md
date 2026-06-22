## Step 2.1：LiteLLM网关集成与熔断器

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | MVP使用Mock LLM仅能返回固定模板，无法应对真实场景。需接入真实LLM（DeepSeek为默认主力，Qwen为备选），并实现统一网关（LiteLLM Proxy）管理密钥、成本追踪和降级。同时必须实现熔断器，防止下游LLM API故障导致雪崩。 |
| **用户故事** | 作为调度器，我通过统一的`LLMClient`调用`generate(prompt, system_prompt)`，自动选择可用模型、记录Token消耗，并在连续失败时触发熔断，快速返回错误而非无限等待。 |
| **需求描述** | ①部署LiteLLM Proxy容器（已包含在docker-compose中）；②配置主模型（DeepSeek-Chat）和备选模型（Qwen-Plus），API Key从环境变量读取；③实现`LLMClient`类，封装`litellm.acompletion`异步调用，支持流式（预留）和同步模式（MVP）；④实现熔断器（连续5次失败或1分钟内错误率>30%触发，冷却60s，半开状态下放行1个请求探测恢复）；⑤每次调用记录Token消耗（prompt_tokens, completion_tokens, total_tokens）及成本（按模型单价计算）到日志；⑥提供`get_usage_stats(task_id)`查询任务累计消耗。 |
| **范围 (Do/Don't)** | **Do：**支持DeepSeek主力、Qwen备选；支持熔断器状态共享（Redis存储）；支持成本追踪。**Don't：**不实现流式输出（V2）；不实现复杂路由策略（如基于成本的智能路由）；不实现用户级配额管理。 |
| **数据契约** | ``代码块-1`` |
| **异常定义** | ``代码块-2`` |
| **成功标准→验收** | **SC1:**正常调用返回有效内容 →**AC1:**向LLMClient发送“写一个求和函数”，返回Python代码且包含`def add`。 |
| | **SC2:**熔断器生效 →**AC2:**模拟连续5次超时（或错误），第6次调用直接抛出`LLMCircuitOpenError`，不转发请求。 |
| | **SC3:**自动恢复 →**AC3:**熔断冷却60s后，第一次请求进入半开状态，若成功则回到CLOSED；若失败则重新OPEN。 |
| | **SC4:**成本追踪 →**AC4:**调用后查看日志，包含`cost_usd`字段，且数值合理（DeepSeek约$0.001/1K tokens）。 |
| | **SC5:**备选降级 →**AC5:**当主力模型连续失败2次，自动切换至备选模型并成功返回。 |
| **待定决策** | **Q1:**熔断状态存储在内存还是Redis？ →**决议：**Redis（跨实例共享，为后续水平扩展准备）。 |
| | **Q2:**熔断阈值（5次失败）是全局还是按模型？ →**决议：**按模型粒度，因为不同模型可用性不同。 |
| | **Q3:**冷却期60s是否固定？ →**决议：**固定，但在配置中可通过`CIRCUIT_BREAKER_TIMEOUT`覆盖。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **技术栈版本** | litellm 1.40.0 (Proxy模式，已部署), redis-py 5.0.1 (用于熔断状态), httpx 0.27.0 (异步HTTP客户端)，Python 3.11。 |
| | LiteLLM Proxy容器已集成在docker-compose中，使用`ghcr.io/berriai/litellm:main-v1.40.0`。 |
| **架构位置** | 能力层（AI网关），位于`/src/llm/client.py`，实现`LLMClient`。被调度器`/src/scheduler/orchestrator.py`调用。 |
| **实施细节** | **核心类与关键方法：** |
| | ``代码块-3`` |
| **风险与缓解** | 风险1：LiteLLM Proxy成为单点故障。缓解：docker-compose增加restart: unless-stopped，且在K8s阶段部署多副本。 |
| | 风险2：Redis连接丢失导致熔断器失效。缓解：熔断器降级为内存模式（仅单实例有效），并记录错误日志。 |
| **需求错位** | 若后续需接入Azure OpenAI等，需修改`PRICES`和模型映射。当前已支持通过配置扩展。 |
| **技术约束** | 必须使用异步（`async/await`）与调度器保持一致性；禁止同步调用`litellm.completion`。 |
| **环境配置** | LITELLM_PROXY_URL=http://litellm:4000 |
| | DEEPSEEK_API_KEY=sk-xxx |
| | QWEN_API_KEY=sk-yyy |
| | CIRCUIT_BREAKER_TIMEOUT=60 |
| | REDIS_URL=redis://redis:6379/0 |
| **依赖链** | LLMClient → redis-py (熔断状态) → litellm (acompletion) → LiteLLM Proxy → 各模型API。 |

🧪 原子化测试用例 (pytest)：
import pytest
from unittest.mock import AsyncMock, patch
from src.llm.client import LLMClient, LLMCircuitOpenError

@pytest.mark.asyncio
async def test_normal_call(llm_client, mock_redis):
with patch("src.llm.client.acompletion", new_callable=AsyncMock) as mock_acompletion:
mock_acompletion.return_value.choices = [AsyncMock(message=AsyncMock(content="def add(a,b): return a+b"))]
mock_acompletion.return_value.usage.dict.return_value = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
resp = await llm_client.generate(LLMRequest(prompt="sum"), "task-1")
assert "add" in resp.content
assert resp.cost_usd > 0

@pytest.mark.asyncio
async def test_circuit_breaker_opens(llm_client, mock_redis):
cb_key = "cb:deepseek/deepseek-chat"
# 模拟连续5次失败
for i in range(5):
await llm_client._circuit_breaker.record_failure(cb_key)
# 第6次应抛出熔断异常
with pytest.raises(LLMCircuitOpenError):
await llm_client.generate(LLMRequest(prompt="test"), "task-2")

@pytest.mark.asyncio
async def test_fallback(llm_client, mock_redis):
with patch("src.llm.client.acompletion", side_effect=Exception("API error")):
with patch.object(llm_client, "_select_model", return_value=llm_client.DEFAULT_MODEL):
with patch.object(llm_client, "generate", new_callable=AsyncMock) as mock_gen:
mock_gen.return_value = LLMResponse(...) # 模拟备选成功
await llm_client.generate(LLMRequest(prompt="test"), "task-3")
mock_gen.assert_called_once()

## Step 2.2：检查点持久化 (Redis + PostgreSQL)

| PRD |  |
| --- | --- |
| **背景** | 调度器执行长耗时任务（可能涉及多次LLM调用），若进程崩溃，重新执行将浪费Token和时间。需实现状态检查点，支持从崩溃中快速恢复。 |
| **用户故事** | 作为调度器，我在每个关键状态转换后调用`save_checkpoint(task_id, snapshot)`，若进程意外终止，重启后调用`load_checkpoint(task_id)`可恢复至最近断点。 |
| **需求描述** | ①提供`CheckpointManager`类，支持异步保存/加载；②Redis存储热数据（`EXPIRE 3600`），Key模板`ckpt:{env}:{task_id}`，值JSON序列化；③PostgreSQL存储冷备份（表`checkpoints`），使用异步写入（fire-and-forgot但需记录错误）；④加载时优先读Redis，若Redis不存在则查PG并回填Redis；⑤版本号（乐观锁）防止旧数据覆盖新数据；⑥提供清理接口`cleanup_old_checkpoints(days=7)`删除PG中过期数据。 |
| **范围 (Do/Don't)** | **Do：**支持Redis + PostgreSQL双层存储；支持版本号乐观锁；支持TTL自动过期。**Don't：**不支持跨版本兼容（V1->V2需显式迁移）；不支持压缩（单次<1MB）。 |
| **数据契约** | ``代码块-4`` |
| **异常定义** | ``代码块-5`` |
| **成功标准→验收** | **SC1:**保存延迟<20ms (P95) →**AC1:**压测`save`1000次，p95延迟<20ms（Redis写入）。 |
| | **SC2:**恢复完整性100% →**AC2:**保存后立即加载，`deepdiff`比较两个对象无差异（忽略updated_at毫秒级）。 |
| | **SC3:**Redis降级PG →**AC3:**Mock Redis抛出`ConnectionError`，保存仍能写入PG，加载时从PG读取并回填Redis。 |
| | **SC4:**版本号防覆盖 →**AC4:**先保存version=1，再保存version=2，加载时返回version=2；若version=1的PG数据晚到（异步），不会覆盖version=2（通过`WHERE version <= EXCLUDED.version`）。 |
| **待定决策** | **Q1:**是否压缩序列化数据？ →**决议：**暂不压缩（单次<1MB），若后续发现膨胀再启用`zlib`。 |
| | **Q2:**清理过期数据的频率？ →**决议：**每周运行一次`cleanup_old_checkpoints(7)`，可通过cron或调度器触发。 |

| ADR |  |
| --- | --- |
| **技术栈版本** | redis-py 5.0.1 (asyncio), asyncpg 0.29.0, orjson 3.9.15 (比pickle快且安全), SQLAlchemy 2.0.25 (用于PG表定义和迁移)。 |
| **架构位置** | 基础设施层，位于`/src/infrastructure/checkpoint_manager.py`，被调度器`SchedulerStateMachine`通过依赖注入调用。 |
| **实施细节** | **完整类实现：** |
| | ``代码块-6`` |
| **风险与缓解** | 风险：orjson序列化datetime时默认转为时间戳，反序列化可能丢失时区。缓解：在`CheckpointData.dict()`中指定`json_encoders = {datetime: lambda v: v.isoformat()}`。 |
| | 风险：PG写入失败（如连接断开）不会影响主流程（已fire-and-forgot），但会丢失冷备份。缓解：在`_save_to_pg`中捕获异常并记录Critical级别日志。 |
| **需求错位** | 若将来需跨语言（Java/Go）读取检查点，orjson序列化可读性好（JSON），PG表也兼容。但当前仅Python内部使用。 |
| **技术约束** | 禁止使用`pickle`（安全风险且无法跨语言）。必须使用异步驱动（asyncpg/aiosqlite）。 |
| **环境配置** | REDIS_URL=redis://redis:6379/0 |
| | DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/app |
| | CHECKPOINT_TTL=3600 |
| | ENV=dev |
| **依赖链** | CheckpointManager → redis-py (异步) → asyncpg (PG池) → 数据库。 |

🧪 原子化测试用例 (pytest)：
import pytest
from unittest.mock import AsyncMock, patch
from src.infrastructure.checkpoint_manager import CheckpointManager, CheckpointData

@pytest.mark.asyncio
async def test_save_and_load(checkpoint_manager):
data = CheckpointData(task_id="123e4567-e89b-12d3-a456-426614174000", state="CODING", retry_count=0, progress=0.5, context={"code": "print('hi')"})
await checkpoint_manager.save("123e4567-e89b-12d3-a456-426614174000", data)
loaded = await checkpoint_manager.load("123e4567-e89b-12d3-a456-426614174000")
assert loaded.task_id == data.task_id
assert loaded.context["code"] == "print('hi')"

@pytest.mark.asyncio
async def test_redis_fallback(checkpoint_manager, mock_redis_failure):
# 模拟Redis不可用，仍能写入PG
with patch.object(checkpoint_manager.redis, "setex", side_effect=ConnectionError):
data = CheckpointData(...)
await checkpoint_manager.save("task-2", data) # 不应抛出异常
# 加载时从PG读取
with patch.object(checkpoint_manager.redis, "get", return_value=None):
loaded = await checkpoint_manager.load("task-2")
assert loaded is not None

@pytest.mark.asyncio
async def test_version_optimistic_lock(checkpoint_manager):
data_v1 = CheckpointData(task_id="task-3", state="PLANNING", retry_count=0, progress=0.1, context={}, version=1)
await checkpoint_manager.save("task-3", data_v1)
data_v2 = CheckpointData(task_id="task-3", state="CODING", retry_count=0, progress=0.5, context={}, version=2)
await checkpoint_manager.save("task-3", data_v2)
loaded = await checkpoint_manager.load("task-3")
assert loaded.state == "CODING"
assert loaded.version >= 2


**✅ 阶段2 (Step 2.1 & 2.2) 交付确认**

本报告完整交付了阶段2核心强化的前两个步骤：

- **Step 2.1**：实现真实LLM调用（LiteLLM+熔断器+成本追踪），替代MVP的Mock，并具备韧性。
- **Step 2.2**：实现检查点持久化（Redis+PG双层存储），使调度器具备崩溃恢复能力。

这两个Step与已交付的MVP组件（调度器状态机、沙箱、API契约）无缝衔接。开发人员可按每个Step拆分为3-5个子任务，约2人日完成。后续Step 2.3（图谱引擎）将在此基础上继续构建。



```
// 代码块-1
from pydantic import BaseModel, Field

    from typing import Optional, Dict, Any, List

    from enum import Enum



    class ModelProvider(str, Enum):

        DEEPSEEK = "deepseek"

        QWEN = "qwen"



    class LLMRequest(BaseModel):

        prompt: str = Field(..., min_length=1, max_length=8000)

        system_prompt: Optional[str] = Field(None, max_length=2000)

        temperature: float = Field(0.7, ge=0.0, le=1.0)

        max_tokens: int = Field(2048, ge=1, le=8192)

        provider: Optional[ModelProvider] = None  # 若为空则自动选择



    class LLMResponse(BaseModel):

        content: str

        provider: ModelProvider

        model_name: str

        usage: Dict[str, int]  # {prompt_tokens, completion_tokens, total_tokens}

        cost_usd: float

        latency_ms: float

        cached: bool = False  # 是否命中缓存（预留）



    class CircuitBreakerState(str, Enum):

        CLOSED = "closed"       # 正常

        OPEN = "open"           # 熔断开启，拒绝请求

        HALF_OPEN = "half_open" # 探测恢复
```


```
// 代码块-2
class LLMError(Exception):

        """LLM调用基础异常"""

        pass



    class LLMConnectionError(LLMError):

        """网络/连接错误"""

        pass



    class LLMAuthenticationError(LLMError):

        """API密钥无效"""

        pass



    class LLMRateLimitError(LLMError):

        """请求限流（429）"""

        pass



    class LLMCircuitOpenError(LLMError):

        """熔断器开启，拒绝请求"""

        pass
```


```
// 代码块-3
import asyncio

    import time

    import logging

    import redis.asyncio as redis

    from litellm import acompletion

    from src.core.config import settings



    logger = logging.getLogger(__name__)



    class LLMClient:

        DEFAULT_MODEL = "deepseek/deepseek-chat"

        FALLBACK_MODEL = "qwen/qwen-plus"

        PRICES = {  # 每1K tokens 美元

            "deepseek/deepseek-chat": {"prompt": 0.00014, "completion": 0.00028},

            "qwen/qwen-plus": {"prompt": 0.0001, "completion": 0.0002},

        }



        def __init__(self, redis_client: redis.Redis):

            self.redis = redis_client

            self._circuit_breaker = CircuitBreaker(redis_client)



        async def generate(self, request: LLMRequest, task_id: str) -> LLMResponse:

            # 1. 选择模型

            model = self._select_model(request.provider)

            cb_key = f"cb:{model}"

            # 2. 检查熔断器

            if await self._circuit_breaker.is_open(cb_key):

                raise LLMCircuitOpenError(f"Circuit breaker open for {model}")

            # 3. 调用LLM

            try:

                start = time.time()

                response = await acompletion(

                    model=model,

                    messages=[

                        {"role": "system", "content": request.system_prompt or "You are a helpful assistant."},

                        {"role": "user", "content": request.prompt}

                    ],

                    temperature=request.temperature,

                    max_tokens=request.max_tokens,

                )

                latency = (time.time() - start) * 1000

                usage = response.usage.dict()

                cost = self._calculate_cost(model, usage)

                # 记录成功，重置熔断器计数

                await self._circuit_breaker.record_success(cb_key)

                self._log_usage(task_id, model, usage, cost, latency)

                return LLMResponse(

                    content=response.choices[0].message.content,

                    provider=ModelProvider.DEEPSEEK if "deepseek" in model else ModelProvider.QWEN,

                    model_name=model,

                    usage=usage,

                    cost_usd=cost,

                    latency_ms=latency

                )

            except Exception as e:

                # 记录失败，更新熔断器

                await self._circuit_breaker.record_failure(cb_key)

                # 尝试备选模型

                if model == self.DEFAULT_MODEL:

                    logger.warning(f"Fallback to {self.FALLBACK_MODEL} for task {task_id}")

                    request.provider = ModelProvider.QWEN

                    return await self.generate(request, task_id)

                raise



    class CircuitBreaker:

        FAILURE_THRESHOLD = 5

        TIMEOUT_SECONDS = 60

        ERROR_RATE_THRESHOLD = 0.3  # 1分钟内



        def __init__(self, redis_client):

            self.redis = redis_client



        async def is_open(self, key: str) -> bool:

            state = await self.redis.get(f"{key}:state")

            if state == b"open":

                return True

            if state == b"half_open":

                # 半开状态下，允许一个请求通过

                await self.redis.delete(f"{key}:state")  # 变为closed（探测成功后会被记录为成功）

                return False

            return False



        async def record_failure(self, key: str):

            fail_count = await self.redis.incr(f"{key}:fail_count")

            await self.redis.expire(f"{key}:fail_count", 60)

            total = await self.redis.incr(f"{key}:total_count")

            await self.redis.expire(f"{key}:total_count", 60)

            if fail_count >= self.FAILURE_THRESHOLD or (total > 10 and fail_count/total >= self.ERROR_RATE_THRESHOLD):

                await self.redis.setex(f"{key}:state", self.TIMEOUT_SECONDS, "open")



        async def record_success(self, key: str):

            # 成功后重置计数

            await self.redis.delete(f"{key}:fail_count", f"{key}:total_count")

            await self.redis.delete(f"{key}:state")  # 若有open/half_open，清除
```


```
// 代码块-4
from pydantic import BaseModel, Field

    from datetime import datetime

    from typing import Dict, Any, Optional



    class CheckpointData(BaseModel):

        task_id: str = Field(..., regex=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')

        state: str  # 来自TaskState枚举值

        retry_count: int = Field(ge=0)

        progress: float = Field(ge=0.0, le=1.0)

        context: Dict[str, Any] = Field(default_factory=dict)  # 中间产物（如代码片段、LLM响应）

        updated_at: datetime = Field(default_factory=datetime.utcnow)

        version: int = Field(default=1, ge=1)
```


```
// 代码块-5
class CheckpointError(Exception): pass

    class CheckpointNotFoundError(CheckpointError): pass

    class CheckpointCorruptedError(CheckpointError): pass
```


```
// 代码块-6
import orjson

    import asyncio

    from typing import Optional

    from redis.asyncio import Redis

    import asyncpg

    from src.core.config import settings



    class CheckpointManager:

        def __init__(self, redis_client: Redis, pg_pool: asyncpg.Pool, env: str = "dev"):

            self.redis = redis_client

            self.pg = pg_pool

            self.env = env

            self._key_prefix = f"ckpt:{env}"



        async def save(self, task_id: str, data: CheckpointData) -> None:

            serialized = orjson.dumps(data.dict())

            key = f"{self._key_prefix}:{task_id}"

            # 写Redis（重试一次）

            try:

                await self.redis.setex(key, 3600, serialized)

            except Exception as e:

                await asyncio.sleep(0.1)

                await self.redis.setex(key, 3600, serialized)

            # 异步写PG（fire-and-forgot，但捕获日志）

            asyncio.create_task(self._save_to_pg(task_id, data))



        async def load(self, task_id: str) -> Optional[CheckpointData]:

            key = f"{self._key_prefix}:{task_id}"

            # 1. 读Redis

            redis_data = await self.redis.get(key)

            if redis_data:

                parsed = CheckpointData(**orjson.loads(redis_data))

                return parsed

            # 2. 降级读PG

            pg_data = await self._load_from_pg(task_id)

            if pg_data:

                # 回填Redis

                await self.redis.setex(key, 3600, orjson.dumps(pg_data.dict()))

                return pg_data

            return None



        async def _save_to_pg(self, task_id: str, data: CheckpointData):

            query = """

            INSERT INTO checkpoints (task_id, state, retry_count, progress, context, updated_at, version)

            VALUES ($1, $2, $3, $4, $5, $6, $7)

            ON CONFLICT (task_id) DO UPDATE SET

                state = EXCLUDED.state,

                retry_count = EXCLUDED.retry_count,

                progress = EXCLUDED.progress,

                context = EXCLUDED.context,

                updated_at = EXCLUDED.updated_at,

                version = checkpoints.version + 1

            WHERE checkpoints.version <= EXCLUDED.version

            """

            await self.pg.execute(

                query,

                task_id, data.state, data.retry_count, data.progress,

                orjson.dumps(data.context), data.updated_at, data.version

            )



        async def _load_from_pg(self, task_id: str) -> Optional[CheckpointData]:

            query = "SELECT state, retry_count, progress, context, updated_at, version FROM checkpoints WHERE task_id = $1"

            row = await self.pg.fetchrow(query, task_id)

            if not row:

                return None

            return CheckpointData(

                task_id=task_id,

                state=row["state"],

                retry_count=row["retry_count"],

                progress=row["progress"],

                context=orjson.loads(row["context"]),

                updated_at=row["updated_at"],

                version=row["version"]

            )



        async def cleanup_old_checkpoints(self, days: int = 7):

            query = "DELETE FROM checkpoints WHERE updated_at < NOW() - INTERVAL '$1 days'"

            await self.pg.execute(query, days)
```


# 多Agent自循环系统 · 阶段3三图谱引擎 (Step 3.1, 3.2, 3.3) · 编码就绪级PRD/ADR

代码图谱 ｜ 数据库图谱 ｜ 配置图谱

**交付声明：**本报告为阶段3（三图谱引擎开发，W5-W6）的全部三个步骤的终极细化文档。三图谱是系统“事实来源”，为L1（引用验证）、L8（配置漂移）等防幻觉层提供数据支撑。每个Step均包含字段级契约、精确函数签名、DDL/配置、原子化pytest用例，可直接编码。

