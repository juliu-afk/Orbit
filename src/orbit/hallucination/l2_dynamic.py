"""L2 动态调用追踪器（Step 4.1）。

WHY L2：LLM 生成代码可能使用 getattr()、动态字符串拼接等技巧调用函数，
这些无法被 L1 静态分析捕获。L2 在沙箱执行时注入 sys.settrace 追踪所有
函数调用，然后对照代码图谱验证被调用函数是否存在。

实现：将用户代码包装在 sys.settrace 追踪逻辑中，在 Sandbox 内执行。
追踪器收集所有 function call 事件的目标函数名，再通过 CodeGraphEngine
逐个验证是否在代码图谱中存在。不在图谱中的调用 → passed=False。

限制（PRD）：仅在 Test/Prod 启用（性能开销 ~200ms）。
"""

from __future__ import annotations

import structlog

from orbit.graph.engines.code_graph import CodeGraphEngine
from orbit.hallucination.base import skip_if_empty
from orbit.hallucination.schemas import HallucinationLevel, L2ReflectionResult, ValidationResult
from orbit.sandbox.executor import Sandbox

logger = structlog.get_logger("orbit.hallucination.l2")

# 注入 sys.settrace 的包装模板
# WHY 在代码中内联 settrace：沙箱是 Docker 进程，无法从外部注入 Python hook，
# 必须把追踪代码嵌入到用户代码一起发给容器执行。
_TRACE_WRAPPER = '''
import sys
import json

_traced_calls = []

def _l2_trace(frame, event, arg):
    """L2 追踪回调：收集所有 function call 事件的目标函数名。
    WHY 仅追踪 call 事件：return/exception 事件不提供新信息，且增加 ~3x 开销。
    """
    if event == "call":
        _traced_calls.append(frame.f_code.co_name)
    return _l2_trace

sys.settrace(_l2_trace)

# === 用户代码开始 ===
{user_code}
# === 用户代码结束 ===

sys.settrace(None)
print("__L2_TRACE_RESULT__" + json.dumps(_traced_calls))
'''

# 追踪结果标记（用于从 stdout 中提取）
_RESULT_MARKER = "__L2_TRACE_RESULT__"

# 沙箱内部函数（L2 自身注入的追踪器函数，不验证）
_TRACE_INTERNAL = frozenset({"_l2_trace"})


class L2DynamicTracer:
    """L2 动态调用追踪器。

    用法：
        tracer = L2DynamicTracer(sandbox, code_engine)
        result = await tracer.validate(code)
        if not result.passed:
            # result.metadata["untracked_calls"] 含未在图谱中找到的调用
            raise DynamicCallError(result.metadata["untracked_calls"])
    """

    def __init__(self, sandbox: Sandbox, code_engine: CodeGraphEngine):
        self._sandbox = sandbox
        self._engine = code_engine

    @skip_if_empty
    async def validate(
        self, code: str, predicted_calls: list[str] | None = None
    ) -> ValidationResult:
        """在沙箱中执行带追踪包装的代码，验证所有函数调用是否在代码图谱中。

        CUA-US2: 可选 predicted_calls——Agent 自述"将调用哪些函数"。
        提供时返回 L2ReflectionResult（含 predicted/actual/deviation 对比），
        不提供时返回 ValidationResult（向后兼容）。

        Args:
            code: LLM 生成的 Python 代码
            predicted_calls: Agent 自述将调用的函数列表（可选）

        Returns:
            ValidationResult 或 L2ReflectionResult
        """
        use_reflection = predicted_calls is not None

        # 检查沙箱可用性
        if not await self._sandbox.is_available():
            base = ValidationResult(
                passed=True,
                level=HallucinationLevel.L2_DYNAMIC,
                warnings=["sandbox unavailable, L2 skipped"],
            )
            if use_reflection:
                return L2ReflectionResult(
                    passed=base.passed,
                    level=base.level,
                    warnings=base.warnings,
                    predicted_calls=predicted_calls or [],
                    actual_calls=[],
                    deviation_score=1.0,
                )
            return base

        # 注入追踪包装
        wrapped_code = _TRACE_WRAPPER.format(user_code=code)

        try:
            stdout = await self._sandbox.run(wrapped_code, language="python")
        except Exception as e:
            logger.info("l2_sandbox_execution_failed", error=str(e))
            base = ValidationResult(
                passed=True,
                level=HallucinationLevel.L2_DYNAMIC,
                warnings=[f"Sandbox execution failed (L2 cannot verify): {e}"],
                metadata={"execution_error": str(e)},
            )
            if use_reflection:
                return L2ReflectionResult(
                    passed=base.passed,
                    level=base.level,
                    warnings=base.warnings,
                    predicted_calls=predicted_calls or [],
                    actual_calls=[],
                    deviation_score=1.0,
                )
            return base

        # 提取追踪结果
        traced = self._parse_trace_result(stdout)
        # 过滤 L2 自身注入的函数
        user_calls = [c for c in traced if c not in _TRACE_INTERNAL]

        # WHY 对照图谱验证：收集到的函数调用必须全部在代码图谱中存在，
        # 否则说明 LLM 生成了不存在的动态调用（L2 的核心职责）
        untracked: list[str] = []
        for call in user_calls:
            try:
                if not await self._engine.exists(call):
                    untracked.append(call)
            except Exception as e:
                logger.warning("l2_graph_query_failed", call=call, error=str(e))

        # ── CUA-US2: 反思式对比 ——
        # 计算预测 vs 实际的偏差分。不改变 passed 判定，仅作为附加信号。
        if use_reflection:
            pred_set = set(predicted_calls or [])
            actual_set = set(user_calls)
            unpredicted = sorted(pred_set - actual_set)  # 预测了但没调用
            unexpected = sorted(actual_set - pred_set)   # 调用了但没预测
            # 偏差分：意外调用占比
            total = max(len(pred_set), 1)
            deviation = min(len(unexpected) / total, 1.0)

            result = L2ReflectionResult(
                passed=len(untracked) == 0,
                level=HallucinationLevel.L2_DYNAMIC,
                errors=[f"Dynamic calls not found in code graph: {', '.join(untracked)}"] if untracked else [],
                metadata={
                    "untracked_calls": untracked,
                    "traced_calls": user_calls,
                    "call_count": len(user_calls),
                },
                predicted_calls=predicted_calls or [],
                actual_calls=user_calls,
                deviation_score=deviation,
                unpredicted_calls=unpredicted,
                unexpected_calls=unexpected,
            )
            if untracked:
                logger.info("l2_untracked_calls", calls=untracked, deviation=deviation)
            else:
                logger.info("l2_trace_complete", call_count=len(user_calls), deviation=deviation)
            return result

        # 原有逻辑——无反思式对比
        if untracked:
            logger.info("l2_untracked_calls", calls=untracked)
            return ValidationResult(
                passed=False,
                level=HallucinationLevel.L2_DYNAMIC,
                errors=[f"Dynamic calls not found in code graph: {', '.join(untracked)}"],
                metadata={
                    "untracked_calls": untracked,
                    "traced_calls": user_calls,
                    "call_count": len(user_calls),
                },
            )

        logger.info("l2_trace_complete", call_count=len(user_calls))
        return ValidationResult(
            passed=True,
            level=HallucinationLevel.L2_DYNAMIC,
            metadata={"traced_calls": user_calls, "call_count": len(user_calls)},
        )

    def _parse_trace_result(self, stdout: str) -> list[str]:
        """从 stdout 中提取 L2 追踪结果。

        WHY 用标记字符串而非单独输出：沙箱 run() 只返回 stdout，
        追踪结果和代码输出混在一起，需标记分隔。
        """
        import json

        for line in stdout.splitlines():
            if line.startswith(_RESULT_MARKER):
                try:
                    result: list[str] = json.loads(line[len(_RESULT_MARKER) :])
                    return result
                except json.JSONDecodeError:
                    logger.warning("l2_trace_result_parse_failed")
                    return []
        return []
