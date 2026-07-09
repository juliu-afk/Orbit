# 阶段1-PRD-多模态P0-LLM网关集成.md

> 基线文档：`docs/research/Orbit-多模态能力落地方案-2026-07.html`（Part A 模型矩阵 + Part C 落地方案）
> 阶段：P0 — 多模态 LLM 集成 + API 接入验证
> 日期：2026-07-10

---

## 1. 背景

Orbit 是轻量级多 Agent 软件开发自循环系统。当前 `gateway/` 模块（`LLMClient`、`LLMRequest`、ProviderAdapter）**仅支持纯文本**——`prompt: str` 和 `messages: list[dict]` 均不接受图片/视频。

同时，国产多模态模型（Qwen3.7-Plus、GLM-4.1V-Thinking 等）已全面成熟，API 可用，OpenAI 兼容，存在永久免费层。

**核心矛盾**：Orbit Agent 只能"读"代码和日志，无法"看"截图、录屏、设计稿——但软件开发中 80% 的信息载体是视觉的。

## 2. 用户故事

| 优先级 | 角色 | 故事 | 价值 |
|--------|------|------|------|
| **P0** | Orbit Agent | 作为 Agent，我希望在 `LLMRequest` 中传入截图，以便理解 UI bug、设计稿、错误弹窗 | Agent 获得视觉能力的基础设施——不改这个，后面所有 Tool 都做不了 |
| **P0** | Gateway | 作为网关，我希望自动检测 content 类型并路由到正确的多模态模型，以便 Agent 不需要知道模型细节 | 多模态路由是 Agent 能用上视觉模型的前提 |
| **P1** | QA Agent | 作为 QA Agent，我希望调用视频分析模型分析 bug 录屏，以便定位问题 | P1——依赖 P0 的 content array 支持 + P1 的 video_tools.py |
| **P1** | Developer Agent | 作为 Developer Agent，我希望截图 → 生成前端代码，以便加速 UI 开发 | P1——依赖 P0 |
| **P2** | Orbit 用户 | 作为用户，我希望在 Chat 面板直接粘贴截图和视频链接，以便自然地与 Agent 交互 | P2——前端改动量大，不阻塞 P0/P1 |

## 3. 验收标准

### P0 必须实现（3 条）

| # | 标准 | 验证方式 |
|---|------|---------|
| **SC1** | `LLMRequest` 支持 `content` 字段，类型 `str | list[dict]`，list 元素支持 `{"type":"text","text":"..."}` / `{"type":"image_url","image_url":{"url":"..."}}` / `{"type":"video_url","video_url":{"url":"..."}}` | 单元测试——构造 content array → Pydantic 校验通过 |
| **SC2** | `LLMClient.generate()` 自动检测 content 类型：纯文本走现有路由；含 image_url/video_url 走多模态路由 | 集成测试——发送含图片的请求 → 断言路由到 GLM-4.1V 或 Qwen3.7-Plus |
| **SC3** | 多模态 API 接入验证通过：智谱 GLM-4.1V-Flash 和阿里 Qwen3.7-Plus 各完成 1 次实际调用，返回有效分析结果 | 手工验证——发一张截图 → 检查返回内容是否正确描述图片 |

### P1 依赖 P0（不阻塞本次）

| # | 标准 | 说明 |
|---|------|------|
| SC4 | 视频分析——传视频 URL → 模型返回分析结果 | 依赖 video_tools.py（P1） |
| SC5 | 私有化路由——敏感数据自动走 MiniCPM-V | 依赖 sandbox docker-compose（P2） |

## 4. 范围（Non-Goals）

- ❌ **不**在本阶段实现 `watch_video` Tool（P1）
- ❌ **不**在本阶段实现 GUI Agent / Computer Use（P3）
- ❌ **不**在本阶段实现审计截图管线（P2）
- ❌ **不**在本阶段改动前端（Chat 面板多模态输入 → P2）
- ❌ **不**集成 yt-dlp / ffmpeg（P1）
- ❌ **不**实现私有化模型部署（P2）
- ✅ **只做**：Gateway 层扩展——让 Orbit 能调多模态 API

## 5. 待确认问题

1. **Adater 命名**：新建 `VisionAdapter` 还是扩展现有 `OpenAIAdapter`？——倾向新建，改动面小
2. **模型配置位置**：模型路由表放 `client.py` 的 `PRICES` 旁边，还是独立 `multimodal.py`？——倾向独立文件
3. **降级链**：多模态调用失败时降级到另一个多模态模型，还是降级到纯文本模型（丢失视觉信息）？——倾向降级到另一个多模态模型
4. **API Key**：智谱 API Key 已有（`ZAI_API_KEY`），阿里百炼需要新申请——是否先只接智谱，Qwen 后续再加？

## 6. 边缘情况

| 场景 | 预期行为 |
|------|---------|
| content 同时含文本+图片+视频 | 按优先级：视频 → GLM，图片 → Qwen，文本 → 现有路由 |
| 所有多模态模型都失败 | 返回明确错误——不静默降级到纯文本（视觉信息丢失不可接受） |
| 单张图片 >10MB | Pydantic 校验拒绝 + 提示压缩 |
| API 返回非预期格式 | 记录原始响应 → 抛 `MultimodalAPIError` → 上层决策重试/降级 |
| LiteLLM 不支持多模态模型名 | 绕过 LiteLLM，httpx 直连 OpenAI 兼容 endpoint |

## 7. 成功指标

- SC1-SC3 全部通过
- 1 次端到端调用：Agent 说"看看这个截图" → Gateway 路由到 GLM-4.1V → 返回有效图片描述
- 零新增外部依赖（httpx 已有，Pillow 已有）
- 不破坏现有纯文本 LLM 调用路径（回归测试全绿）
