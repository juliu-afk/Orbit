"""防幻觉验证管道——将 L1-L8 验证器接入 Agent 执行流程。

WHY 这个文件存在:
  hallucination/ 目录下的 L1-L8 验证器全部未接入执行管道——它们作为独立模块存在，
  无任何调用方。本文件创建复合管道，在代码生成后统一运行验证器。
  每个 validator 的 validate() 接口一致 (code: str, **kwargs) → ValidationResult。

使用方式:
    pipeline = HallucinationPipeline(graph=code_graph, sandbox=sandbox)
    result = await pipeline.validate(code)
    if not result.passed:
        for err in result.errors:
            logger.warning("hallucination_detected", ...)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.graph.engines.code_graph import CodeGraphEngine
    from orbit.sandbox.executor import Sandbox

import structlog

from orbit.hallucination.l1_graph import L1GraphValidator
from orbit.hallucination.l2_dynamic import L2DynamicTracer
from orbit.hallucination.l3_entropy import L3EntropyMonitor
from orbit.hallucination.l4_type import L4TypeValidator
from orbit.hallucination.l5_z3 import L5Z3Validator
from orbit.hallucination.l6_contract import L6ContractValidator
from orbit.hallucination.l7_runtime import L7RuntimeValidator
from orbit.hallucination.l8_config import L8ConfigValidator
from orbit.hallucination.schemas import HallucinationLevel, ValidationResult

logger = structlog.get_logger("orbit.hallucination.pipeline")

# 验证器执行顺序——从快到慢，早期发现错误可提前终止
# L1 图谱(最快)→L4 类型→L3 熵→L2 动态(需沙箱)→L6 合约→L8 配置→L7 沙箱执行(最慢)→L5 Z3(最重)
_VALIDATION_ORDER: list[HallucinationLevel] = [
    HallucinationLevel.L1_GRAPH,
    HallucinationLevel.L4_TYPE,
    HallucinationLevel.L3_ENTROPY,
    HallucinationLevel.L2_DYNAMIC,
    HallucinationLevel.L6_CONTRACT,
    HallucinationLevel.L8_CONFIG,
    HallucinationLevel.L7_RUNTIME,
    HallucinationLevel.L5_Z3,
]

# 致命层级——这些层失败时 pipeline 立即停止，不继续后续验证
_FATAL_LEVELS: frozenset[HallucinationLevel] = frozenset({
    HallucinationLevel.L1_GRAPH,   # 引用不存在的符号 → 代码必然跑不起来
    HallucinationLevel.L7_RUNTIME, # 运行时失败 → 代码跑不起来
})


class HallucinationPipeline:
    """防幻觉复合验证管道——按顺序运行 L1-L8，可选提前终止。

    设计原则:
      - fail-open: 单个验证器异常不阻塞 pipeline，记录日志继续
      - 致命层提前终止: L1/L7 失败 → 不继续后续层（节省资源）
      - 每层结果独立记录

    用法:
        pipeline = HallucinationPipeline(graph=graph, sandbox=sandbox)
        result = await pipeline.validate_quick(code)      # 快速层 L1+L4+L3（同步优先）
        result = await pipeline.validate_full(code)       # 全量 L1-L8
    """

    def __init__(
        self,
        graph: CodeGraphEngine | None = None,
        sandbox: Sandbox | None = None,
    ) -> None:
        self._graph = graph
        self._sandbox = sandbox

        # 懒初始化——只在需要时创建验证器实例
        self._l1: L1GraphValidator | None = None
        self._l2: L2DynamicTracer | None = None
        self._l3: L3EntropyMonitor | None = None
        self._l4: L4TypeValidator | None = None
        self._l5: L5Z3Validator | None = None
        self._l6: L6ContractValidator | None = None
        self._l7: L7RuntimeValidator | None = None
        self._l8: L8ConfigValidator | None = None

    # ── 公共 API ──────────────────────────────────────

    async def validate_quick(self, code: str) -> ValidationResult:
        """快速验证——仅运行无外部依赖的层 (L1+L4+L3)。

        用于每次代码生成后的即时检查。不需要 sandbox/graph 的层可以同步运行。
        """
        levels = [
            HallucinationLevel.L1_GRAPH,
            HallucinationLevel.L4_TYPE,
            HallucinationLevel.L3_ENTROPY,
        ]
        return await self._run_levels(code, levels, stop_on_first_error=False)

    async def validate_full(self, code: str) -> ValidationResult:
        """全量验证——运行所有可用层 (L1-L8)。

        用于 coding 阶段完成后的完整验证。
        依赖 sandbox/graph 的层在依赖缺失时自动跳过。
        """
        return await self._run_levels(code, _VALIDATION_ORDER, stop_on_first_error=False)

    async def validate(self, code: str, max_level: HallucinationLevel | None = None) -> ValidationResult:
        """运行验证直到指定层（含）。

        max_level=None → 运行全部。
        """
        if max_level is None:
            return await self.validate_full(code)
        levels = [l for l in _VALIDATION_ORDER if l <= max_level]
        return await self._run_levels(code, levels, stop_on_first_error=False)

    # ── 内部 ──────────────────────────────────────────

    async def _run_levels(
        self,
        code: str,
        levels: list[HallucinationLevel],
        stop_on_first_error: bool,
    ) -> ValidationResult:
        """按顺序运行指定验证层级。"""
        all_errors: list[str] = []
        all_warnings: list[str] = []
        all_passed = True
        last_level: HallucinationLevel | None = None

        for level in levels:
            last_level = level
            try:
                validator = self._get_validator(level)
                if validator is None:
                    # 所需依赖缺失 → 跳过
                    all_warnings.append(f"{level.value}: 所需依赖不可用，跳过")
                    continue

                if not hasattr(validator, "validate"):
                    all_warnings.append(f"{level.value}: 非标准验证器（无 validate 方法），跳过")
                    continue
                result = await validator.validate(code)
                if not result.passed:
                    all_errors.extend(
                        f"[{level.value}] {e}" for e in result.errors
                    )
                    all_passed = False
                    if level in _FATAL_LEVELS or stop_on_first_error:
                        break
                if result.warnings:
                    all_warnings.extend(
                        f"[{level.value}] {w}" for w in result.warnings
                    )

            except Exception as e:
                # fail-open: 单个验证器崩了不阻塞 pipeline
                logger.warning(
                    "hallucination_validator_crashed",
                    level=level.value,
                    error=str(e),
                    exc_info=True,
                )
                all_warnings.append(f"[{level.value}] 验证器异常: {e}")

        return ValidationResult(
            passed=all_passed,
            level=last_level or HallucinationLevel.L1_GRAPH,
            errors=all_errors,
            warnings=all_warnings,
        )

    def _get_validator(self, level: HallucinationLevel):
        """懒初始化——按需创建验证器实例。返回 None 表示依赖缺失需跳过。"""
        # L1: 图谱验证——需要 CodeGraphEngine
        if level == HallucinationLevel.L1_GRAPH:
            if self._graph is None:
                return None
            if self._l1 is None:
                self._l1 = L1GraphValidator(graph=self._graph)
            return self._l1

        # L2: 动态追踪——需要 Sandbox
        if level == HallucinationLevel.L2_DYNAMIC:
            if self._sandbox is None:
                return None
            if self._l2 is None:
                self._l2 = L2DynamicTracer(sandbox=self._sandbox)
            return self._l2

        # L3: 熵监控——不需要外部依赖
        if level == HallucinationLevel.L3_ENTROPY:
            if self._l3 is None:
                self._l3 = L3EntropyMonitor()
            return self._l3

        # L4: 类型检查——不需要外部依赖
        if level == HallucinationLevel.L4_TYPE:
            if self._l4 is None:
                self._l4 = L4TypeValidator()
            return self._l4

        # L5: Z3 形式化——不需要外部依赖（Z3 自包含）
        if level == HallucinationLevel.L5_Z3:
            if self._l5 is None:
                self._l5 = L5Z3Validator()
            return self._l5

        # L6: 合约验证——不需要外部依赖
        if level == HallucinationLevel.L6_CONTRACT:
            if self._l6 is None:
                self._l6 = L6ContractValidator()
            return self._l6

        # L7: 沙箱运行时——需要 Sandbox
        if level == HallucinationLevel.L7_RUNTIME:
            if self._sandbox is None:
                return None
            if self._l7 is None:
                self._l7 = L7RuntimeValidator(sandbox=self._sandbox)
            return self._l7

        # L8: 配置漂移——不需要外部依赖
        if level == HallucinationLevel.L8_CONFIG:
            if self._l8 is None:
                self._l8 = L8ConfigValidator()
            return self._l8

        return None
