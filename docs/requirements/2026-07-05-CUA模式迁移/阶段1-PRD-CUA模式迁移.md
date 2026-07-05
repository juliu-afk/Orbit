# 阶段 1 PRD — CUA 架构模式迁移

> 日期：2026-07-05 | 来源：三大 CUA 项目源码解构分析
> 完整报告：`docs/research/CUA项目源码解构——Orbit可借鉴模式分析.html`

## 1. 背景

三大 CUA 项目（OpenAI CUA Sample App / trycua/cua / OpenCUA）本质是"AI 操作 GUI"——
截图→识别像素→点击(x,y)→键盘输入。Orbit 操作对象是代码和文本，不需要 GUI 控制能力。

但它们的 Agent 架构设计模式可迁移到 Orbit。WB 于 2026-05-31 完成三大项目源码解构，
Claude 于 2026-07-05 完成 Orbit 适配分析，识别出 5 个可借鉴模式。

## 2. 用户故事

| # | 故事 | 优先级 | 批次 |
|---|------|:--:|:--:|
| US1 | 作为调度器开发者，我希望 Agent 循环有工具级超时和防抖延迟，防止单步卡死和连续操作竞态 | P0 | A |
| US2 | 作为防幻觉层维护者，我希望 L2/L4/L5 验证引入"反思式自述预期→对比实际"模式，降低误判率 | P0 | A |
| US3 | 作为 Orbit 用户，我希望 Orbit 能通过 MCP 协议双向对接外部 Agent/工具生态，不被自研协议锁定 | P1 | B |
| US4 | 作为 Orbit 运维，我希望审计数据能周期性分析并反馈到调度/prompt/阈值调优 | P1 | B |
| US5 | 作为沙箱使用者，我希望沙箱支持自定义镜像（BYOI）和更完善的降级策略 | P2 | B |

## 3. 具体模式

### Phase A（本次迭代）—— US1 + US2

#### US1 — Agent 循环鲁棒性增强（来源：OpenAI CUA Sample App）

OpenAI 的 `responses-loop.ts`（~500 行）展示了 Agent 循环的工程化最佳实践。

**当前状态**：[task_runner.py](../src/orbit/scheduler/task_runner.py#L167) `_agent_cycle` 无工具级超时，无动作间延迟，无循环上限。

**改进点**：
1. **工具级超时**：每个 Agent 工具调用设独立硬超时（默认 20s），超时即抛 `ToolTimeoutError` 并记录 audit
2. **动作间延迟**：关键步骤间插入 120ms 防抖——防止文件系统未刷盘、状态未同步
3. **关键步骤串行化**：CODING 状态写文件时强制 `parallel_tool_calls: false`，避免并发编辑冲突
4. **循环硬上限**：Agent 循环加硬上限（默认 50 轮），超限自动终止 → `FAILED`

**影响模块**：`scheduler/task_runner.py`、`scheduler/dag_runner.py`

#### US2 — 反思式 CoT Prompt（来源：OpenCUA）

OpenCUA 核心创新：不让模型直接"看→做"，而是"看→**想**→做→**反思**"。
每步动作前生成：① 反思前一步 ② 解释当前选择 ③ 考虑替代 ④ 预测下一步状态。

**当前状态**：
- [l2_dynamic.py](../src/orbit/hallucination/l2_dynamic.py) 追踪函数调用→对照图谱验证，无"自述预期"
- [l5_z3.py](../src/orbit/hallucination/l5_z3.py) 形式化验证 pre/post-condition，无"Agent 自预测"
- L4 沙箱执行：执行代码→检查结果，无"Agent 预判行为"

**改进点（三层都改）**：
1. **L2 动态追踪增强**：沙箱执行前让 Agent 预测"将调用哪些函数"→ 执行后对比预测 vs 实际 → 偏差越大越可能是幻觉。新增 `predicted_calls` / `actual_calls` / `deviation_score` 字段
2. **L4 沙箱执行增强**：Agent 生成代码时附带自述"此代码预期行为"→ 沙箱实际执行 → 对比"预期输出 vs 实际输出"→ 矛盾即幻觉信号
3. **L5 Z3 合约增强**：Agent 生成代码时附带自述"此代码满足什么契约"→ Z3 验证自述契约 vs 实际代码 → 矛盾即幻觉信号

**不新增防幻觉层**——修改现有 L2/L4/L5 的 prompt 模板和验证逻辑。

**影响模块**：`hallucination/l2_dynamic.py`、`hallucination/l4_type.py`、`hallucination/l5_z3.py`、`hallucination/schemas.py`

### Phase B（后续迭代）—— US3 + US4 + US5

#### US3 — MCP 协议双向适配层（来源：trycua/cua）

trycua 通过 MCP over stdio 与 Claude Code/Cursor/Codex 通信，证明了 MCP 在 Agent-工具通信中的生态优势。

**改进点**：
- `communication/` 新增 `mcp_adapter.py`——MCP 协议序列化/反序列化
- Orbit 自研协议 ↔ MCP 协议**双向转换**
- Orbit Agent 可调用外部 MCP 工具，外部 MCP Agent 可调用 Orbit 工具
- 参考 trycua 的 `cua-driver mcp` 模式

**影响模块**：`communication/`（新增文件）、`tools/registry.py`

#### US4 — 审计数据飞轮（来源：OpenCUA）

OpenCUA 的"收集→处理→训练→评估→反馈"闭环，Orbit 不做模型训练，但可借鉴数据分析→参数调优闭环节。

**改进点**：
- `observability/trajectory.py`——结构化轨迹收集
- `observability/feedback.py`——周期性审计分析：失败率/误判率/效率指标
- 反馈到：Prompt 模板优化、调度策略参数调整、防幻觉阈值校准

**影响模块**：`observability/`（新增文件）、`scheduler/orchestrator.py`

#### US5 — 沙箱 BYOI + 降级策略（来源：trycua/cua）

trycua 的 `Sandbox.ephemeral(Image.custom("my-image"))` 一套 API 适配多平台。

**改进点**：
- BYOI：允许任务配置中指定 Docker 镜像
- 降级链：Docker → ProcessSandbox（已有）→ 只读分析模式（新增）
- 参考 trycua 的统一沙箱抽象 API

**影响模块**：`sandbox/executor.py`、`sandbox/sandbox_factory.py`

## 4. 验收标准

### Phase A（本次迭代）

| # | 标准 | 对应 US |
|---|------|:--:|
| AC1 | `_agent_cycle` 每次工具调用有独立超时，超时后触发 `ToolTimeoutError` 并记录 audit | US1 |
| AC2 | CODING 状态写文件操作串行化，`parallel_tool_calls` 强制 false | US1 |
| AC3 | Agent 循环超过 50 轮自动终止，状态 `FAILED`，audit 记录 `max_cycles_exceeded` | US1 |
| AC4 | 关键步骤间（写文件→跑测试）插入 120ms 防抖延迟 | US1 |
| AC5 | L2 验证报告新增 `predicted_calls` / `actual_calls` / `deviation_score` 字段 | US2 |
| AC6 | L4 沙箱执行新增 `predicted_behavior` vs `actual_behavior` 对比 | US2 |
| AC7 | L5 验证新增 `self_claimed_contract` vs `z3_verified_contract` 对比 | US2 |
| AC8 | 三层增强后防幻觉误判率不上升（现有测试全通过） | US2 |

### Phase B（后续迭代）

| # | 标准 | 对应 US |
|---|------|:--:|
| AC9 | `communication/mcp_adapter.py` 实现 MCP 协议双向转换 | US3 |
| AC10 | Orbit Agent 可调用外部 MCP 工具（端到端验证） | US3 |
| AC11 | `observability/feedback.py` 输出 ≥3 类改进建议（失败率/误判率/效率） | US4 |
| AC12 | 沙箱支持自定义镜像，降级链 Docker→Process→ReadOnly 完整 | US5 |

## 5. Non-Goals

- 不新增防幻觉层（L10）——只增强现有 L2/L4/L5
- 不实现完整 MCP Server——只做协议适配转换层
- 不实现模型训练——反馈是参数调整，不是 fine-tuning
- 不实现桌面操作/截图/鼠标点击——Orbit 不需要 CUA 核心能力

## 6. 成功指标

| 指标 | 当前 | 目标 |
|------|:--:|:--:|
| Agent 循环卡死率 | ~3%（估算） | <1% |
| 防幻觉 L2/L4/L5 误判率 | 无基线 | 有基线 + 反思式 CoT 比无 CoT 误判率低 ≥10% |
| 调度器工具超时覆盖率 | 0% | 100%（所有工具调用有超时） |

## 7. 决策记录

| 决策 | 结论 |
|------|------|
| 分批策略 | Phase A（US1+US2）先做，Phase B（US3-5）后续 |
| MCP 适配深度 | 双向转换完整实现（非单向） |
| 反思式 CoT 覆盖 | L2 + L4 + L5 三层全做 |
