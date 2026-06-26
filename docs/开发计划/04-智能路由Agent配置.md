# V14.1 开发计划 · Step 2.3 智能路由Agent配置LLM

> **发布日期**: 2026-06-25 | **状态**: 新增Step（设计定稿，待实现）
> **核心目标**: 在 Step 2.1（LiteLLM 网关）和 Step 5.1（调度器）之间增加智能路由决策层，根据任务复杂度和 Agent 角色动态选择 LLM 模型。支持环境变量、CC_SWITCH 全局覆盖、运维手动切换，所有模型变更可追溯、可审计。

---

## 目录

1. [功能概述](#1-功能概述)
2. [模型分级体系](#2-模型分级体系)
3. [路由决策机制](#3-路由决策机制)
4. [Agent LLM 配置检测与强制切换](#4-agent-llm-配置检测与强制切换)
5. [技术实现](#5-技术实现)
6. [与现有 Step 的映射](#6-与现有-step-的映射)
7. [收益分析](#7-收益分析)
8. [实施路线图](#8-实施路线图)

---

## 1. 功能概述

**一句话说明**：系统根据"这个任务有多难"和"是哪个 Agent 在执行"，自动决定"用哪个模型来处理"——简单任务用轻量模型省钱，复杂任务用全量模型保质量。同时运维可通过环境变量、CC_SWITCH 或 API 随时查看和强制切换 Agent 的 LLM 配置。

### 1.1 当前问题

- 所有 Agent、所有任务都用 DeepSeek 全量模型（70B+ 参数）
- 简单任务（改配置、修拼写、查文档）不需要全量模型的推理能力
- 造成不必要的 Token 消耗和成本浪费
- 没有根据任务类型差异化分配 LLM 资源的机制
- 运维无法确认每个 Agent 当前实际在用哪个模型
- 无法通过环境变量或 CC_SWITCH 强制切换 Agent 的 LLM

### 1.2 解决方案

- 引入 **RouterAgent**，在 PLANNING 阶段评估任务复杂度
- 根据任务复杂度和 Agent 角色，动态推荐最优模型
- 简单任务 → 轻量模型（省钱），复杂任务 → 全量模型（保质量）
- 支持降级策略：轻量模型失败时自动升级到全量模型
- 新增 Agent LLM 配置检测功能，通过 API/驾驶舱查询每个 Agent 当前实际使用的模型
- 支持环境变量（`AGENT_${ROLE}_MODEL`）和 CC_SWITCH 强制覆盖配置

---

## 2. 模型分级体系

### 2.1 四层模型分级

| 级别 | 模型 | 参数量 | 成本/1K tokens | 适用场景 |
|------|------|--------|---------------|---------|
| Tier 0 | 本地规则引擎 | — | 零成本 | 极简任务（改配置、查变量） |
| Tier 1 | DeepSeek V4 Flash | — | 低 | 简单任务（单文件/单函数修改） |
| Tier 2 | DeepSeek V4 Pro | — | 中 | 中等任务（多文件修改、代码审查） |
| Tier 3 | DeepSeek V4 Pro | — | 标准 | 复杂任务（架构设计、安全、并发） |
| 降级 | GLM-4.7 Flash（免费） | — | 免费 | 所有模型不可用时的最终降级 |

### 2.2 模型说明

四层模型全部基于现有 LiteLLM 网关已配置的模型（`src/orbit/gateway/client.py`）：
- **GLM-5.2** → Tier 3 最强推理（architect），Coding Plan 订阅
- **DS V4 Pro** → Tier 2 中档推理（developer/reviewer/qa）
- **DS V4 Flash** → Tier 1 轻量任务（config_manager/clarifier）
- **GLM-4.7 Flash** → 统一降级兜底（免费），Coding Plan 订阅

> 失败升级链: Tier 1 失败 → Tier 2 → Tier 3。每个 Tier 独立执行，不看上一 Tier 的失败输出。Tier 3 完成后三方案对比合并。

---

## 3. 路由决策机制

### 3.1 任务复杂度评估维度

RouterAgent 在 PLANNING 阶段评估以下维度：

| 评估维度 | 判定规则 | 影响模型选择 |
|---------|---------|-------------|
| 涉及文件数 | 1个→简单；2-5个→中等；6+→复杂 | 文件越多→需要更强上下文理解 |
| 修改类型 | 配置/注释→极简；单函数→简单；多模块→复杂 | 抽象程度越高→需要更强推理 |
| 是否涉及核心逻辑 | 支付、安全、并发→高风险 | 高风险→必须用全量模型 |
| Agent 角色 | ParserAgent→轻量；DeveloperAgent→中等；ArchitectAgent→全量 | 角色决定推理深度 |
| 历史相似任务 | 存在相似成功案例→可复用推理链 | 有先例→可降级 |
| 是否需要 Z3 验证 | @formal 标记→需要强推理 | 需要 Z3→必须全量模型 |

### 3.2 路由决策矩阵

| 任务复杂度 | Agent 角色 | 推荐模型 | 理由 |
|-----------|-----------|---------|------|
| 极简（配置/注释/格式化） | ConfigAgent | Tier 0 本地规则引擎 | 不需要 LLM 调用 |
| 简单（单函数/单文件） | DeveloperAgent | Tier 1 DS Flash | 轻量推理足够 |
| 中等（多文件/中等修改） | DeveloperAgent | Tier 2 GLM-5.2 | 性价比最优 |
| 复杂（跨模块/架构变更） | ArchitectAgent | Tier 3 DeepSeek-V4 | 需要深度推理 |
| 高风险（支付/安全/并发） | DeveloperAgent | Tier 3 DeepSeek-V4 | 安全优先，不用省钱 |

### 3.3 降级与升级策略

- **升级策略（自动）**：轻量模型验证失败 3 次 → 自动升级到下一级模型重试
- **降级策略（用户可控）**：用户可通过 API 参数强制指定模型级别（如"用轻量模式"）
- **熔断保护**：轻量模型连续失败 5 次 → 全局熔断，强制使用全量模型

---

## 4. Agent LLM 配置检测与强制切换

### 4.1 配置优先级（从高到低）

| 优先级 | 配置来源 | 说明 | 示例 |
|--------|---------|------|------|
| 1（最高） | 运维手动切换（API） | 通过管理 API 强制指定 | `POST /api/v1/agents/DeveloperAgent/llm/switch` |
| 2 | CC_SWITCH 全局开关 | 环境变量强制覆盖 | `CC_SWITCH="DeveloperAgent:glm-5.2,force"` |
| 3 | 环境变量 | 为特定 Agent 指定模型 | `AGENT_DEVELOPERAGENT_MODEL=glm-5.2` |
| 4 | RouterAgent 推荐 | 基于任务复杂度的智能推荐 | Tier 2 → GLM-5.2 |
| 5（最低） | 系统默认 | 全局默认模型 | `DEFAULT_LLM_MODEL=deepseek/deepseek-chat` |

### 4.2 CC_SWITCH 配置格式

```bash
# 所有 Agent 使用指定模型
CC_SWITCH="all:deepseek-v3"

# 为特定 Agent 指定不同模型
CC_SWITCH="DeveloperAgent:glm-5.2,ArchitectAgent:deepseek-v3"

# 强制覆盖（即使 Agent 有环境变量配置也覆盖）
CC_SWITCH="DeveloperAgent:glm-5.2,force"

# 非强制模式（仅当 Agent 没有更高优先级配置时生效）
CC_SWITCH="DeveloperAgent:glm-5.2,no-force"
```

### 4.3 配置状态查询 API

```
GET /api/v1/agents/DeveloperAgent/llm

Response:
{
  "agent": "DeveloperAgent",
  "current": {
    "model": "glm-5.2",
    "source": "cc_switch",
    "reason": "CC_SWITCH: DeveloperAgent:glm-5.2,force",
    "effective_since": "2026-06-25T10:00:00Z",
    "is_forced": true
  },
  "available_sources": ["cc_switch", "environment", "router", "default"],
  "history": [
    {"model": "deepseek-v3", "source": "router", "time": "..."},
    {"model": "glm-5.2", "source": "cc_switch", "time": "..."}
  ],
  "cc_switch_active": true,
  "cc_switch_config": "DeveloperAgent:glm-5.2,force"
}
```

### 4.4 强制切换 API

```
POST /api/v1/agents/DeveloperAgent/llm/switch
{
  "model": "deepseek-v3",
  "reason": "glm-5.2 输出质量下降，临时切换",
  "expires_at": "2026-06-27T10:00:00Z"  // 可选，到期后自动恢复
}
```

### 4.5 驾驶舱面板

| Agent | 当前模型 | 来源 | 操作 |
|-------|---------|------|------|
| DeveloperAgent | glm-5.2 | CC_SWITCH 🔒 | [查看历史] [切换] |
| ArchitectAgent | deepseek-v3 | Router | [查看历史] [切换] |
| ReviewerAgent | deepseek-v3 | 默认 | [查看历史] [切换] |
| QAAgent | ds-flash | 环境变量 | [查看历史] [切换] |

---

## 5. 技术实现

### 5.1 架构位置

```
调度器（Step 5.1）PLANNING 阶段 → RouterAgent（新增）
  → AgentModelResolver（新增）→ LiteLLM 网关（Step 2.1）
```

### 5.2 核心类

```python
# /src/router/agent.py
class ModelTier(str, Enum):
    TIER_0 = "tier_0"  # 本地规则引擎
    TIER_1 = "tier_1"  # DS Flash
    TIER_2 = "tier_2"  # GLM-5.2
    TIER_3 = "tier_3"  # DeepSeek-V4

class AgentModelResolver:
    """按优先级解析 Agent 实际使用的模型
    1. CC_SWITCH 强制覆盖（最高）
    2. 环境变量 AGENT_{ROLE}_MODEL
    3. RouterAgent 推荐
    4. 系统默认模型
    """
```

### 5.3 LiteLLM 网关增强

```python
class LLMClient:
    MODEL_MAP = {
        ModelTier.TIER_0: None,
        ModelTier.TIER_1: "deepseek/deepseek-flash",
        ModelTier.TIER_2: "glm/glm-5.2",
        ModelTier.TIER_3: "deepseek/deepseek-chat",
    }
```

---

## 6. 与现有 Step 的映射

| Step | 原有内容 | 新增集成 |
|------|---------|---------|
| Step 2.1 LiteLLM 网关 | 统一 LLM 调用、成本追踪、熔断器 | 调用前通过 AgentModelResolver 获取实际模型；审计表增加 actual_model 和 model_source 字段 |
| Step 5.1 调度器 | 状态流转：PARSING→PLANNING→CODING→VALIDATING→DONE | PLANNING 阶段调用 RouterAgent；Agent 拉起时注入模型配置到 TaskContext |
| Step 5.2 Agent 角色 | 5 个 Agent 的 System Prompt 和职责 | Prompt 中增加模型级别提示；支持 AgentModelResolver 注入 |
| Step 6.1 驾驶舱 | 实时任务监控 | 新增"Agent-LLM 配置状态"面板 |
| 审计表 | 记录执行轨迹 | 每次 LLM 调用记录 actual_model 和 model_source |

---

## 7. 收益分析

### 7.1 任务分布假设

| 任务类型 | 占比 | 复杂度评分 | 推荐模型 |
|---------|------|-----------|---------|
| 配置/注释修改 | 15% | 0-20 | Tier 0（本地规则） |
| 简单单文件修改 | 25% | 20-40 | Tier 1（DS Flash） |
| 中等多文件修改 | 35% | 40-70 | Tier 2（GLM-5.2） |
| 复杂架构级任务 | 25% | 70-100 | Tier 3（DeepSeek-V4） |

### 7.2 Token 消耗对比

| 场景 | 当前（全用 DeepSeek） | 优化后（智能路由） | 节省 |
|------|---------------------|-------------------|------|
| 简单任务（单次） | ~500 tokens | ~50 tokens（Tier 1） | 90% |
| 中等任务（单次） | ~2000 tokens | ~400 tokens（Tier 2） | 80% |
| 复杂任务（单次） | ~5000 tokens | ~5000 tokens（Tier 3） | 0% |
| **加权平均** | **~2475 tokens/任务** | **~1165 tokens/任务** | **~53%** |

> 智能路由 Agent 预计可节省 ~50% 的 Token 消耗。

---

## 8. 实施路线图

| 阶段 | 任务 | 周期 | 优先级 |
|------|------|------|--------|
| 阶段一：基础路由 | ComplexityScore 计算 + RouterAgent 核心 + 模型映射 | 2-3 天 | P0 |
| 阶段二：配置检测 | AgentModelResolver + CC_SWITCH 解析 + 环境变量检测 | 1-2 天 | P0 |
| 阶段三：LiteLLM 集成 | 多模型配置 + 升级/降级策略 + 审计表增强 | 1-2 天 | P0 |
| 阶段四：API 与驾驶舱 | 配置查询 API + 强制切换 API + 驾驶舱面板 | 1-2 天 | P1 |
| 阶段五：测试 | 路由决策准确率 + 配置优先级验证 + 成本节省验证 | 1-2 天 | P0 |

> 总工作量：6-11 天（约 1.5-2 周），建议与 LiteLLM 网关（Step 2.1）同步推进。

---

*— V14.1 开发计划 · Step 2.3 智能路由Agent配置LLM · 2026年6月25日 —*
