# 08 · 附录 · Appendix

[← 返回目录 Back to index](README.md) · [← 上一章 再开发说明](07-development-guide.md)

---

## 8.1 术语表 · Glossary

| 术语 Term | 含义 Meaning |
|---|---|
| **编排层** Orchestration layer | Orbit 的定位——协调多 Agent，而非单次代码生成 |
| **五图谱** Five-graph system | 代码/数据库/配置/知识/元图谱，Agent 的全局记忆 |
| **元图谱** Meta-graph | 记录五图谱间 12 种跨图谱关系，做影响面分析 |
| **9 层防幻觉** 9-layer defense | L1–L9 纵深验证管道，把错误率压到 <3% |
| **CEGIS** | L5 Z3 形式化的反例引导归纳合成循环（生成→验证→修复→重生成） |
| **检查点** Checkpoint | 状态机关键转换点的快照，用于回滚（Redis 热 + PG 冷） |
| **审计链** Audit trail | `task_audit_trail`，链式记录每步推理，可追溯 |
| **熔断** Circuit breaker | Token/延迟超限即回滚，三态 CLOSED/OPEN/HALF_OPEN |
| **Goal 模式** | 多独立会话编排 + 自主 PR 合入 |
| **Loop 模式** | 定时重复执行 Goal/命令（cron / 自然语言间隔） |
| **三层架构** 3-layer model | L1 系统→Agent / L2 Agent→工具(MCP) / L3 Agent→Agent(A2A) |
| **T1/T2/T3 路由** | 三层模型路由，按任务复杂度选模型（成本/质量平衡） |
| **SCOPE** | evolution 模块的双流记忆机制 |
| **GEPA** | evolution 模块的 Prompt 进化算法 |
| **HITL** Human-in-the-loop | 元认知监控触发的人工干预移交 |
| **Ponytail** | 技术债务台账扫描 |
| **grill-me** | modes 模块的交互协议层（YAML 定义 Agent 行为） |

## 8.2 核心指标基线 · Metric Baselines

| 指标 | 目标 | 来源 |
|---|---|---|
| 调度层延迟 | ≤1500ms（预警 1200ms） | `charter.md:64` |
| 幻觉率 | <3% | `charter.md:65` |
| 幻觉拦截率 | ≥98% | 架构总览:723 |
| CI 覆盖率门禁 | ≥80% | `charter.md:66` |
| 单任务 Token（设计目标） | ≤35 | `charter.md:67` |
| 熔断决策延迟 | ≤12ms | 架构总览:688 |
| 图谱查询延迟 | <50ms | 架构总览:621 |
| L9 合规验证延迟 | P99 <200ms | L9 PRD:12 |
| L9 时效性判断 | ≥95% | L9 PRD:12 |
| L9 告警误报率 | ≤5% | L9 PRD:12 |
| Z3 验证端到端 | 1.87–3.73s（超时 5s） | 架构总览:328 |
| 检查点 RTO | ≤30s | `checkpoint/manager.py` |
| 12 任务项目成本 | 0.012–0.025 元（非高峰） | 架构总览:719 |
| Token 节省 vs V3.1 | 99.4% | 架构总览:733 |

## 8.3 防幻觉层效果速查 · Defense Layer Effectiveness

| 层 | 效果 |
|---|---|
| L1 图谱 | 99% |
| L2 追踪 | 检测 100%，召回 87.6%（F1=0.934），修复 77% |
| L3 熵 | AUROC=0.76，阈值 2.5 bits |
| L5 Z3 | 99%（可证明） |
| L7 沙箱 | 错误率 65%→2%（最优 0%） |
| L9 合规 | 时效性 ≥95%，误报 ≤5% |

## 8.4 路线图 · Roadmap

| 阶段 | Step | 内容 | 状态 |
|---|---|---|---|
| W1–W2 | 0.1–1.2 | 章程/环境/API 契约/图谱 Schema | ✅ |
| W3–W4 | 2.1–2.2 | LiteLLM 网关/检查点 | ✅ |
| W5–W6 | 3.1–3.4 | 图谱引擎 + 知识图谱 | ✅ |
| W7–W8 | 4.1–4.3 | 9 层防幻觉 L1–L9 | ✅ |
| W9–W10 | 5.1–5.7 | 调度器状态机 + Agent 角色 + DAG | ✅ |
| W11–W12 | 6.1–6.3 | 驾驶舱/E2E | ✅ |
| W13 | 7.1–7.5 | 灰度发布 + 可观测性 + DR | ✅ |
| W14+ | 8–10 | 元图谱 + IDE 追赶 + 驾驶舱翻新 | ✅ |
| 当前 | — | 覆盖率冲刺 + 交互协议层 + 自我进化 | 🔄 |

权威更新源：[`docs/产品路线图.md`](../产品路线图.md) · [`docs/已实现功能清单.md`](../已实现功能清单.md)。

## 8.5 原始设计文档索引 · Source Design Docs

本说明书是提炼；研究细节请查原始文档：

| 文档 | 内容 |
|---|---|
| [`docs/charter.md`](../charter.md) | 项目章程（度量基线/范围/风险，"宪法"） |
| [`docs/开发计划_V14.1.md`](../开发计划_V14.1.md) | 总体设计索引（26 章，指向 `docs/开发计划/` 子文档） |
| [`docs/开发计划/00-架构总览.md`](../开发计划/00-架构总览.md) | 架构总览（哲学/防幻觉/图谱/成本） |
| [`docs/三层架构规范.md`](../三层架构规范.md) | 三层边界 + 静态检查规则 |
| [`docs/WORKFLOW.md`](../WORKFLOW.md) | 四阶段开发流程细则 |
| [`docs/PRD+ADR_元图谱.md`](../PRD+ADR_元图谱.md) | 元图谱设计 |
| [`docs/PRD+ADR_Step4.3_L9动态合规验证.md`](../PRD+ADR_Step4.3_L9动态合规验证.md) | L9 合规 |
| [`docs/PRD+ADR_*阶段.md`](../) | 各 Step 逐字段契约（0+1/2/3/4/5/6/7/MVP 阶段） |
| [`docs/SOP-灾难恢复手册.md`](../SOP-灾难恢复手册.md) | 灾难恢复 SOP |
| [`docs/SOP-代码签名.md`](../SOP-代码签名.md) | 代码签名 SOP |
| [`AGENTS.md`](../../AGENTS.md) | 开发哲学 + 实现约束全集 |

## 8.6 关键源文件锚点 · Key Source Anchors

| 主题 | 文件 |
|---|---|
| 启动入口 | [`src/orbit/launcher.py`](../../src/orbit/launcher.py) |
| FastAPI 应用工厂 | [`src/orbit/api/main.py`](../../src/orbit/api/main.py) |
| 元图谱 12 关系 | [`src/orbit/graph/meta_graph.py`](../../src/orbit/graph/meta_graph.py) |
| 防幻觉管道 | [`src/orbit/hallucination/pipeline.py`](../../src/orbit/hallucination/pipeline.py) |
| L9 合规实现 | [`src/orbit/compliance/validator.py`](../../src/orbit/compliance/validator.py) |
| 检查点四级降级 | [`src/orbit/checkpoint/manager.py`](../../src/orbit/checkpoint/manager.py) |
| PyInstaller spec | [`backend/orbit.spec`](../../backend/orbit.spec) |
| 前端路由 | [`frontend/src/router/index.ts`](../../frontend/src/router/index.ts) |

---

[← 返回目录](README.md)

> 本说明书由项目现有文档与源码提炼而成，随版本演进。发现与代码不一致时，以源码 + 章程为准，并请更新本文档对应章节。
</content>
