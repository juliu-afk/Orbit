# PR #229 R2 复审 — feat(wiring): 五大能力模块全链路集成接线

**PR**: [#229](https://github.com/juliu-afk/Orbit/pull/229)
**Commit**: `f0859425` (已 merged)
**复审时间**: 2026-07-07
**R1 结论**: 0 P0 / 0 P1 / 0 P2 — 建议合并

---

## R2 发现汇总

| # | 级别 | 问题 | 影响 |
|---|------|------|------|
| P0-1 | 🔴 阻塞 | Monitor `feed_monitor` 推送 dict，但 `_process_event` 用 `getattr(event, "type")` 访问 | Monitor 永远收不到事件，整个监控+HITL 链路死代码 |
| P0-2 | 🔴 阻塞 | 轨迹 ID 生成/结束不匹配——`start_trajectory` 用 `sha256(task_id:timestamp)`，`on_task_end` 用 `sha256(task_id:)` | `finish_trajectory` UPDATE 命中 0 行，轨迹永不完成，蒸馏管线全链路空转 |
| P0-3 | 🔴 阻塞 | `context["user_profile"]` 写入后全代码库零消费 | Profile 加载接线但未通电——load_profile 结果被丢弃 |
| P1-1 | 🟡 修后合 | Monitor Task 引用未持有 + 队列永不清理 + 无结束信号 | 每个任务泄漏 1 个 Monitor asyncio.Task + 1 个 Queue，长跑 OOM |
| P1-2 | 🟡 修后合 | VIGIL `heal` 返回 `new_action`/`new_args` 被 agent.py 忽略 | 自愈仅注入文字建议，实际工具调用参数不变，同类错误循环 |
| P1-3 | 🟡 修后合 | PreAct 删除高风险工具后，`alternative` 仅 log 不注入 | LLM 选定的 Action 被静默删除，Agent 无反馈、无替代执行 |
| P2-1 | 🔵 建议 | `vigil.py` L52-53 双重 `@dataclass` 装饰器 | 代码异味，无害但应清理 |
| P2-2 | 🔵 建议 | `main.py` L436 `_wiring._get_trajectory()` 跨模块访问私有方法 | 封装破坏，应提供公开 `get_trajectory()` |
| P2-3 | 🔵 建议 | PreAct `use_llm=(turn>0)` 每工具每轮调 LLM | ~100% LLM 调用开销，rule_predictor 先行可缓解但需监控 |

---

## P0-1 — Monitor 事件类型不匹配（全链路静默失效）

**文件**: `src/orbit/integration/wiring.py` L116-125 ↔ `src/orbit/metacognition/monitor.py` L154-170

`feed_monitor` 向队列推送 **dict**：
```python
# agent.py L438
get_wiring().feed_monitor(task_id, {
    "type": "tool_result",
    "data": {"tool": tool_name, "result_size": len(result_str)},
})
```

但 MonitorAgent `_process_event` 使用 **属性访问**：
```python
# monitor.py L155-156
def _process_event(self, event) -> list[Alert]:
    event_type = getattr(event, "type", None)  # ← dict 无 .type 属性
    if event_type is None:
        return []                               # ← 永远走这里
```

**验证**：
```python
>>> d = {"type": "tool_result", "data": {}}
>>> getattr(d, "type", None)
None   # ← dict 用 getattr 返回 None
>>> d.get("type")
'tool_result'
```

**影响**：Monitor Agent 启动成功、HITLManager 接线成功，但 **零事件被处理**。AC3（Monitor 收 TOOL_RESULT + 产生告警）未真正满足。所有 CRITICAL 告警 → HITL 通知前端的链路从未触发。

**修复**：`feed_monitor` 应推送 `StreamEvent` 对象，或 `_process_event` 同时支持 dict：
```python
def _process_event(self, event) -> list[Alert]:
    event_type = getattr(event, "type", None)
    if event_type is None and isinstance(event, dict):
        event_type = event.get("type")  # 支持 dict
    ...
```

---

## P0-2 — 轨迹 ID 不匹配（蒸馏管线全链路空转）

**文件**: `src/orbit/integration/wiring.py` L93-103 ↔ `src/orbit/observability/trajectory.py` L225-228

`on_task_start` → `start_trajectory` 内部生成 ID：
```python
# trajectory.py L225
def _make_traj_id(task_id: str) -> str:
    return hashlib.sha256(f"{task_id}:{time.time()}".encode()).hexdigest()[:16]
```

`on_task_end` → `finish_trajectory` 独立计算 ID：
```python
# wiring.py L99-100
tid = hashlib.sha256(f"{task_id}:".encode()).hexdigest()[:16]
tc.finish_trajectory(tid, ...)
```

`f"{task_id}:"` ≠ `f"{task_id}:{time.time()}"` — **两个 ID 永远不等**。

`finish_trajectory` 执行 `UPDATE trajectories SET ... WHERE trajectory_id=?`，命中的行数 **永远为 0**。轨迹状态停在 `started`，`final_outcome` 永不为 `completed`，`quality_score` 永不为正数。

**连锁影响**：
```
on_task_end 失败 → get_completed() 返回空 → maybe_distill() 的 len(completed) < 3 → 蒸馏永不触发
                                                          ↓
                                              ANCHOR 检查、规则蒸馏、LLM 蒸馏全部空转
```

**验证**：
```python
import hashlib, time
task_id = "task_001"
start_id = hashlib.sha256(f"{task_id}:{time.time()}".encode()).hexdigest()[:16]
end_id   = hashlib.sha256(f"{task_id}:".encode()).hexdigest()[:16]
print(start_id == end_id)  # False — 永远
```

**修复**：`on_task_end` 应使用 `_make_traj_id` 或 `start_trajectory` 返回的 trajectory_id。

---

## P0-3 — user_profile 接线但全代码库零消费

**文件**: `src/orbit/scheduler/task_runner/runner.py` L148-150

```python
profile = w.load_profile(project_id)
if profile:
    context["user_profile"] = profile  # ← 写入 context
```

全代码库搜索 `context.*user_profile`、`context.get("user_profile")`、`context["user_profile"]` — **唯一命中就是 runner.py 的写入处**。

PromptBuilder（`src/orbit/prompt/builder.py`）不读取 `user_profile`，ReActAgent 不读取它，ContextBuilder 不消费它。

**影响**：AC7（ProfileStore 加载至 context）在字面上满足（确实写进了 context dict），但实质上 **Profile 数据完全未影响任何输出**。这是 #201（7 个 Builder 死代码）和 #230（MCTSPlanner 假接线）之后的又一例"接线但未通电"。

---

## P1-1 — Monitor Task 引用泄漏 + 队列无清理

**文件**: `src/orbit/scheduler/task_runner/runner.py` L155-158, `src/orbit/integration/wiring.py`

```python
# runner.py L155
asyncio.create_task(
    w.start_monitor(task_id, goal=prd[:200])
)
# ← 返回的 Task 未存储
```

三个问题叠加：
1. **Monitor Task 引用丢失** — `asyncio.create_task()` 的返回值未存储，GC 可能回收 Monitor 协程
2. **队列永不清理** — `_monitor_queues[task_id]` 在 `on_task_end` 中未删除，dict 无限增长
3. **无结束信号** — MonitorAgent `run()` 循环等待 `event is None` 作为结束信号，但 **无人发送 None**。Monitor Task 永久挂在 `await event_queue.get()`

**影响**：跑 100 个任务后，有 100 个 Monitor Task 悬挂在事件循环中 + 100 个 Queue 在 dict 中。长跑场景内存持续增长。

**修复**：`on_task_end` 应：
```python
q = self._monitor_queues.pop(task_id, None)
if q:
    q.put_nowait(None)  # 发送结束信号
```

---

## P1-2 — VIGIL heal 返回值部分丢弃

**文件**: `src/orbit/agents/react_agent/agent.py` L410-411

```python
heal = self._vigil_healer.heal(diagnosis, tool_name, tool_args)
messages.append({"role": "user", "content": f"[VIGIL 自愈建议] {heal.message}"})
```

`HealResult` 定义了 `new_action`、`new_args`、`success` 字段，但 agent.py 仅使用 `heal.message`。VIGIL 的实际修复策略（如"用 read_file 代替 exec_command"）只以文字形式告诉 LLM，**工具调用参数在下一轮不变**。

**影响**：VIGIL 名为"自愈"，实质只是一个文字建议注入器。真正的"参数修正"逻辑（`HealResult.new_action`/`new_args`）从未被消费。

---

## P1-3 — PreAct 跳过后替代方案丢失

**文件**: `src/orbit/agents/react_agent/agent.py` L351-352

```python
if pred.should_skip() and pred.alternative:
    logger.info("preact_skip", task_id=task_id, tool=tn, alt=pred.alternative[:80])
    tool_calls.remove(tc)  # ← 删除了，但 alternative 只 log
```

PreAct 判断某 Action 高风险 → 删除它 → 记录日志。但 `pred.alternative`（替代方案建议）**既不注入 messages 也不替换 tool_call**。

Agent 在下一轮 LLM 调用前，对 PreAct 删除了什么、建议了什么替代方案**毫无感知**。

---

## P2-1 — 双重 @dataclass 装饰器

**文件**: `src/orbit/metacognition/vigil.py` L52-53

```python
@dataclass
@dataclass
class HealResult:
```

Python 3.12+ 双重 `@dataclass` 不崩溃但属于明显代码错误。

---

## P2-2 — 跨模块访问私有方法

**文件**: `src/orbit/api/main.py` L436

```python
app.state.trajectory_collector = _wiring._get_trajectory()  # ← _前缀方法
```

应提供公开接口 `get_trajectory()`。

---

## ✅ 验证通过的部分

| 项 | 验证 |
|----|------|
| `configure_wiring()` 单例 | ✅ `get_wiring()` 返回同一实例 |
| factory.py → ReActAgent 参数传递 | ✅ preact_engine/vigil_healer 完整透传 |
| PreActEngine `predict()` 调用 | ✅ 确实在 execute_stream L346 被调用 |
| VigilSelfHealer `diagnose()` → `heal()` | ✅ 确实在 execute_stream L408 被调用 |
| ReflectionEngine `reflect()` | ✅ 每轮 turn 后执行，drift detection 工作 |
| HITLManager 接线 | ✅ wiring → Monitor → `_trigger_hitl` 链路存在 |
| ANCHOR `check_before_distill` | ✅ 在 `maybe_distill` 中调用 |
| checkpoint.py 双实例清理 | ✅ `_wire()`/`_get_wiring()` 已删除 |
| VigilSelfHealer diagnose/heal 运行时验证 | ✅ FileNotFoundError 正确诊断+修复 |

---

## R1 对比

R1 报告判定 AC1-AC9 "全覆盖"且 0 P0/P1/P2。R2 发现：
- **AC3**（Monitor 产出告警）：❌ feed_monitor 类型不匹配，事件全部丢弃
- **AC4**（情节记忆写入）：⚠️ 写入正常但轨迹完成（on_task_end）失败
- **AC6**（ANCHOR pre-distill）：⚠️ 接线正确但因轨迹 ID 不匹配导致 `maybe_distill` 内 `get_completed()` 返回空
- **AC7**（Profile 加载至 context）：❌ 写入 context 但全代码库零消费

R1 检查了"是否调用了"但未深入检查"调用是否真正生效"。这正是本项目反复出现的"接线但未通电"模式。

---

## 总体结论

❌ **3 个 P0 + 3 个 P1 需修复**

本 PR 的"五大能力全链路集成"在结构上完整——工厂模式、参数透传、fail-open 包装、单例管理都正确。但三个核心链路存在类型/ID 不匹配导致**静默失效**：

1. **Monitor** 事件类型 dict vs StreamEvent 不匹配 → 监控+HITL 全死
2. **轨迹** ID 时间戳不匹配 → 蒸馏全链路空转
3. **Profile** 写入但无人读取 → 接线未通电

这三个问题都有 try/except: pass 包裹，不会崩溃，但功能完全空转。R1 的 AC 核对只验证了"是否调用了方法"，未验证"方法调用是否产生了预期效果"。

**建议**：针对每个 P0 补一个端到端集成测试（推送事件→验证 Monitor 产出告警；start→end→验证轨迹 completed；load_profile→验证 prompt 中出现 profile 内容），杜绝此类"接线但未通电"的回归。
