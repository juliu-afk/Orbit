# 阶段 1 PRD —— 测试-审查联动体系建设

> 基于：[Orbit测试审查联动研究.html](../../research/Orbit测试审查联动研究.html)（6 篇论文 + 4 家公司 + Orbit 45 模块审计）
> 关联：[Agent测试自循环 PRD](../2026-07-07-Agent测试自循环/阶段1-PRD-Agent测试自循环.md)（另一个会话，已确认）
> 开发计划：[11-Agent测试自循环.md](../../开发计划/11-Agent测试自循环.md) §九

---

## 一、背景与问题

### 1.1 是什么驱动了这次需求

1. **Orbit 审查架构审计**：4 层审查体系设计完整，但存在 3 个断点——已实现的模块之间没有连线
2. **测试-审查联动研究**：学术界 6 篇论文 + 工业界 4 家公司实践全部支持"测试和审查联动能提速 ~60%、提质 ~50%"
3. **Agent 测试自循环 PRD**（另一个会话）：12 条 AC 中 9 条有外部验证，但审查→测试回灌闭环（AC14）缺失
4. **渐进式审查概念**：PRD→ADR→代码三列对照可提速审查、减少遗漏——Orbit 有 RUNE 模式作为微观实现，缺跨阶段对比引擎

### 1.2 现状

Orbit 已有 5 层审查相关能力：

| 层 | 模块 | 成熟度 | 问题 |
|----|------|--------|------|
| 方法论注入 | `compose/skills/review.md` | 高 | 缺与 testing/ 的联动指令 |
| 交互协议 | `modes/review/` | 中 | checklist.md 含恪现遗留的财务/会计维度 |
| 引擎+持久化 | `review/` (service + models + ponytail) | 中 | 状态机完整但从未被编排器调用 |
| 编排门禁 | `compose/orchestrator.py` | 中 | _code_review() 自做简化检查，跳过审查引擎 |
| 测试联动 | `testing/orchestrator.py` | 高 | CrossReport 框架已有，但 Ponytail 未并入、审查可选 |

### 1.3 核心问题清单

| # | 问题 | 类型 | 影响 |
|---|------|------|------|
| S1 | ComposeOrchestrator._code_review() 不调 ReviewService | 断点 | 审查状态机空转，ReviewDecision 表无数据 |
| S2 | modes/review/checklist.md 检查无关维度，漏 Orbit 特有维度 | 断点 | 审查 Agent 在错误维度上浪费注意力 |
| S3 | Ponytail 过度工程检测结果不进 CrossReport | 断点 | 人类看不到"这个类只有一个方法"等警告 |
| S4 | 审查可选——无 review_service 时跳过 | 断点 | CrossReport 可能只有测试结论、没有审查结论 |
| M1 | 审查发现 → 测试回灌闭环缺失 | 缺口 | 审查发现了问题，但没有自动生成防回归测试 |
| M2 | 渐进式审查引擎缺失 | 缺口 | PRD/ADR/代码三阶段各有一套预期提取，但不对照 |
| M3 | 测试↔审查双向信息推送未实现 | 缺口 | PRD 5.5b 设计了协议但未实现 |
| M4 | TestGapDetector 有检测无排序 | 缺口 | 列出缺口但不告诉你哪个最危险 |
| M5 | ReviewDecision 缺少 severity 字段 | 缺口 | 无法区分"致命问题"和"命名建议" |

---

## 二、用户故事

### Batch A — 断点修复（P0，零风险）

| # | 用户故事 | 验收标准 |
|---|---------|---------|
| US-A1 | 作为 Orbit 开发者，我希望 _code_review() 真正调用 ReviewService，审查状态机不再空转 | _code_review() 调用 ReviewService；审查结果写入 review_decisions 表 |
| US-A2 | 作为 Orbit 用户，我希望审查清单覆盖 Orbit 特有关注点，不检查无关维度 | checklist.md 含调度器/防幻觉/图谱/沙箱 4 维度；不含财务/会计 |
| US-A3 | 作为 Orbit 用户，我希望 Ponytail 过度工程检测结果出现在 CrossReport 中 | CrossReport 包含 Ponytail 发现；摘要卡片展示警告数 |
| US-A4 | 作为 Orbit 用户，我希望审查永不静默跳过——至少 Ponytail 静态审查兜底 | 无 review_service → 自动回退 Ponytail → CrossReport 至少一个审查维度 |

### Batch B — 能力增强（P1，小幅新增）

| # | 用户故事 | 验收标准 |
|---|---------|---------|
| US-B1 | 作为 Orbit 用户，我希望审查发现的严重问题自动生成回归测试，防止同类 bug 重现 | severity ≥ major 的 ReviewDecision → 自动生成 test_regression_xxx → 保存到 tests/regression/ → 后续 CI 执行 |
| US-B2 | 作为 Orbit 用户，我希望 PRD 和技术方案阶段提取的预期在代码阶段自动对照，不再依赖审查者记忆 | Spec.tasks 展开为 ReviewCheckpoint → PRD+ADR 预期填充左/中列 → 代码阶段填右列 → 生成"预期 vs 实际"对照报告 |
| US-B3 | 作为 Orbit 用户，我希望测试 Agent 和审查 Agent 在运行时互相推送发现，而不是各自独立出报告 | 测试→审查推送覆盖率低分支；审查→测试推送缺失测试点；CrossReport 中交叉验证条目标注推送来源 |
| US-B4 | 作为 Orbit 用户，我希望测试缺口按风险排序，优先看最危险的缺口 | TestGapDetector 引入代码中心度 + 改动复杂度 + 静态分析发现数加权 → 缺口按风险分排序 |
| US-B5 | 作为 Orbit 开发者，我希望 ReviewDecision 能区分致命/严重/一般，配套 compose/skills/review.md 已有的 severity 体系 | ReviewDecision 新增 severity 字段（critical/major/minor）；API 和 CrossReport 同步支持 |

---

## 三、验收标准总表

| # | 验收标准 | 对应 US | 量化指标 | Batch |
|---|---------|--------|---------|-------|
| AC1 | _code_review() 调用 ReviewService，状态转换完整 | US-A1 | 每次 spec 执行 → 1 条 Review + N 条 ReviewDecision | A |
| AC2 | checklist.md 含调度器/防幻觉/图谱/沙箱 4 维度 | US-A2 | 每维度 ≥3 条检查项；0 条财务/会计维度 | A |
| AC3 | Ponytail 发现出现在 CrossReport 中 | US-A3 | PonytailFinding → CrossValidation 映射率 100% | A |
| AC4 | 审查永不静默跳过 | US-A4 | 无 review_service → Ponytail 兜底；CrossReport 审查维度条目 ≥0 | A |
| AC5 | 审查发现 severity ≥ major → 自动生成 regression 测试 | US-B1 | 生成率 100%；生成测试在 CI 中通过率 ≥90% | B |
| AC6 | Spec 执行时自动展开 ReviewCheckpoint 三列对照表 | US-B2 | 每个 Spec.task 展开 ≥1 条检查点；代码阶段右列填充率 100% | B |
| AC7 | 测试和审查运行时通过 asyncio.Queue 双向推送 | US-B3 | 推送事件记录在 CrossValidation.source 字段 | B |
| AC8 | 测试缺口按风险分排序展示 | US-B4 | 排序因子 ≥3 个；高风险缺口排在前 20% | B |
| AC9 | ReviewDecision.severity 字段可用 | US-B5 | 创建/查询/CrossReport 均支持 severity | B |
| AC10 | 改动不引入新外部依赖 | — | 0 新 PyPI/npm 依赖 | A+B |

---

## 四、Non-Goals（本次不做）

| # | Non-Goal | 理由 |
|---|---------|------|
| 1 | 不改动前端 UI | CrossReport 卡片已有，新字段自然融入现有结构。新 UI 在 Agent 测试自循环 Phase 4 统一做 |
| 2 | 不实现 AB 进化式策略选择（L1-L3） | 长期差异化能力，需先积累 AB 数据 |
| 3 | 不实现 Dodgy Diff 风格意图推断（L3） | 需先有基础联动数据才能做意图推断 |
| 4 | 不修改 Agent 测试自循环 PRD（另一个会话的产物） | AC14 建议已提出，由那个会话的 owner 决定是否纳入 |
| 5 | 不覆盖前端 E2E / 混沌实验 | 分别由 Phase 4+ 和人工触发覆盖 |

---

## 五、边缘情况

| # | 场景 | 预期行为 | Batch |
|---|------|---------|-------|
| E1 | 同一 task 已有活跃审查 | ReviewService 抛 ValueError → _code_review() 捕获，复用已有审查 | A |
| E2 | 审查引擎 DB 未初始化 | init_db() 已在 main.py 启动时调用——本改动不新增建表逻辑 | A |
| E3 | Ponytail 审查返回空（非 Python 文件） | 返回空 PonytailReport → CrossReport 标注 "ponytail: no applicable files" | A |
| E4 | review_service 和 ponytail 都不可用 | CrossReport 标注 "review: unavailable"，不阻塞测试流程 | A |
| E5 | Spec.tasks 为空 | _code_review() 不调用 ReviewService——无代码可审 | A |
| E6 | ReviewCheckpoint 预期为空（PRD 阶段未提取到验收标准） | 左列为空 → 标注 "no expectation extracted from PRD"，不阻塞代码阶段对比 | B |
| E7 | 生成的 regression 测试编译失败 | 重试 2 次 → 仍失败 → 标注 HUMAN_NEEDED，不阻塞审查流程 | B |
| E8 | TestGapDetector 所需的代码中心度数据不可用 | 降级——只用可用的排序因子，标注 "partial ranking" | B |
| E9 | severity 字段在旧 ReviewDecision 记录中不存在 | migration 给旧记录设默认值 "minor"——不阻塞查询 | B |
| E10 | 双向推送消息队列满 | asyncio.Queue(maxsize=100) → 满时丢弃最低优先级消息 → 日志警告 | B |

---

## 六、调度器/防幻觉/图谱影响分析

### 6.1 调度器
- ReviewCheckpoint 的展开在 spec 解析阶段执行——不进入调度器 DAG
- 回归测试生成后的执行通过现有 TestTask → 复用调度器现有路径
- 不新增调度器状态

### 6.2 防幻觉
- 生成的 regression 测试代码经过 L1-L9 验证——复用 testing/ 已有的测试代码验证规则
- ReviewCheckpoint 的预期提取不涉及 LLM——纯静态解析（正则 + AST + Task 字段读取）
- 无新增幻觉风险

### 6.3 图谱
- M4 的代码中心度计算需要 `code_graph.get_callers()` 和 `code_graph.get_callees()`——已有接口
- M2 的 ReviewCheckpoint 不读写 CodeGraph——独立 Pydantic 模型
- 不修改 CodeGraph 表结构

---

## 七、成功指标

| 指标 | 当前 | 目标 | Batch |
|------|------|------|-------|
| 审查链路完整性 | _code_review() 不调 ReviewService | 每次 spec 执行 → 1 条 Review 记录 | A |
| 审查清单领域覆盖率 | 0%（Orbit 维度全缺） | 4 个 Orbit 特化维度 | A |
| Ponytail 发现可见性 | 仅日志 | CrossReport 卡片直接展示 | A |
| 审查缺失兜底 | 无 review_service → 跳过 | Ponytail 自动兜底 | A |
| 审查→测试回灌 | 无 | severity ≥ major 100% 触发 | B |
| 渐进式审查覆盖率 | 0（无跨阶段对照） | 每个 Spec.task 展开 ≥1 条检查点 | B |
| 交叉验证推送覆盖率 | 0（无推送） | 覆盖率低分支 + 缺失测试点 100% 推送 | B |
| 缺口风险排序 | 无排序 | ≥3 个排序因子，高风险排前 20% | B |
| ReviewDecision.severity 填充率 | 字段不存在 | 新记录 100% 有 severity | B |

---

### Batch C — 长期种子（P3，架构落地）

| # | 用户故事 | 验收标准 |
|---|---------|---------|
| US-C1 | 作为 Orbit 用户，我希望 AB 对比的结果持续累积，让系统自动选择历史上得分最高的策略，不再每次都要跑 AB | knowledge/ 中 AB 结果按模块聚合 → 同类模块自动路由到历史胜率最高的策略；胜率差距 >20% 时直接跳过 AB |
| US-C2 | 作为 Orbit 用户，我希望人类在 CrossReport 中的决策反馈回门禁系统，自动调整 Ponytail 规则的严重度 | 人类连续 3 次覆盖某类 Ponytail 警告 → 自动将该类降级为 info；连续 3 次采纳 → 保持或升级 |
| US-C3 | 作为 Orbit 用户，我希望系统能推断代码改动的意图（重构 vs 新功能 vs bug 修复），自动调整测试策略和审查重点 | 根据 PRD/Spec/commit message 分类改动意图 → 重构场景跳过功能测试、bug 修复场景重点回归 |
| US-C4 | 作为 Orbit 用户，我希望测试→审查→进化形成完整三角闭环——发现的问题不仅被修复，还反馈到 Prompt 进化 | 测试发现+审查确认的失败模式 → evolution/ GEPA Prompt 进化 → 同类任务下次质量更高 → 测试更容易通过 → 审查发现更少 |

### 验收标准（Batch C）

| # | 验收标准 | 对应 US | 量化指标 |
|---|---------|--------|---------|
| AC11 | AB 历史胜率自动路由 | US-C1 | 同模块 ≥3 次 AB 记录后启动路由；胜率差 >20% 跳过 AB |
| AC12 | 人类决策反馈门禁参数 | US-C2 | 连续 3 次覆盖 → 降级；决策数据持久化到 knowledge/ |
| AC13 | 改动意图分类准确率 | US-C3 | 区分 3 类意图（重构/新功能/bug修复）≥80% 准确率 |
| AC14 | 三角闭环链路完整 | US-C4 | 失败模式 → evolution/ → Prompt 变更 → 下次同类任务质量提升 |

### Batch C 边缘情况

| # | 场景 | 预期行为 |
|---|------|---------|
| E11 | AB 历史不足 3 次 | 不启动路由——回退到每次都 AB 对比 |
| E12 | 人类决策与 Ponytail 规则冲突频繁 | 标记为 "contested rule" → 不自动调整 → 通知管理员 |
| E13 | 改动意图无法分类 | 默认按"新功能"处理——最保守的测试策略 |

---

## 八、待确认问题

| # | 问题 | 当前假设 |
|---|------|---------|
| Q1 | Batch B 是否应与 Agent 测试自循环 PRD 合并实施？ | 分开——Agent 测试自循环 PRD 是另一个会话的产物，本 PRD 是审查侧的独立增强。两者通过 CrossReport 接口集成，不互相阻塞 |
| Q2 | ReviewCheckpoint 的预期提取对 PRD 文本质量的最低要求？ | PRD 需含至少一条"- "或"* "开头的列表行（验收标准段）。无则标注 "no structured AC found" |
| Q3 | TestGapDetector 的排序权重是否需要人工调参？ | 初始用 TestGapRadar 论文的默认权重，积累 30+ 次审查后根据人类决策数据自动调 |

---

*— 阶段 1 PRD · 2026-07-07 · 等待用户确认 —*
