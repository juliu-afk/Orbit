# PR #241 R5 复审 — 第五轮

> **Commit**: `5813001e` (commit 7: "R4——on_task_end从trajectory读tier + get_router_agent()")
> **审查范围**: wiring.py 变更（+32/-9）+ 全链路 5 方向验证
> **R4 → R5 变化**: 新增 commit 7，声称修复 R4 的 P0-1 和 P0-3

---

## R4 → R5 修复追踪

### R4-P0-1: `_last_tier` 空字符串 → Bandit 不学习

**commit 7 "修复"**: `on_task_end` 不再依赖 `_last_tier`，改为从 **trajectory DB** 读取 `model_tier` 字段：

```python
row = tc._db.execute(
    "SELECT model_tier FROM trajectories WHERE trajectory_id=?",
    (traj_id,)).fetchone()
tier = (row["model_tier"] if row else "") or self._last_tier
```

**验证结果**: ❌ **仍死**

问题不在读取端，而在**写入端**——`model_tier` 永远是空字符串：

| 写入路径 | 状态 |
|---------|------|
| `start_trajectory(model_tier="")` | 默认空，`on_task_start` 不传参 |
| `on_model_tier_decided(task_id, tier)` → `tc.set_model_tier()` | **零调用方** |
| `wiring.set_model_tier(tier)` | **零调用方** |

**根因**：`runner.py` 的任务生命周期中**从不调用** `RouterAgent.evaluate()`：

```
runner.py lifecycle:
  1. on_task_start(task_id, prd, project_id)     ← 创建 trajectory, model_tier=""
  2. load_profile(project_id)
  3. start_monitor(task_id, goal)
  4. _agent_cycle loop                            ← ❌ 没有 RouterAgent.evaluate()
  5. on_task_end(task_id, outcome, 0.8, turns)    ← 读 model_tier="" → if tier: False → 跳过
```

**结论**：修复了读取端（从 DB 读），但 DB 列从未被写入。Bandit 仍然永远不学习。

### R4-P0-3: RouterAgent 零生产实例化

**commit 7 "修复"**: 新增 `get_router_agent()` 方法：

```python
def get_router_agent(self):
    from orbit.router.agent import RouterAgent
    return RouterAgent(
        weights=None,
        bandit=self._get_bandit(),
        drift_detector=self._get_drift(),
    )
```

**验证结果**: ❌ **仍死**

```
grep -rn "get_router_agent" src/orbit/ → 零调用方
```

`get_router_agent()` 被定义了，但 `runner.py` / `context.py` / API 层**没有任何代码调用它**。RouterAgent 从未被创建，`evaluate()` 从未执行，bandit/drift 从未被使用。

### R4-P0-2: CUSUM latency_ms=0 假告警

**状态**: 未在本 commit 修复。CUSUM 在 commit 5 已从 `on_task_end` 移除，当前零反馈路径。

### R4-P0-4: type_sig 启发式

**状态**: 未在本 commit 修复。仅 goal 含 `def`/`List[`/`Optional[` 时触发。

### R4-P0-5: GEPA conformal

**状态**: 未在本 commit 修复。GEPAEngine 零生产创建。

---

## 5 方向最终状态（第 5 轮）

| 方向 | 模块 | 宿主接受参数 | 创建传参 | 调用链完整 | 状态 |
|------|:----:|:----------:|:------:|:--------:|:----:|
| D2 Bandit | ✅ | ✅ | ✅ getter | ❌ `evaluate()` 不调用 → tier 永空 | 🔴 DEAD |
| D13 PID | ✅ | ✅ | ✅ | ✅ | 🟢 ALIVE |
| D8 TypeDirected | ✅ | ✅ | ⚠️ 启发式 | ⚠️ 仅代码生成 | 🟡 PARTIAL |
| D16 Conformal | ✅ | ✅ | ✅ init | ❌ GEPAEngine 零创建 | 🔴 DEAD |
| D20 CUSUM | ✅ | ✅ | ✅ getter | ❌ 零反馈路径 | 🔴 DEAD |

---

## 问题清单

### P0-1（保留）：model_tier 永不写入 → Bandit 读取空字符串

**严重性**: 🔴 P0 — 阻塞合并

commit 7 修复了读取端（从 DB 读），但写入端仍然全断。需要在 `runner.py` 的 `on_task_start` 和 `_agent_cycle` 之间插入：

```python
router = w.get_router_agent() if w else None
if router:
    result = router.evaluate(prd)
    w.on_model_tier_decided(task_id, result.tier)
```

**验证命令**：
```bash
grep -rn "on_model_tier_decided" src/orbit/ --include="*.py" | grep -v "def on_model"
# 结果：零行
grep -rn "get_router_agent" src/orbit/ --include="*.py" | grep -v "def get_router"
# 结果：零行
```

### P0-2（保留）：RouterAgent.evaluate() 零生产调用

**严重性**: 🔴 P0 — 阻塞合并

`get_router_agent()` 已定义但零调用方。RouterAgent 的 `bandit.select()` 和 `drift_detector.update()` 都无法执行。

### P1-1（保留）：CUSUM 完全断联

commit 5 从 `on_task_end` 移除了 CUSUM 调用，commit 7 未恢复。CUSUM 现在零反馈路径。

### P1-2（保留）：GEPA conformal 零生产实例化

GEPAEngine 从未在生产代码中创建。

---

## 4 轮修复模式分析

| 轮次 | 修复策略 | 结果 |
|------|---------|------|
| R2→R3 | commit 4: 加 getter 方法 | 5 个 getter 全死（无调用方） |
| R3→R4 | commit 5: 补传参 + 读 DB | 1/5 通（PID），4/5 断在最后一公里 |
| R4→R5 | commit 7: 改读 DB 列 | 仍死——DB 列从不被写入 |

**根因不变**：每轮修复**审查报告指出的具体代码行**，但不验证**完整调用链端到端可达**。缺少一个从 `task_runner` 调用 `RouterAgent.evaluate()` → `on_model_tier_decided()` → 写入 DB → `on_task_end` 读取 → `bandit.update()` 的集成测试。

---

## 结论

❌ **不建议合并** — 第 5 轮，ALIVE 1/5 + PARTIAL 1/5 + DEAD 3/5

commit 7 的改进是真实的——`_trajectory_ids` 字典 + `traj.trajectory_id` 返回值修复了 traj_id 匹配问题（R2 P0-2），`on_task_end` 从 DB 读取的思路正确。但**最关键的一环缺失**：没有任何代码调用 `RouterAgent.evaluate()` 来产生 model_tier 决策。所有下游链路（bandit.update / drift_detector.update）都因为 tier 为空而静默跳过。

**最小修复**（3 行）：
```python
# runner.py, 在 on_task_start 之后、_agent_cycle 之前
router = w.get_router_agent() if w else None
if router:
    w.on_model_tier_decided(task_id, router.evaluate(prd).tier)
```

---

*审查人: WB R5 | 审查时间: 2026-07-08*
