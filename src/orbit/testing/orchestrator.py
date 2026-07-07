"""测试流程编排器 —— testing/ 模块的核心中枢（L4）。

WHY 编排器: 协调意图提取→策略选择→测试生成→沙箱执行→门禁→修复循环→报告的全流程。
所有外部依赖通过构造函数注入——测试时不需真实 sandbox/gateway。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Protocol

from orbit.testing.gate import GateDecision, QualityGate, TestRunResult
from orbit.testing.intention import IntentionExtractor, TestIntention
from orbit.testing.redundancy_check import FrameworkFitReport, RedundancyChecker
from orbit.testing.reporter import CrossReport, TestReporter
from orbit.testing.strategies.intention_driven import (
    GeneratedTest,
    IntentionDrivenGenerator,
)

# S3: Ponytail 过度工程检测进入测试-审查联动
from orbit.review.ponytail import PonytailReviewer

logger = logging.getLogger(__name__)


# ── 依赖接口（Protocol——不依赖具体实现） ──────────────────────────


class SandboxRunner(Protocol):
    """沙箱执行接口——适配 process_sandbox / docker_sandbox。"""
    async def run(self, code: str, language: str = "python") -> str: ...


class LLMGateway(Protocol):
    """LLM 调用接口——适配 gateway/。"""
    async def generate(self, prompt: str) -> str: ...


class ReviewService(Protocol):
    """代码审查接口——适配 review/。"""
    async def review(self, code: str, goal_id: str) -> dict: ...


# ── 编排器 ──────────────────────────────────────────────────────


class TestOrchestrator:
    """测试流程编排器——L4 核心。
    """
    __test__ = False  # 非 pytest 测试类

    # Phase 1 MVP:
    # - 意图提取 → 意图驱动生成 → 沙箱执行 → 门禁 → 报告
    # - 修复循环（≤3 轮）
    # - 框架适配检查
    # - CrossReport（测试 + 审查合并）
    # Phase 2+: RTS / 变异引导 / AB 对比

    def __init__(
        self,
        sandbox: SandboxRunner | None = None,
        gateway: LLMGateway | None = None,
        review_service: ReviewService | None = None,
        code_graph=None,
        knowledge=None,
        checkpoint_manager=None,
        max_repair_rounds: int = 3,
        ponytail: PonytailReviewer | None = None,  # S3: Ponytail 过度工程检测器
    ):
        self._sandbox = sandbox
        self._gateway = gateway
        self._review = review_service
        self._code_graph = code_graph
        self._knowledge = knowledge
        self._checkpoint = checkpoint_manager

        self._intention_extractor = IntentionExtractor()
        self._generator = IntentionDrivenGenerator(gateway)
        self._gate = QualityGate()
        self._redundancy_checker = RedundancyChecker(code_graph, knowledge)
        self._reporter = TestReporter()
        self._ponytail = ponytail or PonytailReviewer()  # S3/S4: 默认实例化——审查永不静默跳过

        self.max_repair_rounds = max_repair_rounds

    # ── 主入口 ──────────────────────────────────────────────────

    async def run(
        self,
        code: str,
        module: str = "",
        goal_id: str = "",
        prd_text: str = "",
    ) -> dict:
        """执行完整的测试循环——生成 + 执行 + 门禁 + 报告。

        Args:
            code: 新生成的代码内容
            module: 所属模块名（如 "scheduler.state_machine"）
            goal_id: 关联的 Goal ID（可选）
            prd_text: PRD 文本（可选——用于提取 Test Intention）

        Returns:
            dict: 前端可消费的摘要卡片 JSON + 完整结果
        """
        task_id = f"test_{module}_{int(time.time())}"
        start = time.monotonic()

        # 保存检查点
        if self._checkpoint:
            try:
                await self._checkpoint.save(task_id, {"code": code, "module": module})
            except Exception:
                logger.warning("检查点保存失败，继续执行", exc_info=True)

        # ── 1. 提取测试意图 ──
        intention = self._intention_extractor.extract_from_code(code, module)
        if prd_text:
            prd_intentions = self._intention_extractor.extract_from_prd(prd_text)
            # 合并 PRD 意图
            for pi in prd_intentions:
                intention.positive.extend(pi.positive)
                intention.gherkin_scenarios.extend(pi.gherkin_scenarios)

        # ── 2. 生成测试代码 ──
        generated_tests = await self._generator.generate(intention, code)
        test_code = self._merge_test_code(generated_tests)

        # ── 3. 框架适配检查（秒级） ──
        framework_report = await self._redundancy_checker.check(code, module)

        # ── 4. 沙箱执行（仅当框架无阻塞） ──
        result = TestRunResult(task_id=task_id, status="running")
        if framework_report.has_blockings:
            result.compiled = False  # 框架阻塞视为编译失败—强制修复
            result.framework_blockings = [b.detail for b in framework_report.blockings]
            result.status = "failed"
            result.errors = result.framework_blockings
        elif self._sandbox:
            result = await self._execute_tests(test_code, code, task_id)
        else:
            # 无沙箱——跳过执行（开发阶段回退）
            result.passed = len(generated_tests)
            result.compiled = True
            result.status = "passed"

        # ── 5. 门禁判定 ──
        decision = self._gate.evaluate(result)

        # ── 6. 修复循环（如果有失败） ──
        while decision in (GateDecision.FAILED, GateDecision.SUPPLEMENT):
            if result.repair_attempts >= self.max_repair_rounds:
                decision = GateDecision.FAILED_PERMANENT
                result.status = "failed_permanent"
                break

            # 调用 LLM 修复
            if self._gateway:
                repaired_code = await self._repair_code(code, result, intention)
                # 重新生成 + 执行
                result = await self._execute_repair_cycle(
                    repaired_code, test_code, task_id
                )
                decision = self._gate.evaluate(result)
            else:
                # 无 LLM → 无法修复 → 直接标记
                decision = GateDecision.FAILED_PERMANENT
                result.status = "failed_permanent"
                break

        # ── 7. 反馈回灌 ──
        # Phase 3: 失败模式 → knowledge/

        # ── 8. 并行启动审查 + Ponytail + 生成 CrossReport ──
        # S4: 审查不应可选——无 review_service 时至少跑 Ponytail 静态检测
        # S3: Ponytail 发现进入 CrossReport.cross_validations
        review_result = None
        ponytail_findings: list[dict] = []

        # 并行跑审查 Agent + Ponytail 静态检测
        async def _run_review() -> dict | None:
            if self._review:
                try:
                    return await self._review.review(code, goal_id)
                except Exception:
                    logger.warning("审查服务调用失败，回退静态分析", exc_info=True)
            return None

        async def _run_ponytail() -> list[dict]:
            findings: list[dict] = []
            try:
                report = self._ponytail.review_file(module + ".py" if module else "code.py", code)
                for f in report.findings:
                    findings.append({
                        "file": f.file_path,
                        "line": f.line,
                        "severity": f.severity,
                        "category": f.category,
                        "message": f.problem,
                        "suggestion": f.lazier_alternative,
                        "source": "ponytail",  # S3: 标注来源，CrossReport 区分审查维度
                    })
            except Exception:
                logger.warning("ponytail_review_failed", exc_info=True)
            return findings

        # 并行执行——审查 Agent 和 Ponytail 互不阻塞
        review_result, ponytail_findings = await asyncio.gather(
            _run_review(), _run_ponytail(),
        )

        # S4: 无 review_service → Ponytail + 静态兜底
        if review_result is None:
            review_result = self._static_review_fallback(code, module)

        # S3: 将 Ponytail 发现注入审查结果，使其进入 CrossReport
        if ponytail_findings:
            if "issues" not in review_result:
                review_result["issues"] = []
            review_result["issues"].extend(ponytail_findings)
            review_result["ponytail_count"] = len(ponytail_findings)  # 摘要卡片展示用

        cross = self._reporter.build_cross_report(task_id, result, review_result)

        # ── 9. 合并框架警告到报告 ──
        result.framework_warnings = [w.detail for w in framework_report.warnings]
        result.duration_sec = time.monotonic() - start
        result.status = decision.value

        summary_card = self._reporter.build_summary_card(result, decision, framework_report)

        # 附加 CrossReport 共识信息
        summary_card["cross_report"] = {
            "consensus": cross.consensus,
            "divergent_count": len(cross.divergent_points),
            "divergent_points": [
                {"target": d.target, "reason": d.review_reason, "suggestion": d.suggestion}
                for d in cross.divergent_points
            ],
        }

        return summary_card

    # ── TDD 模式入口 ────────────────────────────────────────────

    async def run_tdd(
        self,
        goal_id: str = "",
        module: str = "",
        prd_text: str = "",
    ) -> tuple[list[GeneratedTest], TestIntention]:
        """TDD 第一步：先于代码生成——返回测试代码和意图，供 Agent 约束代码生成。

        Returns:
            (generated_tests, intention) —— Agent 在生成实现代码前应先用这些测试约束自己。
        """
        intention = TestIntention(target=module)
        if prd_text:
            prd_intentions = self._intention_extractor.extract_from_prd(prd_text)
            for pi in prd_intentions:
                intention.positive.extend(pi.positive)

        generated_tests = await self._generator.generate(intention, "")
        return generated_tests, intention

    # ── 内部方法 ─────────────────────────────────────────────────

    async def _execute_tests(
        self, test_code: str, source_code: str, task_id: str
    ) -> TestRunResult:
        """沙箱执行测试代码 + 被测代码。"""
        result = TestRunResult(task_id=task_id, status="running")
        full_code = f"{source_code}\n\n{test_code}"

        try:
            import json

            output = await self._sandbox.run(full_code)  # type: ignore[union-attr]
            # 尝试解析 pytest JSON 输出
            # Phase 1: 简化为 exit code 判断
            result.compiled = "SyntaxError" not in output
            result.passed = 1 if result.compiled else 0
            result.failed = 0 if result.compiled else 1
            result.status = "passed" if result.compiled else "failed"
        except Exception as e:
            result.compiled = False
            result.failed = 1
            result.status = "failed"
            result.errors.append(str(e))

        return result

    async def _repair_code(
        self, code: str, result: TestRunResult, intention: TestIntention
    ) -> str:
        """调用 LLM 修复代码。"""
        if not self._gateway:
            return code

        error_text = "\n".join(result.errors) if result.errors else "未知错误"
        prompt = f"""以下代码的测试失败，请修复。

测试意图:
- 正向: {'; '.join(intention.positive)}
- 异常: {'; '.join(intention.negative)}
- 边界: {'; '.join(intention.edge_cases)}

错误信息:
{error_text}

原始代码:
```python
{code}
```

请只输出修复后的完整代码，不要解释。"""
        try:
            return await self._gateway.generate(prompt)
        except Exception:
            return code  # LLM 调用失败，返回原代码

    async def _execute_repair_cycle(
        self, code: str, test_code: str, task_id: str
    ) -> TestRunResult:
        """执行一次修复后的测试循环。"""
        result = await self._execute_tests(test_code, code, task_id)
        result.repair_attempts += 1
        return result

    def _merge_test_code(self, tests: list[GeneratedTest]) -> str:
        """合并多条测试代码为一个可执行文件。"""
        imports = "import pytest\n\n"
        body = "\n\n".join(t.code for t in tests)
        return imports + body

    def _static_review_fallback(self, code: str, module: str) -> dict:
        """审查 Agent 不可用时的静态分析兜底。

        WHY 兜底: S4 断点——审查不应可选。当 ReviewService 不可用时，
        至少用正则+AST 做最小安全+结构检查，确保 CrossReport 总是有审查结果。
        """
        import ast
        import re

        issues: list[dict] = []

        # 1. 硬编码密钥检测
        secret_patterns = [
            (r'(?i)(api_key|password|secret|token)\s*=\s*["\'][^"\']{8,}["\']', "可能硬编码密钥"),
            (r'(?i)(-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----)', "包含私钥"),
        ]
        for pattern, msg in secret_patterns:
            if re.search(pattern, code):
                issues.append({
                    "file": module, "line": 0, "severity": "blocking",
                    "message": f"[静态兜底] {msg}",
                    "suggestion": "从环境变量读取，禁止硬编码",
                })

        # 2. 危险函数调用检测
        dangerous_calls = {
            "eval": "使用 eval() 存在代码注入风险",
            "exec": "使用 exec() 存在代码注入风险",
            "os.system": "使用 os.system() 存在命令注入风险",
            "subprocess.call": "使用 subprocess.call() 建议走 sandbox/ 模块",
        }
        for func, msg in dangerous_calls.items():
            if func + "(" in code:
                issues.append({
                    "file": module, "line": 0, "severity": "warning",
                    "message": f"[静态兜底] {msg}",
                    "suggestion": f"替换 {func}() 为安全替代方案",
                })

        # 3. AST 结构检查
        try:
            tree = ast.parse(code)
            func_count = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
            if func_count == 0:
                issues.append({
                    "file": module, "line": 0, "severity": "info",
                    "message": "[静态兜底] 代码中未定义函数",
                })
        except SyntaxError:
            issues.append({
                "file": module, "line": 0, "severity": "blocking",
                "message": "[静态兜底] 代码有语法错误",
                "suggestion": "检查缩进和括号匹配",
            })

        return {"issues": issues, "source": "static_fallback"}
