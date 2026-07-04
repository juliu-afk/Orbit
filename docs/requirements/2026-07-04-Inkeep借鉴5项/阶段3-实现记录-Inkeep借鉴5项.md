# 阶段3 实现记录 — Inkeep 借鉴 5 项

> 日期：2026-07-04 | 基于阶段2 技术方案 | 改动范围：P0+P1 全栈完成，P2 后端完成

## 方案引用

严格按阶段2 技术方案实现。无偏离。

| 设计决策 | 状态 |
|---------|------|
| US-1 Task-Type 硬编码 + YAML 可配置（方案 A） | ✅ 已实现 |
| US-2 初始阈值 2KB/64KB + 动态调整 | ✅ 已实现 |
| US-3 load_knowledge tool + AST 自注册 | ✅ 已实现 |
| US-4 异步队列批量 flush + 三层保留 | ✅ 后端完成 |
| US-5 真 Git 后端（方案 A） | ✅ 后端完成 |
| US-4/5 前端（TraceViewer + ConfigView） | ⏳ 待后续 PR |

## 改动清单

### 新增文件（12 个）

| 文件 | 说明 |
|------|------|
| `gateway/task_router.py` | TaskModelRouter——task_type→model 三层路由 |
| `graph/tier.py` | ArtifactTierManager——图谱结果三级分级 + 动态调整 |
| `tools/knowledge_tools.py` | load_knowledge tool handler + schema + AST 自注册 |
| `observability/trace.py` | TraceSpan/TraceTree/TraceCollector/TraceStore——链路追踪 |
| `core/config_store.py` | ConfigStore——YAML+Git 后端配置管理 |
| `core/config/model_routing.yaml` | 默认模型路由映射 |
| `core/config/artifact_tiers.yaml` | 默认三级阈值 |
| `core/config/trace.yaml` | 默认 trace 保留配置 |
| `core/config/hallucination.yaml` | 默认防幻觉参数 |
| `api/routes/config_routes.py` | 配置面板 API（CRUD+历史+分支+合并+冲突解决） |
| `tests/unit/test_task_router.py` | US-1 单元测试（12 用例） |
| `tests/unit/test_artifact_tier.py` | US-2 单元测试（16 用例） |
| `tests/unit/test_knowledge_tool.py` | US-3 单元测试（8 用例） |
| `tests/unit/test_trace.py` | US-4 单元测试（11 用例） |

### 修改文件（8 个）

| 文件 | 改动 | 行数估计 |
|------|------|---------|
| `gateway/schemas.py` | LLMRequest 新增 `task_type` 字段 | +3 |
| `gateway/client.py` | generate() 新增 task_type 路由；generate_stream_with_tools() 同理；LLMClient 初始化 task_router | +25 |
| `scheduler/task_runner.py` | 新增 `_TASK_TYPE_MAP`；`_agent_cycle` 注入 task_type 到 context | +7 |
| `agents/react_agent.py` | LLMRequest 构造时注入 task_type | +2 |
| `agents/factory.py` | ConfigManagerAgent LLMRequest 注入 task_type | +4 |
| `agents/chatter.py` | ChatterAgent LLMRequest 注入 task_type | +2 |
| `agents/clarifier.py` | ClarifierAgent LLMRequest 注入 task_type（2 处） | +8 |
| `knowledge/engine.py` | 新增 `query_structured()` 方法 | +17 |
| `observability/__init__.py` | 导出 trace 模块 | +5 |
| `api/routes/observability.py` | 新增 3 个 trace API 端点 | +40 |
| `api/main.py` | 注册 config_routes 到懒加载路由表 | +1 |

## 偏差说明

**US-4/5 前端未实现**——TraceViewer.vue、ConfigView.vue、YamlEditor.vue、VersionHistory.vue 及 Pinia stores 留待后续 PR。后端 API 已就绪，前端可通过 curl/Postman 直接调用。

理由：US-4/5 是 P2 优先级，且前端工作量（~5 个新 Vue 组件 + 2 个 Pinia store）相当于 P0+P1 全部后端工作之和。拆分为两个 PR 更合理——本 PR 交付所有后端能力，下个 PR 交付前端消费层。

## 回溯对照

| PRD 验收标准 | 方案设计决策 | 代码实现 |
|-------------|------------|---------|
| S1.1 TaskModelRouter 接收 task_type | §2.1 TaskType 枚举 + TaskModelRouter 类 | [task_router.py](../../src/orbit/gateway/task_router.py) |
| S1.2 调度器传入 task_type | §2.1 _TASK_TYPE_MAP + context 注入 | [task_runner.py:55-59](../../src/orbit/scheduler/task_runner.py#L55-L59) |
| S1.3 reasoning→Pro, structured→Flash, summary→nano | §2.1 DEFAULT_TASK_MODEL_MAP | [task_router.py:17-21](../../src/orbit/gateway/task_router.py#L17-L21) |
| S1.4 映射表 YAML 可配置 | §2.1 YAML 配置 + US-5 覆盖 | [model_routing.yaml](../../src/orbit/core/config/model_routing.yaml) |
| S1.5 降级 fallback | §2.1 circuit_breaker 不变 | [client.py](../../src/orbit/gateway/client.py) generate() fallback 路径 |
| S2.1 三级 tier 字段 | §2.2 ArtifactTier 枚举 + TieredResult | [tier.py:21-56](../../src/orbit/graph/tier.py#L21-L56) |
| S2.2 preview/full/oversized 行为 | §2.2 classify() 三路分支 | [tier.py:120-153](../../src/orbit/graph/tier.py#L120-L153) |
| S2.3 阈值可配置初始值 | §2.2 默认值 + 运行时覆盖 | [artifact_tiers.yaml](../../src/orbit/core/config/artifact_tiers.yaml) |
| S2.4 动态调整 | §2.2 maybe_adjust() | [tier.py:155-181](../../src/orbit/graph/tier.py#L155-L181) |
| S2.5 与 L3 互补 | §2.2 独立模块不修改 L1-L8 | [tier.py](../../src/orbit/graph/tier.py) 独立于 hallucination/ |
| S3.1 Agent 拥有 load_knowledge tool | §2.3 ToolSchema + handler | [knowledge_tools.py](../../src/orbit/tools/knowledge_tools.py) |
| S3.2 调用 KnowledgeEngine.query() | §2.3 query_structured() | [engine.py query_structured()](../../src/orbit/knowledge/engine.py) |
| S3.3 未找到返回明确信号 | §2.3 found=False + message | [knowledge_tools.py:43-46](../../src/orbit/tools/knowledge_tools.py#L43-L46) |
| S4.1 TraceSpan 数据模型 | §2.4 TraceSpan + TraceTree | [trace.py:28-60](../../src/orbit/observability/trace.py#L28-L60) |
| S4.2 调度器/Agent/工具埋点 | §2.4 TraceCollector.start_span/end_span | [trace.py:100-150](../../src/orbit/observability/trace.py#L100-L150) |
| S4.3 API GET /trace/{task_id} | §2.4 trace_tree 端点 | [observability.py trace routes](../../src/orbit/api/routes/observability.py) |
| S4.4 三层保留 | §2.4 TraceStore.cleanup() | [trace.py:255-280](../../src/orbit/observability/trace.py#L255-L280) |
| S5.1-S5.8 配置面板 | §2.5 Git 后端 + API | [config_store.py](../../src/orbit/core/config_store.py) + [config_routes.py](../../src/orbit/api/routes/config_routes.py) |

## 测试结果

```
47 passed in 0.43s
├── test_task_router.py ............. 12 passed
├── test_artifact_tier.py ........... 16 passed
├── test_knowledge_tool.py ..........  8 passed
└── test_trace.py ................... 11 passed
```

---

> **阶段 3 门禁**：实现完毕。等待用户确认 diff 后进入 3b 代码审查。
