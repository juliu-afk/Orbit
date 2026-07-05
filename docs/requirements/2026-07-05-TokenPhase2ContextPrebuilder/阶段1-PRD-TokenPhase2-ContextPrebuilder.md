# 阶段1-PRD-TokenPhase2-ContextPrebuilder

> 日期: 2026-07-05 | 版本: v1.0 | 状态: 待用户确认
> 来源: [Token节省落地执行报告 §11 Phase 2](file:///C:/Users/Administrator/OneDrive/Desktop/Token节省落地执行报告_2026-06-26.md)
> 详细设计: [Token节省Phase2——Orbit Agent层上下文预构建方案.html](file:///D:/Orbit docs/Token节省Phase2——Orbit Agent层上下文预构建方案.html)

---

## 1. 问题与背景 (Problem Statement)

### 当前状态
Orbit 已实现 Phase 0+1 Token 节省（CLAUDE.md 拆分、PR 审核预处理、AGENTS.md 同步）。Agent 层有 5 层反应式压缩管线（L1-L5），在 ReAct 循环中检测阈值后触发压缩。

### 核心问题
**压缩是反应式的，不是前置式的。** Agent 首次 LLM 调用时 context 仍是全量原始数据——首轮 token 已浪费。压缩在循环中兜底，但触发频率高、效果打折。

### 根因
- 没有 dispatch 前的 context 裁剪步骤
- TaskContext 是通用篮子——填充内容不按角色适配
- 没有"不含完整 diff"的硬约束
- 所有扫描（影响面、权限、测试缺口）由 Agent 在循环中用 LLM 判断——贵且不稳定

---

## 2. 目标用户与角色 (Target Users)

| 角色 | 痛点 | 受益 |
|------|------|------|
| **Orbit 最终用户** | Agent 执行慢、Token 消耗高、出结果慢 | -44% token/任务，响应更快 |
| **Orbit 开发者** | 压缩逻辑散落各处，难维护 | 统一 ContextPrebuilder 体系，可测可换 |
| **Orbit 调度器** | 不知道给每个 Agent 塞多少 context | 角色特定裁剪规则，结构化管理 |

---

## 3. 用户故事 (User Stories)

### P0（必须做）

**US1: Developer Agent 只收到相关代码**
> 作为 Developer Agent，当我收到编码任务时，我只看到变更范围内的代码片段（≤5 个文件）和现有测试，不看到全量代码库。以便我聚焦任务而非被无关代码分散注意力。

**US2: Reviewer Agent 不收到完整 diff**
> 作为 Reviewer Agent，当我审查 PR 时，我收到 diff 摘要 + 权限变更 + schema 变更的结构化报告，而非完整 diff。以便我快速定位高风险点而非逐行阅读。

**US3: Context 字段有硬上限**
> 作为调度器，TaskContext 的每个字段有 max_chars 约束（默认 5000），超过自动截断+摘要替代。以便防止单字段塞入大段原始数据撑爆 context window。

### P1（应该做）

**US4: QA Agent 只跑增量测试**
> 作为 QA Agent，当我收到验证任务时，我根据变更范围（git diff 分析）自动决定测试粒度——冒烟/单元+集成/回归。以便不浪费 token 跑无关测试。

**US5: Clarifier Agent 不看到代码细节**
> 作为 Clarifier Agent，当我收到需求澄清任务时，我只看到用户原始输入 + 项目说明书 + 关键词，不看到代码实现细节。以便聚焦需求理解而非被实现细节干扰。

### P2（可延后）

**US6: 所有 Agent 间消息有大小约束**
> 作为 MessageBus，Agent 间转发的消息体超过阈值自动截断。以便防止大消息撑爆下游 Agent 的 context。

---

## 4. 验收标准 (Acceptance Criteria)

| # | AC | 关联 US | 验证方式 |
|---|-----|---------|---------|
| AC1 | 5 个 ContextPrebuilder 子类全部实现，`build(role, task_type, raw_context) → pruned_context` 返回裁剪后 dict | US1, US2, US5 | 单元测试——给定 raw_context，验证输出字段数 ≤ 输入，无关字段已删除 |
| AC2 | TaskContext 所有字段 `.to_dict()` 后每个字符串值 ≤ 5000 chars | US3 | 单元测试——构造超长字段，验证截断 |
| AC3 | 7 个 Context Builder 全部实现，输入文件列表/git diff/PRD，输出结构化 dict | US1-US5 | 集成测试——用真实 Orbit PR 跑 |
| AC4 | 5 个预扫描器全部实现，输出结构化 dict（文件列表/依赖图/覆盖率缺口等） | US1, US2, US4 | 单元测试——验证输出 schema |
| AC5 | ReviewerAgent 收到的 context 不含完整 diff——只有 diff 摘要（≤ 3000 chars） | US2 | 集成测试——对比原始 diff 大小和 Reviewer context 大小 |
| AC6 | SCOPING 状态正确识别变更范围 → 测试粒度决策正确（前端only→冒烟, 核心模块→回归） | US4 | 单元测试——3 种变更范围 × 3 种预期决策 |
| AC7 | Token 基准测试——同任务改造后 token 消耗 ≤ 改造前 70% | AC7 | 回归测试——记录改造前后同任务 token 数 |
| AC8 | 已有压缩管线（L1-L5）不受影响——当 ContextPrebuilder 裁剪后仍超阈值时，反应式压缩仍触发 | — | 集成测试——构造极端大 context，验证压缩兜底 |
| AC9 | 所有新增文件 py_compile 通过 | — | CI 门禁 |

---

## 5. 成功指标 (Success Metrics)

| 指标 | 当前基线 | 目标 | 测量方法 |
|------|---------|------|---------|
| 单任务链 Token 消耗 | ~40,000（5 Agent 调用） | ≤28,000（-30%） | `budget_tracker.record_usage()` 日志比对 |
| 压缩管线触发频率 | 80%+ 的 Agent 调用触发 WARN/FORCE | ≤40% | `compressor.compress()` 日志 `action != SKIP` 占比 |
| Reviewer Agent context 体积 | 等同于完整 diff + 全量文件 | ≤ 完整 diff 的 30% | `reviewer-input.md` 大小对比 |
| QA Agent 测试执行数 | 全量跑 | 增量——仅变更相关测试 | 测试执行清单对比 |

---

## 6. 非目标 (Non-Goals)

- ❌ 不改变现有 5 层压缩管线（L1-L5）——本次是补充前置步骤，不是替代
- ❌ 不改变 PromptBuilder 三层缓存策略
- ❌ 不修改 Agent 基类的 execute() 接口
- ❌ 不做 LLM 驱动的上下文分析——本次全部确定性规则/正则/AST
- ❌ 不引入新的 LLM 调用——ContextPrebuilder 和 Scanner 都是纯 Python，0 LLM 调用

---

## 7. 边缘情况与风险

| 场景 | 预期行为 |
|------|---------|
| 空 context（新项目，无 git diff） | ContextPrebuilder 返回最小 context（仅项目说明书 + 用户输入），不崩溃 |
| 超大 diff（100+ 文件变更） | 分类摘要——按模块分组列出文件名，不列举每行变更 |
| 非 git 项目 | Scanner 返回空 dict——降级为仅 ContextPrebuilder 裁剪，不报错 |
| 不支持的编程语言 | ImportDependencyScanner 跳过——标注 `language_unsupported=True`，不影响其他扫描器 |
| ContextPrebuilder 异常 | fail-open——返回原始 context + warning 日志，不阻塞 Agent 执行 |
| 压缩管线与预构建冲突 | 预构建先执行，压缩后兜底——L1-L5 阈值检查仍然生效 |

---

## 8. 待确认问题

1. **SCOPING 状态插入位置**：在 PARSING 之后、PLANNING 之前？还是 PARSING 之后、CODING 之前？→ 建议 PARSING→SCOPING→PLANNING，SCOPING 输出变更范围供 Architect 和 Developer 共享。

2. **max_chars 默认值**：5000 chars 是否合适？→ 当前 PromptBuilder context 层截断也是 5000，保持一致。

3. **Token 基准测试**：用哪个任务做 benchmark？→ 建议用 Orbit 近 3 个 PR 的平均——PR#171, #172, #173（项目说明书系列）。

---

> 阶段门禁：请用户确认以上 8 章内容（特别是待确认问题 #1 SCOPING 插入位置），确认后进入阶段 2 技术方案。
