# 阶段2-技术方案-Mode自调优

> 基于阶段1 PRD（验收标准共 12 条），本次技术方案覆盖 12 条，无偏离。

## 一、需求回顾

| AC# | 验收标准 | US |
|-----|---------|----|
| AC1 | TaskQualityScorer 计算三维度分 | US1 |
| AC2 | 任务 DONE 时自动调用 scorer 并写入 audit | US1 |
| AC3 | 用户反馈从 chat 自动提取 | US1 |
| AC4-6 | `/mode fast/deep/reset` + 回复确认 | US2 |
| AC7 | 自然语言检测"快点"/"别问了"/"问细点" | US2 |
| AC8 | Agent 首条 reply 带模式前缀 | US3 |
| AC9 | compose 技能也带前缀 | US3 — **P2 远期**（子 agent 输出格式复杂） |
| AC10 | mode 切换后前缀立即变化 | US3 |
| AC11 | 现有测试全绿 | 回归 |
| AC12 | 新增 ≥12 条测试 | 覆盖率 |

## 二、影响范围

### 新增文件（6 个）

| 文件 | 用途 | 预估行数 |
|------|------|---------|
| `src/orbit/modes/scorer.py` | TaskQualityScorer——三维度纯函数评分引擎 | 80 |
| `src/orbit/modes/tuner.py` | ModeTuner——mode 意图检测 + mode.yaml 写回 | 90 |
| `src/orbit/modes/indicator.py` | ModeIndicator——模式前缀标签生成 | 30 |
| `tests/unit/test_mode_scorer.py` | scorer 单元测试 ≥5 条 | 80 |
| `tests/unit/test_mode_tuner.py` | tuner 单元测试 ≥5 条 | 80 |
| `tests/unit/test_mode_indicator.py` | indicator 单元测试 ≥3 条 | 50 |

### 修改文件（4 个）

| 文件 | 改动内容 | 预估行数 |
|------|---------|---------|
| `src/orbit/modes/loader.py` | 新增 `update_mode()`——从预设写回 mode.yaml | +30 |
| `src/orbit/scheduler/task_runner.py` | DONE 状态: 调用 scorer → 写入 audit | +15 |
| `src/orbit/agents/clarifier.py` | reply 前加模式前缀；execute 前检测 mode 意图 | +20 |
| `src/orbit/compose/orchestrator.py` | compose 技能回复带前缀 | +10 |

**总计**：新增 ~410 行 Python，修改 ~75 行。

## 三、数据模型

### TaskQualityScore (scorer.py)

```python
@dataclass
class TaskQualityScore:
    task_id: str
    user_satisfaction: float     # 0-1，用户反馈维度
    session_quality: float       # 0-1，会话质量维度
    delivery_outcome: float      # 0-1，交付结果维度
    total: float                 # 加权总分
    detail: dict                 # 明细（正/负面消息数、V1-V3 状态、DONE/FAILED）
    scored_at: str               # ISO timestamp
```

### ModePreset (tuner.py)

```python
class ModePreset(StrEnum):
    FAST = "fast"     # 加速：8 问题/分支 + 广度优先
    DEEP = "deep"     # 深入：30 问题/分支 + 深度优先
    RESET = "reset"   # 恢复默认
```

## 四、API / 接口设计

### scorer——纯函数，无 IO

```python
class TaskQualityScorer:
    @staticmethod
    def score_user_satisfaction(chat_history: list[dict]) -> DimensionScore:
        """维度1: 从 chat 消息提取正面/负面信号。
        
        +0.3 / 正面关键词: "对" "好的" "确认" "可以" "OK" "yes"
        -0.5 / 负面关键词: "不对" "不是" "重来" "换个" "错了"
        -1.0 / 放弃信号: 超时 / 用户离开
        """

    @staticmethod
    def score_session_quality(clarifier_result: dict | None) -> DimensionScore:
        """维度2: 从 clarifier PRD 校验结果提取。
        
        V1+V2+V3 全部 passed → +0.4
        clarification_status="ready" → +0.3
        PRD 完整度 = (goal_len/50 + scope_len/50 + len(ac)/3) / 3 → +0.3
        clarifier_result=None → 0（非 PARSING 任务，跳过）
        """

    @staticmethod
    def score_delivery(task_state: str, review_passed: bool, has_regression: bool) -> DimensionScore:
        """维度3: 从任务终态提取。
        
        DONE → +0.4, FAILED → 0
        审查通过 → +0.3
        无回归 bug → +0.2
        无需求变更 → +0.1
        """

    @classmethod
    def score(cls, task_id, chat_history, clarifier_result, task_state, review_passed, has_regression=False):
        dim1 = cls.score_user_satisfaction(chat_history)
        dim2 = cls.score_session_quality(clarifier_result)
        dim3 = cls.score_delivery(task_state, review_passed, has_regression)
        return TaskQualityScore(
            user_satisfaction=dim1.score,
            session_quality=dim2.score,
            delivery_outcome=dim3.score,
            total=0.3*dim1.score + 0.3*dim2.score + 0.4*dim3.score,
            detail={"dim1": dim1.detail, "dim2": dim2.detail, "dim3": dim3.detail},
        )
```

### ModeTuner——mode 意图检测 + 写回

```python
class ModeTuner:
    # 自然语言触发词 → 预设映射
    INTENT_PATTERNS: dict[str, list[str]] = {
        "fast":  ["/mode fast", "快点", "别问了", "太慢了", "加快", "速战速决"],
        "deep":  ["/mode deep", "问细点", "深入", "仔细", "详细"],
        "reset": ["/mode reset", "恢复默认", "回到默认"],
    }

    @classmethod
    def detect_intent(cls, message: str) -> ModePreset | None:
        """检测消息中是否有 mode 调整意图。"""

    @classmethod
    def apply_preset(cls, loader: ModeLoader, mode_name: str, preset: ModePreset) -> ModeConfig:
        """根据预设修改 mode.yaml 并写回磁盘，返回新 config。"""
```

### ModeIndicator——前缀标签

```python
class ModeIndicator:
    @staticmethod
    def for_agent(mode_name: str | None, strategy: str) -> str:
        """Agent 模式前缀——mode=None 时显示'默认'."""
    
    @staticmethod
    def for_compose_skill(skill_name: str) -> str:
        """Compose 技能前缀."""
```

预设输出：

| 场景 | 前缀 |
|------|------|
| clarify·depth_first | `[🔍 clarify·深度模式]` |
| clarify·breadth_first | `[🔍 clarify·广角模式]` |
| clarify·fast preset | `[🔍 clarify·快速模式]` |
| clarify·默认 | `[🔍 clarify·默认]` |
| compose:plan | `[📋 compose:plan]` |
| compose:review | `[🔎 compose:review]` |

## 五、数据流

### 评分流程（任务完成时）

```
task_runner.run_task()
  → state=DONE
    → scorer.score(
        task_id,
        chat_history=context["history"],           # 维度1
        clarifier_result=context["artifacts"].get("PARSING"),  # 维度2
        task_state="DONE",                          # 维度3
        review_passed=context["artifacts"].get("VERIFYING", {}).get("passed", False),
      )
    → self._audit_logger.log("task_runner", "quality_score", ...)
```

### Mode 调优流程（聊天中）

```
clarifier.execute(input_data)
  → input_data.task (用户消息)
    → intent = ModeTuner.detect_intent(message)
      → intent is not None:
        → loader = ModeLoader()
        → new_config = ModeTuner.apply_preset(loader, "clarify", intent)
        → reply = f"已切换到{intent}模式。{new_config.behavior.question_strategy}..."
        → return AgentOutput(result={"reply": reply, ...})  ← 不走 LLM
      → intent is None:
        → 正常流程
```

### 模式指示器流程（每次回复）

```
clarifier.execute() → LLM 输出 → parsed["reply"]
  → prefix = ModeIndicator.for_agent(
        mode_name=self._mode.name if self._mode else None,
        strategy=self._question_strategy,
    )
  → parsed["reply"] = f"{prefix} {parsed['reply']}"
```

## 六、与 PRD 对照表

| AC# | 技术实现 | 文件 |
|-----|---------|------|
| AC1 | `TaskQualityScorer.score()` | `modes/scorer.py` |
| AC2 | `task_runner.py` DONE 状态调用 scorer → `_audit_logger.log()` | `scheduler/task_runner.py` |
| AC3 | `score_user_satisfaction()` 关键词匹配 chat_history | `modes/scorer.py` |
| AC4-6 | `ModeTuner.detect_intent()` + `apply_preset()` + `ModeLoader.update_mode()` | `modes/tuner.py`, `modes/loader.py` |
| AC7 | `INTENT_PATTERNS` 自然语言关键词映射 | `modes/tuner.py` |
| AC8 | `ModeIndicator.for_agent()` → reply 前缀注入 | `modes/indicator.py`, `agents/clarifier.py` |
| AC9 | `ModeIndicator.for_compose_skill()` → compose reply 前缀 | `modes/indicator.py`, `compose/orchestrator.py` |
| AC10 | mode 切换后 `_mode` 已更新 → 下次 `system_prompt()` 读新值 | `modes/tuner.py` |
| AC11 | 不改核心模块逻辑，新增参数均有默认值 | — |
| AC12 | `test_mode_scorer.py` 5 条 + `test_mode_tuner.py` 5 条 + `test_mode_indicator.py` 3 条 | `tests/unit/` |

## 七、风险

| 风险 | 缓解 |
|------|------|
| mode 意图误检测（用户说"快点做完"被当成 mode 调优） | 优先匹配 `/mode` 精确命令，自然语言仅在无命令时匹配 |
| 写回 mode.yaml 并发冲突 | `update_mode()` 是同步写小文件（<1KB），概率极低。加 try/except |
| 用户删了 mode.yaml 后 `/mode reset` 失败 | `reset` → 从内置默认值重建 mode.yaml |

---

> 12 条验收标准全覆盖，等待确认后进入阶段3。
