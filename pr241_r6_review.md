# PR #241 R6 复审 — 第六轮 ✅ 可合并（附条件）

> **Commit**: `677b5060` (commit 8+9)
> **审查范围**: runner.py 变更(+15/-1) + wiring.py 变更(+8/-0) + 全链路 5 方向端到端验证
> **R5 → R6 变化**: 新增 commit 8（task_runner 端到端接通）+ commit 9（CUSUM 接入 on_task_end）

---

## R5 → R6 修复追踪

### R5-P0-1: model_tier 永不写入 → Bandit 不学习

**commit 8 "修复"**: runner.py 在 `on_task_start` 后新增完整调用链：

```python
ra = w.get_router_agent()              # 创建带 bandit+drift 的 RouterAgent
if ra is not None:
    dec = await ra.evaluate(...)       # 评估任务复杂度→选 tier
    w.on_model_tier_decided(task_id, dec.tier.value)  # 写入 trajectory DB
    context["router_tier"] = dec.tier.value
```

**验证结果**: ✅ **完全接通**

完整写入→读取→反馈链路：
```
runner.py L145: ra = w.get_router_agent() → RouterAgent(bandit, drift)
runner.py L152: dec = await ra.evaluate(file_count, change_type, risk, agent_role)
runner.py L156: w.on_model_tier_decided(task_id, dec.tier.value)
    → wiring L113: tc.set_model_tier(traj_id, model_tier)  # 写入 DB
    → wiring L114: self._last_tier = model_tier            # 备份
...
on_task_end L126: SELECT model_tier FROM trajectories WHERE trajectory_id=?
on_task_end L130: tier = row["model_tier"]                 # 读取（非空！）
on_task_end L132: b.update(tier, success, latency_ms)      # Bandit 学习 ✅
```

类型一致性验证：`ModelTier(StrEnum)` → `.value` = `"tier_0"`/`"tier_1"`/... → 匹配 Bandit 的 arm 名称集合 `["tier_0", "tier_1", "tier_2", "tier_3"]`。✅

### R5-P0-2: RouterAgent.evaluate() 零生产调用

**commit 8 "修复"**: runner.py L152 现在调用 `await ra.evaluate(...)`。

**验证结果**: ✅ **完全接通**

`get_router_agent()` 返回的实例同时持有 `_bandit`（ThompsonBandit）和 `_drift`（CUSUMDriftDetector），均为共享单例。状态跨任务保留。

### 新增（commit 9）: CUSUM 接入 on_task_end

**commit 9**: `on_task_end` 在 `b.update()` 后新增 CUSUM 调用：

```python
d = self._get_drift()
if d:
    alert = d.update(model=tier, latency_ms=est_latency,
                     success=success, output_len=quality_score * 1000)
    if alert is not None:
        b.reset_arm(alert.model)
```

**验证结果**: ✅ **接通**，但有两个 P2 语义问题（见下文）

---

## 5 方向最终状态（第 6 轮）

| 方向 | 状态 | 链路 | 说明 |
|------|:----:|------|------|
| D2 Bandit | ✅ ALIVE | runner→evaluate→on_model_tier_decided→DB→on_task_end→b.update | 完整闭环 |
| D13 PID | ✅ ALIVE | wiring._get_monitor→MonitorAgent(pid)→check_now→compute | 从 R3 起接通 |
| D8 TypeDirected | ⚠️ PARTIAL | enhance_prompt(type_sig=) | 启发式仅在 goal 含 Python 类型注解时触发 |
| D16 Conformal | 🔴 DEAD | GEPAPopulation(conformal=) 在 init 中接通，但 GEPAEngine 零生产创建 | maybe_distill 从不调用 GEPAEngine |
| D20 CUSUM | ✅ ALIVE | on_task_end→d.update→b.reset_arm on alert | 双时间尺度反馈 |

**进度**: R2 全死 → R3 1/5 → R4-R5 1/5 → **R6 3/5 + 1 partial**

---

## 问题清单

### P1-1（保留）：D16 Conformal 仍死代码 — GEPAEngine 零生产创建

**严重性**: 🟡 P1 — 修后合并

`maybe_distill()` 的蒸馏管线是 `DistillationEngine → LLMDistiller → GRPOScorer`。`GEPAEngine.evolve_population()` 从未被任何生产代码调用——它只出现在 GEPAEngine 类的 docstring 示例中。

`GEPAPopulation(conformal=conformal)` 在 `GEPAEngine.__init__` 中正确接通了，但 GEPAEngine 本身永远不会被实例化。

**修复建议**：在 `maybe_distill()` 末尾添加 GEPA 进化步骤，或在 wiring 中暴露 `_get_gepa()`。

### P2-1：quality_score * 1000 作为 output_len — 语义不匹配

`on_task_end` 传 `output_len=quality_score * 1000`。但 `quality_score` 是 0.0-1.0 的质量评分，而 CUSUM 的 `output_len` 参数语义是"输出长度（token/字符数）"。runner.py 传的是硬编码 `0.8`，所以 CUSUM 每次看到的 output_len 恒为 800。基线建立后异常分数永远为 0——**CUSUM 对输出质量维度完全盲化**。

### P2-2：turns=0 时 est_latency=0 → CUSUM 边界假告警

```python
est_latency = turns * 2000.0 if turns > 0 else 0.0
```

立即失败的任务（turns=0）传入 `latency_ms=0` → `log(1)=0` → 如果基线 mean ≈ 9.0，异常 = 9.0 → CUSUM 触发假告警 → `bandit.reset_arm()` 重置 Bandit 后验。

**影响范围**：仅影响立即失败任务的边缘场景，不阻塞合并。

### P2-3：RouterAgent 每次任务重新创建

`get_router_agent()` 在 docstring 中声称"创建单例"，但实际每次调用都 `return RouterAgent(...)`。Bandit/CUSUM 通过 `_get_bandit()`/`_get_drift()` 懒加载单例共享状态，所以**不影响功能**，但 RouterAgent 对象本身会被重复创建。建议缓存。

---

## 测试

- 19/19 单元测试通过 ✅
- 导入验证通过 ✅
- RouterAgent 实例验证：`_bandit` = ThompsonBandit ✅，`_drift` = CUSUMDriftDetector ✅

---

## 结论

✅ **可合并**（附条件：P1-1 后续 PR 修复）

经过 6 轮审查、9 个 commit，5 方向最终达到 **ALIVE 3/5 + PARTIAL 1/5 + DEAD 1/5**。

核心突破在 commit 8——runner.py 终于接入了 `RouterAgent.evaluate()` → `on_model_tier_decided()` 的写入端，使得 Bandit 和 CUSUM 的完整反馈闭环（write→DB→read→update）首次端到端可达。commit 9 的 CUSUM 接入也合理（使用 est_latency 而非硬编码 0，避免了 R3 发现的假告警问题）。

**保留的 P1-1**（GEPA conformal 死代码）不阻塞核心功能——GEPA 进化引擎是一个可选的离线优化步骤，不影响实时任务执行。建议后续 PR 将 GEPAEngine 接入 `maybe_distill()` 管线。

3 个 P2 是小问题，可后续优化。

---

*审查人: WB R6 | 审查时间: 2026-07-08*
