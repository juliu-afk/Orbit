"""L4 静态类型检查器（Step 4.1）。

WHY L4：LLM 生成代码常犯类型错误（参数类型与返回值类型不匹配），
这些错误在运行前就能通过 mypy 静态分析发现，拦截成本低。

实现：通过 subprocess 调用 mypy --strict 检查生成的代码。
ADR 决议：使用 --strict 但忽略 no-untyped-def（允许动态函数未标注类型）。

输出解析：mypy 返回非零退出码时，从 stdout 提取错误行号和消息。
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

import structlog

from orbit.hallucination.base import skip_if_empty
from orbit.hallucination.schemas import (
    HallucinationLevel,
    L4BehaviorResult,
    ValidationResult,
)
from orbit.observability.metrics import record_hallucination_validation as _record_hallucination

logger = structlog.get_logger("orbit.hallucination.l4")

# mypy 忽略的规则（PRD Q2 决议：strict 模式但放行未标注类型的函数）
_MYPY_FLAGS = ["--strict", "--disable-error-code", "no-untyped-def"]


class L4TypeValidator:
    """L4 mypy 静态类型检查器。

    用法：
        validator = L4TypeValidator()
        result = await validator.validate(code)
        if not result.passed:
            raise TypeCheckError(result.errors)
    """

    def __init__(self, mypy_path: str = "mypy"):
        # mypy_path 保留用于向后兼容——实际执行始终用 sys.executable -m mypy
        # 确保使用当前 venv 的 mypy + 完整依赖
        self._mypy_path = mypy_path
        self._available: bool | None = None  # 缓存 mypy 可用性

    @skip_if_empty
    async def validate(
        self, code: str, predicted_behavior: str | None = None
    ) -> ValidationResult:
        """对代码片段运行 mypy 静态类型检查。

        CUA-US2: 可选 predicted_behavior——Agent 自述"此代码预期行为"。
        提供时返回 L4BehaviorResult（含 predicted/actual behavior 对比），
        不提供时返回 ValidationResult（向后兼容）。

        Args:
            code: LLM 生成的 Python 代码
            predicted_behavior: Agent 自述的预期行为描述（可选）

        Returns:
            ValidationResult 或 L4BehaviorResult
        """
        use_reflection = predicted_behavior is not None

        # 检查 mypy 是否可用（缓存结果）
        available = await self._check_available()
        if not available:
            base: ValidationResult = ValidationResult(
                passed=False,
                level=HallucinationLevel.L4_TYPE,
                errors=["mypy is not installed or not found in PATH"],
            )
            _record_hallucination(base.passed)
            if use_reflection:
                return L4BehaviorResult(
                    passed=base.passed,
                    level=base.level,
                    errors=base.errors,
                    predicted_behavior=predicted_behavior or "",
                    actual_behavior="mypy unavailable",
                    behavior_match=False,
                    behavior_diff="mypy not available—cannot verify behavior",
                )
            return base

        # 写临时文件（mypy 需文件输入，不支持 stdin）
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = Path(f.name)

        try:
            result = await self._run_mypy(tmp_path)
            _record_hallucination(result.passed)

            # ── CUA-US2: 反思式行为对比 ——
            # mypy 推断的类型错误作为"实际行为"，与 Agent 自述预期对比。
            # REVIEW-FIX P1-3: 原 behavior_match = result.passed 是空壳——
            # 现在从 predicted_behavior 提取类型声明，与 mypy 错误做关键词交叉对比。
            if use_reflection:
                actual_behavior = (
                    "type check passed" if result.passed
                    else f"type errors: {'; '.join(result.errors[:5])}"
                )
                behavior_match = self._compare_behavior(
                    predicted_behavior or "", result
                )
                behavior_diff = ""
                if not behavior_match:
                    behavior_diff = (
                        f"Predicted: {predicted_behavior}\n"
                        f"Actual: {actual_behavior}"
                    )
                return L4BehaviorResult(
                    passed=result.passed,
                    level=HallucinationLevel.L4_TYPE,
                    errors=result.errors,
                    warnings=result.warnings,
                    metadata=result.metadata,
                    predicted_behavior=predicted_behavior or "",
                    actual_behavior=actual_behavior,
                    behavior_match=behavior_match,
                    behavior_diff=behavior_diff,
                )

            return result
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception as e:
                logger.debug("temp_cleanup_failed", path=str(tmp_path), error=str(e))

    async def _run_mypy(self, file_path: Path) -> ValidationResult:
        """执行 mypy 并解析输出。

        WHY python -m mypy: shutil.which("mypy") 可能找到系统级 mypy
        （缺 pathspec 依赖），用当前 Python 解释器的 -m mypy 确保
        使用 venv 内安装的 mypy + 其完整依赖。
        """
        import sys
        cmd = [sys.executable, "-m", "mypy", *_MYPY_FLAGS, str(file_path)]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=30)
        except TimeoutError:
            logger.warning("l4_mypy_timeout")
            return ValidationResult(
                passed=False,
                level=HallucinationLevel.L4_TYPE,
                errors=["mypy execution timed out (30s)"],
            )
        except FileNotFoundError:
            self._available = False
            return ValidationResult(
                passed=False,
                level=HallucinationLevel.L4_TYPE,
                errors=[f"mypy executable not found: {self._mypy_path}"],
            )
        except Exception as e:
            logger.warning("l4_mypy_error", error=str(e))
            return ValidationResult(
                passed=False,
                level=HallucinationLevel.L4_TYPE,
                errors=[f"mypy execution failed: {e}"],
            )

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")

        if proc.returncode == 0:
            return ValidationResult(passed=True, level=HallucinationLevel.L4_TYPE)

        # 解析 mypy 输出提取错误行（过滤空行和 summary 行）
        error_lines = [
            line.strip()
            for line in stdout.splitlines()
            if line.strip() and not line.startswith("Found ") and ":" in line
        ]
        if not error_lines:
            error_lines = [stderr.strip()] if stderr.strip() else ["mypy check failed"]

        logger.info("l4_type_error_found", count=len(error_lines))
        return ValidationResult(
            passed=False,
            level=HallucinationLevel.L4_TYPE,
            errors=error_lines[:10],  # 取前 10 条，避免错误过多
            metadata={"error_count": len(error_lines)},
        )

    async def _check_available(self) -> bool:
        """检查 mypy 是否可用——实际试跑验证而非只查路径。

        WHY 实际试跑: shutil.which("mypy") 可能找到系统级 mypy
        （缺 pathspec 依赖），导致 validate() 返回 mypy crash traceback
        而非类型错误。试跑 --version 验证 mypy 确实能加载所有依赖。
        """
        import sys

        if self._available is not None:
            return self._available
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "mypy", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)
            self._available = proc.returncode == 0
        except Exception:
            self._available = False
        if not self._available:
            logger.debug("l4_mypy_not_available")
        return self._available

    @staticmethod
    def _compare_behavior(predicted: str, result: ValidationResult) -> bool:
        """对比 Agent 自述行为与 mypy 实际结果。

        REVIEW-FIX P1-3 + NEW-2: 从 mypy 错误提取 got/expected 类型，
        与 Agent 自述的返回/接受类型做精确匹配。

        WHY 不直接用关键词共现：Agent 自述"returns str" + mypy 报
        "got str, expected int" → 关键词 "str" 共现 → 旧逻辑误判矛盾。
        实际上 Agent 正确预测了实际返回类型(str)，新逻辑识别为匹配。

        算法：
        1. mypy passed → True（无矛盾）
        2. 从 mypy 错误提取 got/expected 类型
        3. 从 predicted 提取 returns/accepts 类型声明
        4. 自述类型 = mypy "got" 类型 → Agent 正确预测实际行为 → True
        5. 自述类型 = mypy "expected" 类型 → Agent 正确预测期望类型 → True
        6. 自述类型与 mypy 类型不重叠 → 矛盾 → False
        7. 无法提取 → fail-open → True
        """
        if result.passed:
            return True
        if not predicted.strip():
            return result.passed

        import re as _re

        # Step 1: 从 mypy 错误提取 got/expected 类型
        error_text = ' '.join(result.errors)
        mypy_types: set[str] = set()
        # 格式1: "got str, expected int" / "got \"str\", expected \"int\""
        for m in _re.finditer(
            r'got\s+"?\'?(\w+(?:\[[^\]]+\])?)',
            error_text, _re.IGNORECASE,
        ):
            mypy_types.add(m.group(1).lower())
        for m in _re.finditer(
            r'expected\s+"?\'?(\w+(?:\[[^\]]+\])?)',
            error_text, _re.IGNORECASE,
        ):
            mypy_types.add(m.group(1).lower())
        # 格式2: "has type \"X\"" / "incompatible type \"X\"" / "type \"X\""
        for m in _re.finditer(r'(?:has|incompatible|return)?\s*type\s+"(\w+)', error_text):
            mypy_types.add(m.group(1).lower())
        # 格式3: 直接的类型名（fallback）
        if not mypy_types:
            for m in _re.finditer(
                r'\b(int|str|float|bool|list|dict|None|tuple|set)\b',
                error_text,
            ):
                mypy_types.add(m.group(1).lower())

        if not mypy_types:
            return True  # 无法提取 mypy 类型 → fail-open

        # Step 2: 从 Agent 自述提取类型声明
        predicted_types: set[str] = set()
        for m in _re.finditer(
            r'(returns?|accepts?|takes?|expects?|outputs?)\s+'
            r'(\w+(?:\s*\|\s*\w+)*)',
            predicted, _re.IGNORECASE,
        ):
            types = _re.split(r'\s*\|\s*', m.group(2))
            predicted_types.update(t.lower() for t in types)
        # fallback: 直接匹配内置类型名
        if not predicted_types:
            for m in _re.finditer(
                r'\b(int|str|float|bool|list|dict|None|tuple|set)\b',
                predicted,
            ):
                predicted_types.add(m.group(1).lower())

        if not predicted_types:
            return True  # 无类型声明可提取 → fail-open

        # Step 3: 对比——自述类型与 mypy 提及的类型有交集 → 匹配
        overlap = predicted_types & mypy_types
        return len(overlap) > 0


# ── V14.2+Theory 方向8: TypeDirectedSynthesizer ──────────────


class TypeDirectedSynthesizer:
    """类型导向代码合成约束器.

    WHY 在生成前而非生成后:
      Wadler "Theorems for free"——多态类型签名提供免费定理。
      如 List[A] → List[A] 只能是 map id（类型约束缩小了实现空间）。
      在 Agent system prompt 中注入这些约束，在生成前消减类型错误。

    用法:
        tds = TypeDirectedSynthesizer()
        constraints = tds.constrain("def f(x: List[int]) -> List[int]:")
        # → ["多态约束: List 类型仅可被 map/filter 操作——不可索引越界",
        #     "必要导入: from typing import List"]
    """

    @staticmethod
    def constrain(type_sig: str) -> list[str]:
        """从类型签名推导生成约束."""
        constraints: list[str] = []

        # 1. 多态 free theorem
        ft = TypeDirectedSynthesizer._derive_free_theorem(type_sig)
        if ft:
            constraints.append(ft)

        # 2. 必要导入
        imports = TypeDirectedSynthesizer._required_imports(type_sig)
        constraints.extend(imports)

        # 3. 安全性约束——禁止 eval/exec
        if "eval" in type_sig.lower() or "exec" in type_sig.lower():
            constraints.append("安全约束: 禁止使用 eval()/exec()——静态类型检查无法验证动态代码")

        return constraints

    @staticmethod
    def _derive_free_theorem(type_sig: str) -> str | None:
        """从多态签名推导 Wadler 自由定理."""
        sig = type_sig.strip()
        # List[A] → List[A] → 只能是 map id 或 filter
        if "List[" in sig and "-> List[" in sig:
            return "多态约束: List 类型的输出只能来自对输入 List 的 map/filter/slice 操作——禁止越界索引"
        # Optional[T] → T → 必须处理 None
        if "Optional[" in sig and "->" in sig:
            return "多态约束: Optional 类型输入——必须先检查 None 再使用返回值"
        # Callable → 高阶函数约束
        if "Callable[" in sig:
            return "多态约束: Callable 参数——不应假设具体实现，仅能调用签名规定的参数"
        return None

    @staticmethod
    def _required_imports(type_sig: str) -> list[str]:
        """从类型签名推断必要导入."""
        imports: list[str] = []
        type_map = {
            "Decimal": "from decimal import Decimal",
            "datetime": "from datetime import datetime",
            "timedelta": "from datetime import timedelta",
            "Path": "from pathlib import Path",
            "Optional": "from typing import Optional",
            "List": "from typing import List",
            "Dict": "from typing import Dict",
            "Tuple": "from typing import Tuple",
            "Callable": "from typing import Callable",
            "Iterator": "from typing import Iterator",
        }
        for type_name, import_stmt in type_map.items():
            if type_name in type_sig and import_stmt not in imports:
                imports.append(f"必要导入: {import_stmt}")
        return imports
