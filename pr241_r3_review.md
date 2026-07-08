# PR #241 R3 复审 — feat(theory): P0五方向

**PR**: [#241](https://github.com/juliu-afk/Orbit/pull/241)
**Commit**: `3163b5b5` (4 commits, open)
**复审时间**: 2026-07-08 R3

---

## 结论：2 P0 + 2 P1 + 1 P2 — ❌ 不建议合并

R2 报告 2 P0 + 2 P1，commit 4 标题"R2全修"。实际验证：**5 个方向中仅 1 个（PID）真正接通**，其余 4 个仍在"接线但未通电"状态。此外发现 commit 4 引入 2 个新 P0。

---

## R2 问题修复追踪

### R2-P0-1：五方向生产接线 → ❌ 仅 1/5 修复

| 方向 | _get_*() getter | on_task_end 调用 | 宿主创建传参 | 反馈闭环 | 状态 |
|------|:-:|:-:|:-:|:-:|------|
| D2 Bandit | ✅ 新增 | ✅ `b.update()` | ❌ `RouterAgent()` 未传 bandit | ❌ `_last_tier` 空 | **仍死代码** |
| D13 PID | ✅ 新增 | — | ✅ `MonitorAgent(pid=pid)` | ✅ `check_now()` 调用 `compute()` | **已接通** |
| D8 TypeDirected | — | — | ❌ `enhance_prompt()` 未传 `type_sig` | — | **仍死代码** |
| D16 Conformal | ✅ 新增 | — | ❌ `GEPAPopulation()` 未传 conformal | ❌ `_get_conformal()` 零调用方 | **仍死代码** |
| D20 CUSUM | ✅ 新增 | ✅ `d.update()` | ❌ `RouterAgent()` 未传 drift | ❌ `_last_tier` 空 | **仍死代码** |

### R2-P0-2：`_last_tier` 空字符串 → ❌ 未修复（升级为新 P0-1）

`wiring.set_model_tier()` 方法**存在但零调用方**。`_last_tier` 初始值 `""`（空字符串），`on_task_end` 中：

```python
if b and d and self._last_tier:   # ← "" 是 falsy，条件永远为 False
    ...
    b.update(self._last_tier, success)  # 永远不执行
```

**验证**：

```python
>>> bool("")  # 空字符串是 falsy
False
>>> from orbit.router.bandit import ThompsonBandit
>>> b = ThompsonBandit(['tier_0','tier_1','tier_2','tier_3'])
>>> b.update("", True)  # 空 arm 不在 posteriors 中
>>> b.posteriors  # 无变化
{'tier_0': {'alpha': 1.0, 'beta': 1.0}, ...}  # 先验未动
```

`on_model_tier_decided()` 将 tier 存入 **TrajectoryCollector**（`tc.set_model_tier(traj_id, model_tier)`），而非 `wiring._last_tier`。两个 `set_model_tier` 同名但不同对象，数据流断裂。

### R2-P1-1：Conformal `p_value` 语义 → ⚠️ 表面修复，实质未修

commit 4 将 `p_value(p.principle, p.principle)` 改为 `p_value(p.category or "general", p.principle)`。但 `_nonconformity(task, code)` 签名接收 `task` 参数后**完全忽略它**：

```python
@staticmethod
def _nonconformity(task: str, code: str, success: bool | None = None) -> float:
    base = 0.0
    if success is not None:
        base = 0.0 if success else 3.0
    lint = code.lower().count("error") * 0.5
    length = len(code) / 5000.0
    return base + lint + length    # ← task 从未参与计算
```

**验证**：

```python
>>> cp.p_value("audit", "good code") == cp.p_value("coding", "good code")
True   # 不同 task 产生完全相同的 p-value
```

### R2-P1-2：CUSUM 冷却期 → ✅ 已修复

新增 `_cooldown` 字典 + `_COOLDOWN_WINDOW = 10`。变点检测后 10 次更新内不重触发。测试 `test_cooldown_prevents_repeat_alerts` 验证正确。

---

## 新发现问题

### P0-1（阻塞）：`on_task_end` 传 `latency_ms=0` 给 CUSUM → 首次调用必触发假告警

**文件**: `src/orbit/integration/wiring.py` L131

```python
alert = d.update(model=self._last_tier, latency_ms=0, success=success, output_len=0)
```

`latency_ms=0` → `log(max(0, 1)) = log(1) = 0`。基线 `latency_log_mean ≈ 6.9`（来自首次调用的真实延迟）。异常分数 = `|0 - 6.9| / 1.0 = 6.9`。

```python
import math
# Fisher 联合（正常成功场景）:
# success anomaly = |1.0 - 0.9| = 0.1
# latency anomaly = 6.9
# output anomaly = 0 (output_len=0 跳过)
combined = -2 * (math.log(0.9) + math.log(max(1 - 0.99, 0.001)))
#         = -2 * (-0.105 + (-6.908))
#         = 14.03
# cusum increment = 14.03 - 1.0 = 13.03 > h=5.0
```

**每个任务结束后都会触发假变点告警**，导致 `bandit.reset_arm()` 被调用，Bandit 后验被重置为先验——**Bandit 永远无法收敛**。

### P0-2（阻塞）：`RouterAgent` 单例创建不传 `bandit` / `drift_detector`

**文件**: `src/orbit/router/agent.py` L101

```python
agent = RouterAgent(weights=ScoreWeights.from_env())
#          ↑ 未传 bandit=...  也未传 drift_detector=...
```

`wiring._get_bandit()` 和 `_get_drift()` 创建的实例**从未注入 RouterAgent**。RouterAgent.evaluate() 中 `if self._bandit is not None:` 永远为 False，Bandit 选择逻辑永远不执行。

### P1-1：`test_p_value_different_task_same_code` 是假覆盖测试

**文件**: `tests/unit/test_p0_five.py`

```python
def test_p_value_different_task_same_code(self):
    ...
    p1 = cp.p_value("audit", "good code")
    p2 = cp.p_value("coding", "good code")
    assert 0 <= p1 <= 1 and 0 <= p2 <= 1  # ← 恒真断言
```

`p_value` 返回值 `(count_ge + 1) / (n + 1)`，数学上**永远**在 `[0, 1]` 区间。此断言**不可能失败**，不验证"不同 task 产生不同 p-value"这一声称的功能。

### P1-2：`conformal.py` 删除 59 行文档注释

commit 4 将 `conformal.py` 从 80 行缩减到 50 行，删除了类文档字符串、方法文档字符串和数学保证说明（如"分布无关""有限样本有效"）。代码功能不变但可维护性下降。

---

## 正面发现

1. **Monitor `_process_event` dict 修复**（继承自 #229）：`isinstance(event, dict)` 分支正确处理 dict 事件，修复了 #229 的 P0-1
2. **PID 方向完整接通**：`wiring._get_monitor()` → `MonitorAgent(pid_controller=pid)` → `check_now()` → `pid.compute()` → PID 信号注入 Alert 系统
3. **CUSUM 冷却期**：`_COOLDOWN_WINDOW = 10` 有效防止连续触发，单元测试覆盖
4. **GEPA p_value 调用语义**：`p_value(category, principle)` 比 `(principle, principle)` 更合理（虽然 _nonconformity 忽略 task 参数）

---

## 修复优先级

| # | 级别 | 问题 | 修复方案 | 工作量 |
|---|------|------|---------|--------|
| P0-1 | 🔴 | `_last_tier` 空字符串 | `on_model_tier_decided` 中追加 `self._last_tier = model_tier` | 1 行 |
| P0-2 | 🔴 | CUSUM `latency_ms=0` 假告警 | `on_task_end` 传入真实 latency（需从 task 结果获取）或跳过无延迟数据 | 5 行 |
| P0-3 | 🔴 | RouterAgent 未注入 bandit/drift | RouterAgent 单例改为 `RouterAgent(weights=..., bandit=self._get_bandit(), drift_detector=self._get_drift())` | 3 行 |
| P0-4 | 🔴 | enhance_prompt 未传 type_sig | `agent.py` L221 从 context 中提取 type_sig 传入 | 3 行 |
| P0-5 | 🔴 | GEPAPopulation 未传 conformal | `gepa.py` L120 改为 `GEPAPopulation(conformal=wiring._get_conformal())` | 3 行 |
| P1-1 | 🟡 | Conformal `_nonconformity` 忽略 task | 实现 task-based 非一致性评分（如 task-code 语义相似度） | ~20 行 |
| P1-2 | 🟡 | 假覆盖测试 | 断言改为 `assert p1 != p2`（需先修 P1-1） | 1 行 |

**核心判断**：commit 4 在 wiring.py 添加了完整的 getter 方法和 `on_task_end` 调用，但**断在了最后一公里**——RouterAgent 创建时不传参、`_last_tier` 没人写、`enhance_prompt` 不传 `type_sig`、GEPA 不传 conformal。这些是 1-3 行的修改，但缺了它们，5 个方向中 4 个仍是死代码。