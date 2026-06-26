# PRD：Step 2.3 智能路由Agent + 测试体系补全

> 版本: v1.0 | 日期: 2026-06-26 | 状态: 待确认

---

## 1. 背景

### 1.1 智能路由（Step 2.3）

当前 Orbit 所有 Agent、所有任务统一使用 DeepSeek-V4-Pro（70B+），简单任务（改配置、修拼写、查文档）不需要全量模型的推理能力，造成 Token 浪费。运维无法确认每个 Agent 实际在用哪个模型，无法强制切换。

设计文档 `docs/开发计划/04-智能路由Agent配置.md`（2026-06-25）已定稿，代码层零实现。

### 1.2 测试缺口

设计文档 `docs/开发计划/05-测试体系.md`（2026-06-25）定义了 10 维度测试体系。现有 65 个测试文件覆盖了大部分单元/集成/E2E，但有 4 个缺口：

| 缺口 | 现状 |
|------|------|
| L9 合规验证层测试 | `src/orbit/compliance/` 已实现，但无测试文件 |
| RouterAgent 测试 | 模块未实现 |
| 混沌测试 | `tox -e chaos` 未建立 |
| 安全扫描 | semgrep/bandit 未集成到 CI |

---

## 2. 用户故事

### P0

- **作为运维人员**，我希望通过 CC_SWITCH 环境变量强制切换 Agent 的 LLM 模型，以便在模型质量波动时快速止损。
- **作为系统**，我希望 RouterAgent 在 PLANNING 阶段根据任务复杂度自动选择模型，简单任务用轻量模型省钱，复杂任务用全量模型保质量。
- **作为开发者**，我希望 L9 合规验证层有单元测试覆盖，避免回归。

### P1

- **作为运维人员**，我希望通过 API 查询每个 Agent 当前实际使用的模型和来源。
- **作为 QA**，我希望 CI 中集成安全扫描（semgrep + bandit），每次 PR 自动检查。

### P2

- 混沌工程测试框架搭建
- 驾驶舱"Agent-LLM 配置状态"面板

---

## 3. 验收标准

### AC1-6：智能路由（Step 2.3 阶段一~三）

| # | 标准 | 验证方式 |
|---|------|---------|
| AC1 | RouterAgent 能根据任务复杂度输出 ModelTier（Tier 0-3） | 单元测试：给定不同复杂度输入，断言输出 Tier |
| AC2 | AgentModelResolver 按优先级正确解析模型（CC_SWITCH > 环境变量 > Router > 默认） | 单元测试：5 种优先级组合 |
| AC3 | CC_SWITCH 支持 `all:`、`AgentName:`、`force`/`no-force` 格式 | 单元测试：解析器 |
| AC4 | LiteLLM 客户端调用前通过 Resolver 获取实际模型 | 集成测试：mock LiteLLM，断言传入了正确模型 |
| AC5 | 降级策略：轻量模型失败 3 次 → 自动升级 | 集成测试 |
| AC6 | 审计表记录 actual_model 和 model_source | 集成测试 |

### AC7-9：测试补全

| # | 标准 | 验证方式 |
|---|------|---------|
| AC7 | L9 合规验证层有单元测试（正向+异常） | `pytest tests/unit/test_compliance.py` |
| AC8 | RouterAgent + AgentModelResolver 单元测试通过 | `pytest tests/unit/test_router.py` |
| AC9 | CI 集成 semgrep 安全扫描 | `.github/workflows/` 配置 |

---

## 4. 模型体系（基于现有 LiteLLM 网关配置）

| Tier | 模型 | 适用场景 | 来源 |
|------|------|---------|------|
| Tier 0 | 本地规则引擎 | 极简任务（改配置、查变量） | 无 LLM 调用 |
| Tier 1 | DeepSeek V4 Flash | 简单任务（单文件/单函数修改） | `gateway/client.py` 已有 |
| Tier 2 | GLM-5.2 | 中等任务（多文件修改、代码审查） | `gateway/client.py` 已有 |
| Tier 3 | DeepSeek V4 Pro | 复杂任务（架构设计、安全、并发） | `gateway/client.py` 已有 |
| 降级兜底 | GLM-4.7 Flash（免费） | 所有模型不可用时的最终降级 | `gateway/client.py` 已有 |

## 5. 交付计划——拆 4 个 PR

| PR | 内容 | 文件 | AC | 工作量 |
|----|------|------|----|--------|
| #1 | **RouterAgent 核心**——RouterAgent + Resolver + CC_SWITCH 解析器 | `src/orbit/router/` 新模块 + 单元测试 | AC1-AC3, AC8 | 2-3天 |
| #2 | **LiteLLM 集成**——网关接入 Resolver + 调度器调用 + 审计表增强 | gateway/client.py, scheduler/orchestrator.py, audit | AC4-AC6 | 1-2天 |
| #3 | **API + 驾驶舱**——查询/强制切换端点 + 驾驶舱面板 | api 新端点, frontend 面板 | — | 1-2天 |
| #4 | **测试补全**——L9 单元测试 + semgrep CI + 混沌框架 | tests/unit/test_compliance.py, .github/workflows/, tests/chaos/ | AC7, AC9 | 1-2天 |

## 6. Non-Goals（本次不做）

- 无。全部纳入上述 4 个 PR。

---

## 5. 影响范围

| 模块 | 改动 | 类型 |
|------|------|------|
| `src/orbit/router/` | **新增**——RouterAgent + AgentModelResolver + CC_SWITCH 解析器 | 新模块 |
| `src/orbit/gateway/` | **修改**——LLM 客户端调用前接入 Resolver | 修改 |
| `src/orbit/scheduler/orchestrator.py` | **修改**——PLANNING 阶段调用 RouterAgent | 修改 |
| `src/orbit/audit/` | **修改**——审计表增加 actual_model / model_source 字段 | 修改 |
| `tests/unit/test_compliance.py` | **新增**——L9 合规验证层测试 | 新文件 |
| `tests/unit/test_router.py` | **新增**——RouterAgent + Resolver 单元测试 | 新文件 |
| `.github/workflows/` | **修改**——CI 增加 semgrep 安全扫描 | 修改 |

---

## 6. 边缘情况

| 场景 | 处理 |
|------|------|
| CC_SWITCH 格式错误（非法 Agent 名） | 解析失败→打印 WARN→降级到下一个优先级 |
| 所有模型源都不可用 | 降级到 DEFAULT_LLM_MODEL，如未设→抛 ConfigurationError |
| 轻量模型连续失败达熔断阈值 | 全局熔断，强制使用全量模型 |
| RouterAgent 复杂度评分异常（负值/超范围） | clamp 到 [0, 100] |
| CC_SWITCH 和环境变量同时配置同一 Agent | CC_SWITCH 优先（force 模式），环境变量优先（no-force 模式） |
| 审计表写入失败 | 不阻塞主流程，WARN 日志 + 降级 |

---

## 8. 待确认问题（已确认）

1. RouterAgent 的复杂度评分权重是否需要调优？→ ✅ 支持动态调整，权重可配置（环境变量/配置文件），根据实际数据持续优化
2. CC_SWITCH 的变更是否需要审计？→ ✅ 是，任何模型变更都写入 task_audit_trail
3. 本次是否包含 API 端点？→ ✅ 包含，纳入 PR #3

---

> **阶段 1 已确认。进入阶段 2 技术方案。**
