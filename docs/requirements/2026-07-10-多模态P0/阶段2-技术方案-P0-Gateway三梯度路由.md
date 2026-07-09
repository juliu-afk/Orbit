# 阶段2-技术方案-多模态P0-Gateway三梯度路由

> 基线：阶段1 PRD v2（API 实测定稿）· 4 条验收标准 · 2026-07-10
> 本次技术方案覆盖 SC1-SC4，无偏离。

---

## 1. PRD 验收标准 → 技术方案对照

| # | PRD 标准 | 技术实现 | 状态 |
|---|---------|---------|------|
| SC1 | `LLMRequest` 支持 `content: str \| list[dict]` | `schemas.py`：新增 `ContentBlock` 联合类型 + `LLMRequest.content` 字段 | 覆盖 |
| SC2 | 三梯度路由：单图→T1, 多图→T2, 长视频→T3 | `multimodal.py`：`TierRouter` 根据 content 分析 + `tier` 参数选模型 | 覆盖 |
| SC3 | T1/T2 GLM-4.1V-Flash 调用通过 | `adapters/vision.py`：`VisionAdapter` httpx 直连 `/api/paas/v4`，返回 `LLMResponse` | 覆盖 |
| SC4 | T3 GLM-4.6V 调用通过 | 同上，model=`glm-4.6v`，128K 上下文 | 覆盖 |

## 2. API / 数据模型设计

### 2.1 LLMRequest 扩展（schemas.py）

```python
# 新增类型
from pydantic import BaseModel, Field
from typing import Literal

class TextContent(BaseModel):
    type: Literal["text"] = "text"
    text: str

class ImageContent(BaseModel):
    type: Literal["image_url"] = "image_url"
    image_url: dict  # {"url": "https://..." | "data:image/...;base64,..."}

class VideoContent(BaseModel):
    type: Literal["video_url"] = "video_url"
    video_url: dict  # {"url": "https://..."}

ContentBlock = TextContent | ImageContent | VideoContent

# LLMRequest 修改
class LLMRequest(BaseModel):
    prompt: str = Field(...)
    content: str | list[dict] | None = Field(  # ← 新增
        None, description="多模态 content array（OpenAI 兼容格式）。为 None 时走现有纯文本路径"
    )
    tier: int | None = Field(                   # ← 新增
        None, description="手动指定梯度（1/2/3）。None=自动检测"
    )
    # 以下字段不变
    system_prompt: str = ...
    temperature: float = 0.2
    max_tokens: int = 2048
    tools: list[dict] | None = None
    messages: list[dict] | None = None
    ...
```

### 2.2 三梯度路由配置（multimodal.py）

```python
from dataclasses import dataclass
from enum import IntEnum

class Tier(IntEnum):
    LIGHT = 1    # 免费，单图/短视频
    STANDARD = 2 # 免费+thinking，多图/中等视频
    HEAVY = 3    # 付费，长视频/设计稿/批量文档

@dataclass
class TierConfig:
    model: str
    endpoint: str               # api_base
    max_tokens: int
    thinking: bool | None       # None = 使用模型默认
    cost_per_million: float     # 元/百万 tokens，0=免费

TIERS: dict[Tier, TierConfig] = {
    Tier.LIGHT: TierConfig(
        model="glm-4.1v-thinking-flash",
        endpoint="https://open.bigmodel.cn/api/paas/v4",
        max_tokens=4096,
        thinking=None,           # auto——信任模型判断
        cost_per_million=0.0,    # 免费
    ),
    Tier.STANDARD: TierConfig(
        model="glm-4.1v-thinking-flash",
        endpoint="https://open.bigmodel.cn/api/paas/v4",
        max_tokens=8192,
        thinking=True,           # 强制开启——深度推理
        cost_per_million=0.0,    # 免费
    ),
    Tier.HEAVY: TierConfig(
        model="glm-4.6v",
        endpoint="https://open.bigmodel.cn/api/paas/v4",
        max_tokens=8192,
        thinking=None,
        cost_per_million=4.0,    # ¥1+3=4 元/M (sum)
    ),
}
```

### 2.3 VisionAdapter（adapters/vision.py）

```python
class VisionAdapter:
    """多模态 HTTP 适配器——httpx 直连 OpenAI 兼容端点。

    WHY 不用 LiteLLM：LiteLLM 多模态模型支持滞后（GLM-4.1V 未收录、GLM-4.6V 部分支持）。
    用 httpx 直连标准平台 /api/paas/v4，OpenAI 兼容协议，零中间层。

    WHY 独立 adapter 而非扩展 OpenAIAdapter：
    - 多模态请求的 payload 格式不同（content array vs string prompt）
    - 计费/降级逻辑独立于文本模型
    - P1 多 provider 时更容易扩展
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=60.0)

    async def generate(
        self, config: TierConfig, content: list[dict], prompt: str,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """发送多模态请求，返回统一 LLMResponse。"""
        messages = [{
            "role": "user",
            "content": [
                *content,
                {"type": "text", "text": prompt},
            ]
        }]
        body = {
            "model": config.model,
            "messages": messages,
            "max_tokens": max_tokens or config.max_tokens,
        }
        if config.thinking is not None:
            body["thinking"] = {"type": "enabled"}  # GLM-4.6V thinking 参数

        resp = await self._client.post(
            f"{config.endpoint}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        # → LLMResponse
```

## 3. 数据流

```
Agent 调用 LLMClient.generate(req)
    │
    ├─ req.content is None → 现有纯文本路径（不改动）
    │
    └─ req.content is not None → 多模态路径（新增）
        │
        ├─ 1. TierRouter.classify(req.content, req.tier)
        │      · 检测 content 类型（image/video/text 数量）
        │      · req.tier 显式指定 → 直接使用
        │      · None → 自动判定：
        │        - 单图/短视频 → Tier.LIGHT
        │        - 多图/"分析"关键词 → Tier.STANDARD
        │        - 长视频/大文档 → Tier.HEAVY
        │
        ├─ 2. VisionAdapter.generate(config, content, prompt)
        │      · POST {endpoint}/chat/completions
        │      · 成功 → LLMResponse(content, usage, cost)
        │      · 失败 →
        │        - Tier.HEAVY 失败 → 降级 Tier.STANDARD（记录降级事件）
        │        - Tier.STANDARD 失败 → MultimodalAPIError（不降级到纯文本）
        │
        └─ 3. 返回 LLMResponse（含 usage + cost 追踪）
```

## 4. LLMClient.generate() 改动点（client.py）

```python
# 在 generate() 方法开头增加多模态分支
async def generate(self, req: LLMRequest, ...) -> LLMResponse:
    # 新增：多模态检测
    if req.content is not None:
        return await self._generate_multimodal(req, task_id)

    # 以下为现有纯文本逻辑——不变
    ...
```

最小侵入——只在入口加一个 `if` 分支，现有 200+ 行纯文本逻辑零改动。

## 5. 调度器状态变更

**N/A。** P0 仅涉及 Gateway 层，不触及 `scheduler/`。Agent 调用 LLMClient 的接口不变（`generate(req, task_id, ...)` → `LLMResponse`），调度器无感知。

## 6. 防幻觉层影响

**N/A。** 防幻觉层（L1-L8）作用于 Agent 输出验证和代码生成，不拦截 LLM API 调用。多模态请求经过现有 L1-L8 pipeline 时，L4 类型检查可能遇到新格式（content array），但 Pydantic 已做第一层校验，L4 不受影响。

## 7. 图谱 Schema 变更

**N/A。** 不涉及数据库。

## 8. 边界 case 清单

| # | 场景 | 预期行为 | 验证方式 |
|---|------|---------|---------|
| C1 | content 为 `str`（向后兼容） | 视为纯文本 prompt，走现有路径 | 单元测试 |
| C2 | content 为 `[{"type":"text",...}]` | 视为纯文本，走现有路径 | 单元测试 |
| C3 | content 含 `image_url`（HTTP URL） | 检测→T1 | 集成测试 |
| C4 | content 含 `image_url`（base64 data URI） | 同 C3 | 集成测试 |
| C5 | content 含 `video_url` | 检测→T2（默认开 thinking） | 集成测试 |
| C6 | content 含 3 张以上图片 | 检测→T2 | 集成测试 |
| C7 | content 含视频且时长 >10min | 检测→T3 | 集成测试 |
| C8 | req.tier=3 显式指定 | 直接走 T3，跳过自动检测 | 单元测试 |
| C9 | T3 返回 429 | 降级 T2，日志记录降级事件 | 集成测试 |
| C10 | T2 返回 429 | 抛 `MultimodalAPIError` | 集成测试 |
| C11 | 图片 >10MB | Pydantic `field_validator` 拒绝 | 单元测试 |
| C12 | API 返回非 200/非 JSON | 抛 `MultimodalAPIError` + 原始文本 | 集成测试 |
| C13 | content 含不支持的 type（如 `audio`） | Pydantic 校验拒绝 | 单元测试 |
| C14 | content 和 prompt 同时存在 | 合并——content 在前，prompt text 追加在末尾 | 单元测试 |
| C15 | 并发 5 个 T1 请求 | VisionAdapter 正常处理（5 并发在 GLM-4.1V 限制内） | 手工 |

## 9. 风险与缓解

| # | 风险 | 影响 | 概率 | 缓解 |
|---|------|------|------|------|
| R1 | **GLM-4.1V-Flash 从免费变收费** | T1/T2 产生费用 | 低（智谱承诺永久免费） | T1/T2 默认免费，PRICES 表中标记 `cost_per_million=0`。如收费，改配置即可 |
| R2 | **GLM-4.6V 单次费用高**（128K 满上下文可能 ¥0.5-1/次） | 高频使用 T3 成本累积 | 中 | T3 仅在长视频/设计稿→代码时触发，非默认。用量监控 + 月度成本告警 |
| R3 | **VisionAdapter 绕过 LiteLLM，失去统一成本追踪** | 多模态成本不入 LiteLLM 账本 | 中 | VisionAdapter 自己返回 `LLMUsage(cost_usd=...)`, workload 层合并 |
| R4 | **httpx 直连不经过熔断器** | 故障时无自动熔断 | 中 | P0 手动重试（T3→T2 降级）。P1 将 VisionAdapter 接入 CircuitBreaker |
| R5 | **标准平台 API 不稳定**（免费模型 429） | T1/T2 偶发限流 | 低（实测 T1/T2 通过，GLM-4.6V-Flash 429 已排除） | 降级到 T2（更高 max_tokens）。持续 429 → 告警 |

## 10. 依赖链

### 内部模块依赖
```
新增：
  gateway/multimodal.py   → 无内部依赖（纯数据类）
  gateway/adapters/vision.py → gateway/schemas.py (LLMResponse, LLMUsage)
                              → core/config.py (settings.ZAI_API_KEY)

修改：
  gateway/schemas.py      → 无（Pydantic 自包含）
  gateway/client.py       → gateway/multimodal.py (TierRouter)
                          → gateway/adapters/vision.py (VisionAdapter)
```

### 外部依赖
```
httpx  → 已有（Orbit 依赖链中已存在）
Pillow → 已有
None 新增外部依赖
```

### API Key
```
ZAI_API_KEY → 已有（settings.ZAI_API_KEY），零新申请
```

## 11. 文件改动汇总

| 文件 | 操作 | 预估行数 | 复杂度 |
|------|------|---------|--------|
| `src/orbit/gateway/schemas.py` | 修改 | +40 | 低（Pydantic 类型扩展） |
| `src/orbit/gateway/multimodal.py` | **新建** | ~120 | 中（路由逻辑 + 配置） |
| `src/orbit/gateway/adapters/vision.py` | **新建** | ~150 | 中（HTTP 适配器 + 错误处理） |
| `src/orbit/gateway/adapters/__init__.py` | 修改 | +3 | 低 |
| `src/orbit/gateway/client.py` | 修改 | +30 | 低（入口 if 分支） |
| **合计** | 2 新 + 3 改 | ~343 | 0.5 周 |

## 12. 测试策略

| 层 | 用例 | 覆盖 |
|----|------|------|
| 单元 | `test_content_schema.py`——ContentBlock 校验、拒绝超大图片、拒绝不支持类型 | SC1 + C11/C13/C14 |
| 单元 | `test_tier_router.py`——自动检测各梯度、手动 tier 指定 | SC2 + C3-C8 |
| 集成 | `test_vision_adapter.py`——T1/T2/T3 实际调用、429 降级、非 200 错误 | SC3/SC4 + C9/C10/C12 |
| 回归 | 现有纯文本测试全绿——证明 generate() 改动不影响现有路径 | C1/C2 |
