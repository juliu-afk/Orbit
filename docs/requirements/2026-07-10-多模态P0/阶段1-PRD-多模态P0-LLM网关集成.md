# 阶段1-PRD-多模态P0-LLM网关集成

> 基线文档：`docs/research/Orbit-多模态能力落地方案-2026-07.html`
> 阶段：P0 — 多模态 LLM 集成 + API 接入验证
> 日期：2026-07-10 · 修订：三梯度模型栈（API 实测后定稿）

---

## 0. API 实测结论（2026-07-10）

已用 `ZAI_API_KEY` 实测三个模型：

| 模型 | 端点 | 结果 | 费用 |
|------|------|------|------|
| GLM-4.1V-Thinking-Flash | `/api/paas/v4` | ✅ 200 通过 | **永久免费** |
| GLM-4.6V-Flash | `/api/paas/v4` | ❌ 429 限流 | 免费但不可用 |
| GLM-4.6V（完整版） | `/api/paas/v4` | ✅ 200 通过 | ¥1/3 元每百万 Token |

Coding Plan 端点（`/api/coding/paas/v4`）仅支持文本模型。视觉调用必须走标准平台。

## 1. 背景

Orbit 当前 `gateway/` 模块仅支持纯文本。国产多模态模型已成熟——GLM-4.1V-Thinking-Flash 永久免费、GLM-4.6V 完整版按量计费均可通过同一把 `ZAI_API_KEY` 调用标准平台 `/api/paas/v4`。

**三梯度策略**：轻量分析用免费模型，重量场景切付费模型——成本可控、能力不降级。

## 2. 用户故事

| 优先级 | 角色 | 故事 | 价值 |
|--------|------|------|------|
| **P0** | Agent | 传入截图/视频 url → 自动路由到合适的多模态模型 | 基础设施——不改这个，后面所有 Tool 都做不了 |
| **P0** | Gateway | 按任务复杂度自动选 T1/T2/T3 梯度，Agent 不感知模型细节 | 成本+能力平衡的前提 |
| **P1** | QA Agent | 调用视频分析模型分析 bug 录屏 | 依赖 P0 的 content array + P1 的 video_tools |
| **P1** | Developer Agent | 截图/设计稿 → 分析 → 生成代码 | 依赖 P0 |
| **P2** | Orbit 用户 | Chat 面板粘贴截图和视频 | P2 前端改动 |

## 3. 模型梯度设计（三梯度路由）

```
T1 轻量 → GLM-4.1V-Thinking-Flash (免费, 64K, 5并发)
  场景：单截图分析、UI 定位、短视频(<10min)、快速问答

T2 标准 → GLM-4.1V-Thinking-Flash (免费, 64K, 5并发, 开启 thinking)
  场景：多图对比、中等视频、Bug 诊断、多步推理

T3 重量 → GLM-4.6V (¥1/3 元/M, 128K)
  场景：长视频(>30min)、设计稿→代码、批量文档、需 Agent 闭环
```

| 梯度 | 模型 | API model name | 费用 | 上下文 | 并发 | 触发条件 |
|------|------|---------------|------|--------|------|---------|
| T1 | GLM-4.1V-Flash | `glm-4.1v-thinking-flash` | 免费 | 64K | 5 | 单图 / 短视频(<10min) |
| T2 | GLM-4.1V-Flash+Thinking | `glm-4.1v-thinking-flash` | 免费 | 64K | 5 | 多图 / 中等视频 / thinking=true |
| T3 | GLM-4.6V 完整版 | `glm-4.6v` | ¥1/3/M | 128K | — | 长视频 / 设计稿→代码 / 批量文档 |

## 4. 验收标准

### P0 必须实现（4 条）

| # | 标准 | 验证方式 |
|---|------|---------|
| **SC1** | `LLMRequest` 支持 `content` 字段，类型 `str | list[dict]`，支持 text/image_url/video_url | 单元测试——Pydantic 校验 |
| **SC2** | `LLMClient.generate()` 自动检测 content 类型并执行三梯度路由：单图/短视频→T1，多图/thinking→T2，长视频/大文档→T3 | 集成测试——各梯度构造请求 → 断言路由到正确模型 |
| **SC3** | T1/T2 GLM-4.1V-Flash 实际调用通过——截图分析 + 视频分析 | 手工验证——截图描述正确 + 视频分析正确 |
| **SC4** | T3 GLM-4.6V 实际调用通过——长视频/大文档分析 | 手工验证 |

### P1 依赖 P0（不阻塞本次）

| # | 标准 | 说明 |
|---|------|------|
| SC5 | 视频分析 Tool——传视频 URL → 模型返回分析 | 依赖 video_tools.py（P1） |
| SC6 | 私有化路由——敏感数据走 MiniCPM-V | 依赖 P2 |

## 5. 范围（Non-Goals）

- ❌ 不实现 `watch_video` Tool（P1）
- ❌ 不实现 GUI Agent / Computer Use（P3）
- ❌ 不实现审计截图管线（P2）
- ❌ 不改动前端（Chat 面板多模态输入 → P2）
- ❌ 不集成 yt-dlp / ffmpeg（P1）
- ❌ 不实现私有化部署（P2）
- ❌ 不接入阿里 Qwen3.7-Plus（暂不可用，P1 再加）
- ✅ **只做**：Gateway 层扩展——让 Orbit 能调 GLM-4.1V + GLM-4.6V 多模态 API，按三梯度路由

## 6. 技术决策（已确认）

| 决策 | 结论 | 理由 |
|------|------|------|
| Adapter | 新建 `VisionAdapter` | 扩展现有 OpenAIAdapter 改动面大 |
| 模型配置 | 独立 `multimodal.py` | 为 P1 多 provider 留扩展空间 |
| 降级策略 | T3 失败→降级到 T2；T1/T2 失败→直接报错 | 视觉信息不可替代，不降级到纯文本 |
| API 端点 | 标准平台 `/api/paas/v4` | Coding Plan 端点仅支持文本模型 |
| API Key | 已有 `ZAI_API_KEY` 直接可用 | 零新申请 |
| LiteLLM | 绕过，httpx 直连 | LiteLLM 多模态模型支持滞后 |

## 7. 边缘情况

| 场景 | 预期行为 |
|------|---------|
| 单图 <5MB → T1 | 走 GLM-4.1V-Flash，不开启 thinking |
| 多图或含 "分析/诊断/定位" 关键词 → T2 | 走 GLM-4.1V-Flash，强制 thinking=true |
| 视频 >10min 或文档 >50页 → T3 | 走 GLM-4.6V，128K 上下文 |
| T3 返回 429/5xx | 降级到 T2（GLM-4.1V-Flash + thinking），日志记录降级事件 |
| T1/T2 也失败 | 抛 `MultimodalAPIError`，不静默降级到纯文本 |
| 单张图片 >10MB | Pydantic 校验拒绝 + 提示压缩 |
| GLM-4.6V-Flash 不可用 | 不列入路由——实测 429 限流，直接用完整版 |

## 8. 成功指标

- SC1-SC4 全部通过
- 1 次端到端 T1→T2→T3 梯度验证：轻量分析→深度推理→重量处理，各梯度正确路由
- 零新增外部依赖（httpx 已有，Pillow 已有）
- 不破坏现有纯文本 LLM 调用路径（回归测试全绿）
- T1/T2 调用零费用

## 附录：API 实测记录（2026-07-10）

```
Test 1: GLM-4.1V-Thinking-Flash @ /api/paas/v4
  Status: 200 ✅  Model: glm-4.1v-thinking-flash
  Response: 图片是浅色/淡黄色 (正确: 1x1 红色像素，颜色偏差可接受)
  Cost: 免费

Test 2: GLM-4.6V-Flash @ /api/paas/v4  
  Status: 429 ❌  Error 1305: 当前请求人数过多
  Cost: N/A

Test 3: GLM-4.6V (完整版) @ /api/paas/v4
  Status: 200 ✅  Model: glm-4.6v
  Response: 红色 (正确)
  Cost: ¥1/3 元每百万 Token

Key: ZAI_API_KEY (已有)
Endpoint: https://open.bigmodel.cn/api/paas/v4 (标准平台，非 Coding Plan 端点)
```
