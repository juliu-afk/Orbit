# PR #241 R4 复审 — feat(theory): P0五方向

**PR**: [#241](https://github.com/juliu-afk/Orbit/pull/241)
**Commit**: `8ae21299` (6 commits, open)
**复审时间**: 2026-07-08 R4

---

## 结论：2 P0 + 2 P1 — ❌ 不建议合并（第 4 轮）

Commit 5 标题"R3全修——五方向全接通"。逐条验证后：**5 个 P0 逐条"修复"，但每条修复都断在最后一公里**。

---

## R3 P0 修复逐条追踪

### R3-P0-1：`_last_tier` 空字符串 → ❌ 未真正修复

**修复内容**：`on_model_tier_decided` 中新增 `self._last_tier = model_tier`（wiring.py L114）

**问题**：`on_model_tier_decided()` **全代码库零调用方**。没有任何生产代码调用此方法。

```
grep -rn "on_model_tier_decided" src/ tests/ --include="*.py" | grep -v "def on_model"
# 结果: 空
```

`set_model_tier()` 同样零调用方。`_last_tier` 初始值 `""`，`if b and self._last_tier:` 中空字符串为 falsy → **Bandit 反馈块仍然永远不执行**。

### R3-P0-2：CUSUM `latency_ms=0` 假告警 → ❌ 修复方式导致 CUSUM 彻底断联

**修复内容**：从 `on_task_end` 中**完全移除** CUSUM 调用（wiring.py L128-134）

**问题**：移除了假告警来源，但 CUSUM 现在**完全没有任何反馈路径**。`_get_drift()` getter 存在但 `on_task_end` 不再调用 `d.update()`。CUSUM 从"每次假告警"变成"永不运行"。方向 20 **比修复前更死**。

### R3-P0-3：RouterAgent 未注入 bandit/drift → ❌ 未修复

**commit 消息声称**："wiring暴露create_router_agent"

**实际代码**：`grep -rn "create_router_agent" src/orbit/` → **零结果**。方法不存在。RouterAgent 仍只在文档字符串示例中出现，生产代码中**从不实例化**（无论传不传 bandit）。

### R3-P0-4：enhance_prompt 未传 type_sig → ⚠️ 表面修复

**修复内容**：agent.py L221-223 从 goal 提取 type_sig：

```python
type_sig = goal if "def " in goal or "List[" in goal or "Optional[" in goal else ""
```

**问题**：仅在 goal 文本包含 Python 类型注解关键字时 type_sig 非空。典型业务任务 goal 是自然语言（如"审计2024年应收账款"），不含 `def`/`List[`/`Optional[` → type_sig 为空 → TypeDirectedSynthesizer 不执行。

**结论**：对代码生成任务**部分有效**，对审计/财税业务任务**完全无效**。

### R3-P0-5：GEPAPopulation 未传 conformal → ❌ 未真正修复

**修复内容**：`GEPAEngine.__init__` 接受 `conformal` 参数并传给 `GEPAPopulation(conformal=conformal)`

**问题**：`GEPAEngine` 本身**全代码库零生产创建**。唯一出现位置是 `gepa.py` L103 的**文档字符串示例**：

```python
"""GEPA Prompt 进化引擎。

用法:
    engine = GEPAEngine(llm=llm, distill=de)  # ← docstring，不是生产代码
"""
```

`grep -rn "GEPAEngine(" src/orbit/` 排除 docstring 后**零结果**。GEPA 整个进化管线不在生产路径中，conformal 注入到 GEPAPopulation 也无意义。

---

## R3 P1 修复追踪

### R3-P1-1：`_nonconformity` 忽略 task → ⚠️ 弱修复

**修复内容**：新增 task-code 词重叠惩罚：

```python
task_words = set(task.lower().split())
code_words = set(code.lower().split())
overlap = len(task_words & code_words) / max(len(task_words | code_words), 1)
semantic_penalty = (1.0 - overlap) * 0.5 if task_words else 0.0
```

**问题**：实际场景中 task（如 `"audit"`）和 code（如 `"good code"`）词集几乎不重叠，penalty 值相同：

```python
>>> cp.p_value("audit", "good code") == cp.p_value("coding", "good code")
True  # 仍然相同
```

语义分离在原理上实现了，但词级 Jaccard 重叠对短文本（单字 task）效果极差。

### R3-P1-2：假覆盖测试 → ✅ 已移除，但未替换

旧测试 `test_p_value_different_task_same_code`（断言 `0<=p<=1` 恒真）已删除。但未新增有意义的差异化测试。`test_p_value_range` 仍只断言 `0<=p<=1`。

---

## 5 方向最终状态

| 方向 | R2 | R3 | R4 (commit 5) | 变化 |
|------|:--:|:--:|:--:|------|
| D2 Bandit | 死代码 | 死代码 | **仍死代码** | `_last_tier` 写入路径存在但零调用方 |
| D13 PID | 死代码 | ✅ 接通 | ✅ 接通 | 无退化 |
| D8 TypeDirected | 死代码 | 死代码 | **部分接通** | 仅代码生成任务有效 |
| D16 Conformal | 死代码 | 死代码 | **仍死代码** | GEPAEngine 零生产创建 |
| D20 CUSUM | 死代码 | 死代码（假告警） | **更死** | on_task_end 移除后零反馈路径 |

**ALIVE: 1/5，PARTIAL: 1/5，DEAD: 3/5**

---

## 系统性问题诊断

本 PR 经过 **4 轮审查**，每轮"修复"都遵循同一模式：

1. **定点修复**：针对审查报告指出**具体代码位置**做最小修改
2. **不验证调用链**：修复了"写了什么"但不验证"谁调用它"
3. **引入新断裂**：修复 A 时断开 B（如移除 CUSUM 解决假告警，但 CUSUM 彻底断联）

**根因**：缺少从 `task_runner → wiring.on_model_tier_decided → _last_tier → on_task_end → bandit.update` 的**端到端集成测试**。每个模块的单元测试全绿，但组装后的链路从未被验证。

---

## 正面发现

1. **commit 5 CUSUM 冷却期**（继承 commit 4）：`_COOLDOWN_WINDOW = 10` + 测试覆盖正确
2. **GEPA `p_value(category, principle)`** + `_nonconformity` task 参数参与计算：方向正确（虽然效果弱）
3. **PID 方向从 R3 起完整接通**：`wiring._get_monitor() → MonitorAgent(pid=pid) → check_now() → compute()`
4. **测试精简**：从 21 个含假覆盖测试缩减到 19 个有意义的测试，全部通过
5. **type_sig 提取逻辑**：对纯代码生成任务有效（goal 含 Python 类型注解时触发）

---

## 合并建议

**❌ 不建议合并。** 需要 1 个端到端集成测试验证以下链路：

```
task_runner 创建任务
  → RouterAgent.evaluate() 选 tier
    → wiring.on_model_tier_decided(task_id, tier)   ← 当前零调用
      → _last_tier = tier
  → 任务执行
  → wiring.on_task_end(task_id, outcome)
    → bandit.update(_last_tier, success)             ← 当前 _last_tier 空
```

没有这个集成测试，"接线但未通电"问题将在后续 PR 中持续重现。