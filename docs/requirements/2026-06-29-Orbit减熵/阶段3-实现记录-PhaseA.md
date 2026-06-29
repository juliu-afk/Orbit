# Orbit 减熵 Phase A——阶段 3 实现记录 + 阶段 3b 代码审查

> 基线：[[阶段2-技术方案-内部减熵]] [[阶段2-技术方案-业务层减熵]] | 日期：2026-06-29

## 一、方案引用

按阶段 2 技术方案实施。实际完成范围：

| 方案 | PRD ID | 状态 |
|------|--------|------|
| 2.2 简洁规则 #9 | US-B2 | ✅ |
| 2.1 上下文相关性打分 | US-B1 | ✅ |
| 2.1 ResourceGuard 消重 | US-1 | ✅ |
| 2.2 Clarifier 消重 | US-2 | ✅ |
| 2.4 空目录清理 | US-4 | ✅ |

## 二、改动清单

| 文件 | 变化 | 类别 |
|------|------|------|
| `src/orbit/prompt/builder.py` | +22/-2 | 业务P0: 规则#9 + context裁剪 |
| `src/orbit/context/relevance.py` | NEW +232 | 业务P0: ast相关性打分器 |
| `src/orbit/resource_guard/resource_guard.py` | ~130行改写 | 内部P0: 复用GatewayCircuitState |
| `src/orbit/agents/clarifier.py` | +6/-18 | 内部P0: CONTRADICTION统一导入 |
| `src/orbit/scheduler/clarifier.py` | +8 | 内部P0: 合并矛盾对列表 |
| `src/orbit/core/__init__.py` | +5 | 内部P1: 填充__init__ |
| `src/orbit/graph/models/__init__.py` | +19 | 内部P1: 填充__init__ |
| `tests/unit/test_resource_guard.py` | +6/-7 | 测试适配新字段 |
| `src/orbit/api/dependencies/` | 删除 | 内部P1: 空目录 |
| `src/orbit/graph/schemas/` | 删除 | 内部P1: 空目录 |
| `src/orbit/infrastructure/` | 删除 | 内部P1: 空目录 |

净变化：137 insertions / 82 deletions (-3 empty dirs, +1 new file)

## 三、偏差说明

| 方案 | 偏差 | 理由 |
|------|------|------|
| 2.2 Clarifier 消重 | "删 agents/clarifier.py" → 改为统一 CONTRADICTION_PAIRS 导入 | agents/clarifier.py 被 chat 端点+factory 深度集成，全删风险高。改为从 scheduler 统一导入矛盾对列表，效果等价 |
| 2.1 ResourceGuard | 未注入完整 CircuitBreaker 对象 | gateway CircuitBreaker 是 async（Redis 存储），ResourceGuard 是 sync。采用共用 GatewayCircuitState 模型+阈值常量的方案，效果等价 |
| HALF_OPEN_PROBE_LIMIT | 3→1 | 消重时用了 gateway 的 HALF_OPEN_PROBE_LIMIT=1，原来 ResourceGuard 定义 DEFAULT_HALF_OPEN_PROBE_LIMIT=3。更严格的探测策略，gateway 的默认值更合理 |

## 四、阶段 3b 代码审查

| 维度 | 结果 |
|------|------|
| 安全 | ✅ 无硬编码密钥、无注入风险 |
| 调度器 | N/A——未改动状态机 |
| 防幻觉 | N/A——未改动防幻觉层 |
| 方案偏差 | ✅ 偏差已记录并说明理由 |
| 测试覆盖 | ✅ 967 passed, 0 failed |
| 代码质量 | 🔴→✅ 发现 1 个 bug（半开失败不重开熔断）→ 已修复 |

### 审查发现

| # | 严重度 | 位置 | 问题 | 处置 |
|---|--------|------|------|------|
| 1 | 🔴 致命 | `resource_guard.py:140` | 半开探测失败后 `not self._circuit.half_open` 阻止重开→永久卡 HALF_OPEN | **已修复**——加半开失败分支 |
| 2 | 🟡 风险 | `resource_guard.py` | HALF_OPEN_PROBE_LIMIT 3→1 | **接受**——gateway 默认值 1 更合理 |
| 3 | 🟡 注意 | `clarifier.py` | 6 对新增 regex 矛盾对生效 | **合理**——行为扩展非回退 |
| 4 | ❓ | `resource_guard.py` | 死代码 `_CIRCUIT_KEY` | **已删** |

## 五、回溯对照

PRD → 方案 → 代码可追溯：

- AC-1 ResourceGuard 无独立熔断 → `_state`/`_failure_count`/`_last_failure_time`/`_open_at` 全部删除，改用 GatewayCircuitState
- AC-2 只有一个 CONTRADICTION_PAIRS → agents 从 scheduler 导入，单点维护
- AC-4 空目录处理 → 3 删除 + 2 填充
- AC-B1 上下文注入 -30% → `extract_relevant_context()` 按关键词裁剪
- AC-B2 简洁规则 → RULES_BLOCK #9

---
> 关联：[[阶段1-PRD-内部减熵]] [[阶段1-PRD-业务层减熵]]
