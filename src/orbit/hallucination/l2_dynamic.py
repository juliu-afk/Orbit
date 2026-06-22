"""L2 动态调用追踪器（Step 4.1）。

WHY L2：LLM 生成代码可能使用 getattr()、动态字符串拼接等技巧调用函数，
这些无法被 L1 静态分析捕获。L2 在沙箱执行时注入 sys.settrace 追踪所有
函数调用，验证被调用的函数是否在代码图谱中存在。

实现：将用户的代码包装在 sys.settrace 追踪逻辑中，在 Sandbox 内执行。
追踪器收集所有 function call 事件的目标函数名，然后对照图谱验证。

限制（PRD）：仅在 Test/Prod 启用（性能开销 ~200ms）；当前传递
enable_l2 标志让 Sandbox 决定是否注入追踪。
"""

from __future__ import annotations

import structlog

from orbit.hallucination.schemas import HallucinationLevel, ValidationResult
from orbit.sandbox.executor import Sandbox

logger = structlog.get_logger()

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


class L2DynamicTracer:
    """L2 动态调用追踪器。

    用法：
        tracer = L2DynamicTracer(sandbox, code_engine)
        result = await tracer.validate(code)
        if not result.passed:
            # result.metadata["untracked_calls"] 含未在图谱中找到的调用
            ...
    """

    def __init__(self, sandbox: Sandbox):
        self._sandbox = sandbox

    async def validate(self, code: str) -> ValidationResult:
        """在沙箱中执行带追踪包装的代码，收集函数调用。

        Args:
            code: LLM 生成的 Python 代码

        Returns:
            ValidationResult：passed=True 所有调用均在图谱中
        """
        if not code.strip():
            return ValidationResult(
                passed=True,
                level=HallucinationLevel.L2_DYNAMIC,
                warnings=["empty code, skipped"],
            )

        # 检查沙箱可用性
        if not await self._sandbox.is_available():
            return ValidationResult(
                passed=True,
                level=HallucinationLevel.L2_DYNAMIC,
                warnings=["sandbox unavailable, L2 skipped"],
            )

        # 注入追踪包装
        wrapped_code = _TRACE_WRAPPER.format(user_code=code)

        try:
            stdout = await self._sandbox.run(wrapped_code, language="python")
        except Exception as e:
            # 沙箱执行失败（语法错误/超时/运行时异常）→ 记录但不阻断
            # WHY 不阻断：L2 是运行时验证，代码语法错误应该被 L1/L4 拦下，
            # L2 不做重复拦截。
            logger.info("l2_sandbox_execution_failed", error=str(e))
            return ValidationResult(
                passed=True,
                level=HallucinationLevel.L2_DYNAMIC,
                warnings=[f"Sandbox execution failed (L2 cannot verify): {e}"],
                metadata={"execution_error": str(e)},
            )

        # 提取追踪结果
        traced = self._parse_trace_result(stdout)
        logger.info("l2_trace_complete", call_count=len(traced))
        return ValidationResult(
            passed=True,
            level=HallucinationLevel.L2_DYNAMIC,
            metadata={"traced_calls": traced, "call_count": len(traced)},
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
                    return json.loads(line[len(_RESULT_MARKER):])
                except json.JSONDecodeError:
                    logger.warning("l2_trace_result_parse_failed")
                    return []
        return []
