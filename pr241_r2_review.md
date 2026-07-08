# PR #241 R2 复审 — feat(theory): P0五方向

**PR**: [#241](https://github.com/juliu-afk/Orbit/pull/241)
**Commit**: `9ac2560b` (3 commits, open)
**复审时间**: 2026-07-08

---

## R2 发现汇总

| # | 级别 | 问题 | 影响 |
|---|------|------|------|
| P0-1 | 🔴 阻塞 | **五个方向全部接线但未通电** — 0/5 有生产调用方 | 整个 PR 产出 +1028 行零生产价值 |
| P0-2 | 🔴 阻塞 | R1 P1-1 修复无效 — `update_bandit()` 方法已加但 task_runner 从不调用 | Bandit 永远不学习，Thompson Sampling 退化为均匀随机 |
| P1-1 | 🟡 修后合 | GEPA ConformalPredictor 语义误用 — `p_value(principle, principle)` 传入相同文本 | 即使接线，筛选永不过滤任何原则 |
| P1-2 | 🟡 修后合 | ConformalPredictor `predict()` 硬编码 `success=True` | 只按代码长度和"error"计数筛选，丢失核心 nonconformity 信号 |
| P2-1 | 🔵 建议 | CUSUM Fisher 方法统计不严谨 — `(1-m)` 当 p-value 使用 | 非统计有效的组合方法，但功能上可用 |
| P2-2 | 🔵 建议 | CUSUM 变点后立即重置+重更新基线 → 连续触发 | 模拟测试中 20 次 drift 调用产生 20 次告警（应只 1 次） |

---

## P0-1 — 五方向全部零生产接线

这是本项目"接线但未通电"系统性问题的最极端案例。以下逐方向验证：

### 方向 2: Bandit (ThompsonBandit)

| 检查项 | 结果 |
|--------|------|
| 模块算法正确 | ✅ select/update/reset 功能验证通过 |
| `RouterAgent.__init__` 接受 `bandit` 参数 | ✅ |
| `evaluate()` 中调用 `bandit.select()` | ✅ |
| **RouterAgent 创建时传入 bandit** | ❌ `agent.py:101`: `RouterAgent(weights=ScoreWeights.from_env())` |
| **task_runner 调用 `update_bandit()`** | ❌ 全代码库 grep: 零调用方 |

**链路**：模块定义 ✓ → 参数接受 ✓ → evaluate 调用 ✓ → **实例化 ✗ → 反馈更新 ✗**

### 方向 13: PID (PIDAgentController)

| 检查项 | 结果 |
|--------|------|
| 模块算法正确 | ✅ Kp/Ki/Kd 计算正确，四级映射合理 |
| `MonitorAgent.__init__` 接受 `pid_controller` 参数 | ✅ |
| `check_now()` 中调用 `pid.compute()` | ✅ |
| **wiring `_get_monitor()` 创建时传入 pid** | ❌ `wiring.py:322`: `MonitorAgent()` — 无参 |

### 方向 8: TypeDirectedSynthesizer

| 检查项 | 结果 |
|--------|------|
| 模块算法正确 | ✅ free theorem 推导 + import 推断 |
| `wiring.enhance_prompt()` 接受 `type_sig` 参数 | ✅ commit 3 已加 |
| **`enhance_prompt` 调用时传 `type_sig`** | ❌ `agent.py:221`: `enhance_prompt(system, category="", keywords=kw)` — 无 type_sig |

### 方向 16: ConformalPredictor

| 检查项 | 结果 |
|--------|------|
| 模块算法正确 | ✅ Inductive CP 公式正确 |
| `GEPAPopulation.__init__` 接受 `conformal` 参数 | ✅ |
| **GEPAPopulation 创建时传入 conformal** | ❌ `gepa.py:119`: `GEPAPopulation()` — 无参 |
| **`p_value()` 调用语义** | ❌ 见 P1-1 |

### 方向 20: CUSUMDriftDetector

| 检查项 | 结果 |
|--------|------|
| 模块算法正确 | ✅ CUSUM 积分逻辑正确 |
| `RouterAgent.__init__` 接受 `drift_detector` 参数 | ✅ |
| **RouterAgent 创建时传入 drift_detector** | ❌ 同 Bandit |
| **`update_drift()` 被 task_runner 调用** | ❌ 全代码库 grep: 零调用方 |

---

## P0-2 — R1 P1-1 修复无效

R1 要求新增 `update_bandit()` 方法供 task_runner 调用。commit 2 (`d9a629ab`) 添加了方法：

```python
# router/agent.py L218-226
def update_bandit(self, tier: str, success: bool, latency_ms: float = 0.0) -> None:
    if self._bandit is not None:
        from orbit.router.bandit import is_bandit_enabled
        if is_bandit_enabled():
            self._bandit.update(tier, success, latency_ms)
```

方法本身正确，但 **task_runner 从不调用它**：
```
grep -rn "\.update_bandit(" src/orbit/ → 0 hits (排除 def)
grep -rn "update_bandit\|update_drift" src/orbit/scheduler/ → 0 hits
```

**效果**：R1 P1-1 标记为"已修复"但实际只完成了一半——方法存在但没有调用方。Bandit 的 Beta 后验永不更新，`select()` 永远从先验 `Beta(1,1)` = `Uniform(0,1)` 采样，等同于纯随机选择。

`update_drift()` 同理——方法存在但零调用方。

---

## P1-1 — GEPA ConformalPredictor 语义误用

即使 `GEPAPopulation(conformal=cp)` 被正确传入，`select_elite` 的调用也有语义错误：

```python
# gepa.py L68
p_val = self._conformal.p_value(p.principle, p.principle)  # ← 同一文本传两次
```

`ConformalPredictor.p_value(task, code)` 的设计语义是：
- `task`: 任务描述
- `code`: 生成的代码
- `_nonconformity` 计算代码中的 "error" 出现次数和代码长度

但 GEPA 传入 `(principle.principle, principle.principle)` ——策略原则文本被同时当作 task 和 code。策略原则中几乎不会包含 "error" 字样，长度也远短于代码。

**验证**：
```python
cp.calibrate([('t','good code',True)]*10 + [('t','bad error error',False)]*5)
cp.p_value('Always validate inputs', 'Always validate inputs')  # → 0.375
cp.p_value('Use type hints', 'Use type hints')                  # → 0.375
# 所有原则 p > 0.05 → 全部保留 → 等同无筛选
```

---

## P1-2 — ConformalPredictor.predict() 硬编码 success=True

```python
# conformal.py L55
score = self._nonconformity(task, code, True)  # ← 硬编码 success=True
```

`_nonconformity` 中 `success=False → base=3.0`，`success=True → base=0.0`。predict 永远用 `success=True`，意味着 **非一致性评分只看代码长度和 "error" 计数**，丢弃了最核心的信号（任务是否成功）。

---

## P2-1 — CUSUM Fisher 方法统计不严谨

```python
# drift_detector.py L107-110
combined = -2 * sum(
    math.log(max(1.0 - min(m, 0.99), 0.001))
    for m in metrics_anomaly.values()
)
```

Fisher 方法要求 `p_i` 是有效的 p-value ∈ (0,1)。但代码用 `(1 - anomaly_score)` 近似 p-value——anomaly_score 本身不是 p-value，没有经过校准。这个组合不是统计有效的，但作为启发式异常检测器功能上可用。

---

## P2-2 — CUSUM 变点后无冷却期

变点检测后，`_cusum` 重置为 0 并立即 `_update_baseline()`。但新基线基于当前窗口（包含了 drift 数据），下次 `update()` 时如果 drift 持续，anomaly 相对新基线仍大 → CUSUM 立即重新积累 → 连续告警。

**模拟验证**：20 次 drift 调用产生 **20 次 DriftAlert**（每次都触发+重置+再触发）。应有冷却期或重置后提高阈值。

---

## ✅ 验证通过的部分

| 项 | 结果 |
|----|------|
| ThompsonBandit select/update/reset | ✅ Beta 后验数学正确 |
| PIDAgentController 四级映射 | ✅ subtle/gentle/firm/urgent 阈值合理 |
| ConformalPredictor 数学公式 | ✅ calibrate/predict/p_value 公式正确（使用方式有误） |
| CUSUMDriftDetector 基本功能 | ✅ 正常数据不误报，drift 数据能检测 |
| TypeDirectedSynthesizer | ✅ free theorem + import 推断正确 |
| 18 单元测试 | ✅ 全部通过 |
| 0 新依赖 | ✅ 纯 stdlib |
| commit 2 修复 R1 P1-1 | ⚠️ 方法已加但无调用方 |
| commit 2 修复 R1 P2-1/P2-2 | ✅ update_drift 方法已加（同无调用方） |
| commit 3 修复 R1 P2-3 | ⚠️ enhance_prompt 加了 type_sig 参数（同无调用方传参） |

---

## R1 对比

| R1 结论 | R2 验证 |
|---------|---------|
| P1-1: update_bandit 缺失 → commit 2 已修 | ❌ 方法已加但 task_runner 从不调用 |
| P2-1: _drift 未使用 → commit 2 已修 | ❌ update_drift 方法已加但从不调用 |
| P2-2: statistics 导入 → commit 2 已删 | ✅ |
| P2-3: constrain 无调用方 → commit 3 已修 | ❌ enhance_prompt 加了参数但 agent.py 不传 |
| AC: "18 tests pass" | ✅ 但只测模块自身，不测接线 |
| AC: "Bandit select/update 正确" | ✅ 但零生产接线 |

R1 检查了"方法是否存在"和"算法是否正确"，但未检查"是否被实际调用"。

---

## 总体结论

❌ **2 P0 + 2 P1 需修复**

本 PR 是 Orbit 项目"接线但未通电"系统性问题的**最极端案例**：5 个方向 × ~200 行/方向 = ~1000 行高质量理论实现，但**零生产接线**。每个方向都遵循同一模式：

1. 模块算法正确 ✅
2. 宿主类接受参数 ✅
3. 宿主类方法逻辑正确 ✅
4. **宿主类创建时不传参** ❌ ← 断点在这里
5. **task_runner 从不调用反馈方法** ❌ ← 断点在这里

R1 的修复（commit 2/3）走了同样的路径——加方法但不加调用方，加参数但不传值。这让 PR 表面上从"1 P1 + 3 P2"变成了"全绿"，但实质上五个方向全部是死代码。

**建议**：本 PR 不应合并。需要在 task_runner / wiring / RouterAgent 创建处完成实际接线后再提交。具体需要：
1. `task_runner/runner.py` 中创建 `RouterAgent(bandit=..., drift_detector=...)` 并在任务结束时调用 `update_bandit()` / `update_drift()`
2. `wiring.py` `_get_monitor()` 中创建 `MonitorAgent(pid_controller=PIDAgentController())`
3. `agent.py` `enhance_prompt` 调用传入 `type_sig`（从当前任务的函数签名提取）
4. `gepa.py` `GEPAPopulation(conformal=...)` 传入实例，并修复 `p_value` 调用语义
