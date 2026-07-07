# 11-Agent 测试自循环模块

> **版本**: V14.1+TestCycle | **日期**: 2026-07-07 | **状态**: 设计定稿，待实施
> **详细设计**: [`docs/research/Orbit测试环节设计——Agent自循环测试体系.md`](../research/Orbit测试环节设计——Agent自循环测试体系.md)
> **父文档**: [`05-测试体系.md`](05-测试体系.md) — 10 维度 × 200+ 场景测试体系（本模块为 05 的 Agent 自循环实现层）

---

## 一、目标

将测试从"人类驱动的阶段 4 外部门禁"升级为"Agent 内建质量闭环"。

新增 `src/orbit/testing/` 模块（~10 文件），复用 Orbit 已有 45 个模块的能力，实现：

```
意图理解 → 测试生成 → 代码生成(TDD) → 沙箱执行 → 多验证器验证 → 反馈闭环
```

---

## 二、新增模块结构

```
src/orbit/testing/
├── __init__.py
├── orchestrator.py          # 核心编排器——L4 中枢
├── intention.py             # PRD/Goal → Test Intention 提取
├── gate.py                  # 质量门禁判定
├── rts.py                   # 智能测试选择（依赖变更 → 只跑受影响模块）
├── agent_behavior.py        # Agent 行为测试（测试 Orbit 的 Agent 自身）
├── feedback.py              # 失败模式 → knowledge/ 回灌
├── reporter.py              # 测试报告生成（人类可读 + Agent 可消费 JSON）
├── strategies/
│   ├── __init__.py
│   ├── path_sensitive.py    # 路径敏感生成（依赖 code_graph CFG）
│   ├── mutation_guided.py   # 变异引导生成（调用 mutmut）
│   ├── intention_driven.py  # 意图驱动生成
│   ├── property_based.py    # 属性测试生成（Hypothesis）
│   └── ab_runner.py         # AB 四层对比——策略/模型/Prompt/分支
└── api/
    ├── __init__.py
    └── test_routes.py       # 测试相关 REST API（/api/v1/tests/*）
```

---

## 三、测试类型矩阵

| 类型 | 何时生成 | 何时运行 | 成本 | 触发方式 |
|------|---------|---------|------|---------|
| **单元测试** | 阶段 3 代码生成前（TDD） | 秒级：生成完立即跑 | 5-30s | orchestrator 自动 |
| **属性测试(PBT)** | 阶段 3 检测到纯函数时 | 秒级：同上 | +5-15s | orchestrator 自动（条件） |
| **契约测试骨架** | 阶段 2 技术方案后 | 骨架空跑（验证结构），阶段 3 填充后正式跑 | 10-30s | 阶段 2 Agent 自动生成，阶段 3 填充 |
| **Gherkin 场景骨架** | 阶段 1 PRD 后 | 骨架空跑，阶段 3 填充后正式跑 | 秒级 | 阶段 1 Agent 自动生成 |
| **集成测试** | 阶段 3 新 API/模块边界时 | 分钟级：展示 diff 前 | +20-40s | rts.py 检测变更触发 |
| **回归测试** | Bug 修复时 | 分钟级：修 bug 前先确认复现 | 10-30s | 阶段 3 Agent 强制 |
| **变异测试** | 不生成（执行型） | 分钟级：核心模块秒级通过后 | 1-2min | orchestrator 自动（核心模块） |
| **AB 测试 L1** | 两种策略都适用时 | 秒级：与单元测试并行 | +10-20s | ab_runner 自动（~30% 场景） |
| **AB 测试 L2-L4** | 按需 | 分钟-小时级 | 不定 | 人工/定时触发 |
| **Agent 行为测试** | 调度器/Agent 角色变更时 | 每日定时 | 分钟级 | 定时任务触发 |
| **E2E 测试** | 核心 workflow 变更时 | PR 门禁层 / 每日 | 2-10min | CI / 定时触发 |

---

## 四、与 WORKFLOW.md 的流程集成

```
阶段 1 → 生成 Gherkin 场景骨架（从 PRD 验收标准提取）
阶段 2 → 生成契约测试骨架 + Test Plan
阶段 3 → 填充骨架 + TDD 内循环（单元+PBT+集成+AB）
阶段 3b → 人类审查（附测试结果摘要）
阶段 4 → Agent 跑全部门禁 → 人类验收
```

---

## 五、四 Phase 实施路线

### Phase 1：基础内循环（1-2 周）——MVP

| 文件 | 内容 | 优先级 |
|------|------|--------|
| `testing/orchestrator.py` | 核心编排流程 | P0 |
| `testing/intention.py` | Test Intention 提取 | P0 |
| `testing/gate.py` | 编译 + 覆盖率门禁 | P0 |
| `testing/strategies/intention_driven.py` | 意图驱动生成 | P0 |
| `testing/api/test_routes.py` | API 端点 | P0 |
| `tests/unit/test_testing_*.py` | 自身单元测试 | P0 |

**验收标准**：Agent 生成代码后自动跑单元测试 + 覆盖率判定 + 失败自修复 ≤3 轮

### Phase 2：策略增强（2-3 周）

| 文件 | 内容 | 优先级 |
|------|------|--------|
| `testing/rts.py` | 智能测试选择 | P1 |
| `testing/strategies/path_sensitive.py` | 路径敏感生成 | P1 |
| `testing/strategies/property_based.py` | Hypothesis PBT | P1 |

**验收标准**：代码图谱依赖分析 → 只跑受影响模块，全量回归 ≤5 分钟

### Phase 3：闭环反馈（3-4 周）

| 文件 | 内容 | 优先级 |
|------|------|--------|
| `testing/feedback.py` | 失败模式 → knowledge/ 回灌 | P1 |
| `testing/strategies/ab_runner.py` | AB 四层对比 | P2 |
| `testing/strategies/mutation_guided.py` | 变异引导生成 | P2 |
| `testing/agent_behavior.py` | Agent 行为测试 | P2 |

**验收标准**：失败模式入库 → 下次同类任务预判；AB 结果沉淀到 knowledge/

### Phase 4：人类报告 + 生产化（4-6 周）

| 文件 | 内容 | 优先级 |
|------|------|--------|
| `testing/reporter.py` | 测试报告生成 | P1 |
| `frontend/` `TestResultCard.vue` | 聊天流内嵌测试摘要卡片（~60 行新组件） | P1 |
| `frontend/` `MessageItem.vue` | 新增 `test_result` 段类型（~20 行改动） | P1 |
| `frontend/` `TestPanel.vue` | 加 compact 模式 + 回调 props（~30 行改动） | P1 |

**验收标准**：测试结果以摘要卡片形式内嵌在聊天流中，跟代码块同级；展开后可查看详情、覆盖率缺口、AB 对比

---

## 六、API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/tests/run` | 触发测试执行（传入代码/模块） |
| GET | `/api/v1/tests/results/:task_id` | 获取测试结果 |
| GET | `/api/v1/tests/coverage?module=` | 获取覆盖率报告 |
| POST | `/api/v1/tests/ab-compare` | 触发 AB 策略对比 |
| GET | `/api/v1/tests/history?module=` | 获取模块历史测试趋势 |
| WS | `/ws/tests/:task_id` | 实时测试进度推送 |

---

## 七、依赖关系

```
testing/ 依赖（全部已有，无需新建）:
├── goal/           — 解析任务目标
├── knowledge/      — 检索历史用例 + 缺陷模式
├── graph/          — CFG 提取 + 依赖分析（RTS）
├── sandbox/        — Docker 隔离执行
├── hallucination/  — L1-L9 验证
├── compliance/     — L9 合规验证
├── review/         — 代码审查
├── observability/  — 轨迹收集 + 反馈
├── checkpoint/     — 测试前保存检查点
├── evolution/      — 失败模式 → Prompt 进化
└── gateway/        — LLM 调用

外部依赖（无需新增）:
├── pytest / pytest-xdist / pytest-cov
├── mutmut（变异测试）
├── Hypothesis（属性测试）
└── Playwright（E2E）
```

---

## 八、成功指标

| 指标 | 当前 | 目标 |
|------|------|------|
| Agent 代码生成后自动测试执行率 | 0%（人工触发） | 100% |
| 测试失败自修复成功率 | 无此能力 | ≥70%（3 轮内） |
| 新代码测试生成覆盖率 | 0%（依赖人类手写） | 100%（必有对应测试） |
| RTS 节省测试时间 | 无（全量跑） | -60% |
| 人类测试介入时间 | 阶段 4 全部手动 | 仅审核结果 + 处理阻塞 |

---

*— V14.1+TestCycle · 2026-07-07 —*
