"""质量门禁判定 —— Agent 内循环的通过/失败/补充/永久失败判定。

WHY 独立文件：门禁逻辑与编排器解耦，可独立测试、独立调参。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class GateDecision(Enum):
    """门禁判定结果"""
    PASSED = "passed"              # 全部通过
    FAILED = "failed"              # 编译失败/安全问题 → 立即修复
    SUPPLEMENT = "supplement"      # 覆盖率不足/变异体存活 → 补测试
    FAILED_PERMANENT = "failed_permanent"  # 修复 3 轮仍失败 → 转人工


@dataclass
class TestRunResult:
    """一次测试运行的完整结果——门禁判定的输入。

    WHY dataclass: 纯数据载体，不需要 Pydantic 验证开销。API 层另有 Pydantic 模型。
    """
    __test__ = False  # 非 pytest 测试类
    task_id: str = ""
    status: str = "running"
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    coverage_pct: float = 0.0
    mutation_score: float | None = None  # 仅核心模块
    compiled: bool = True
    critical_vulnerabilities: int = 0
    duration_sec: float = 0.0
    repair_attempts: int = 0
    errors: list[str] = field(default_factory=list)
    # 框架适配检查结果
    framework_blockings: list[str] = field(default_factory=list)  # 循环依赖等阻塞项
    framework_warnings: list[str] = field(default_factory=list)   # 冗余/跨层等警告


class QualityGate:
    """Agent 内循环的门禁判定。

    判定顺序（短路）：编译 → 安全 → 覆盖率 → 变异 → 框架阻塞 → 通过。
    """

    # 门禁阈值——可调参
    BRANCH_COVERAGE_MIN: float = 0.80
    MUTATION_SCORE_MIN: float = 0.70
    MAX_REPAIR_ATTEMPTS: int = 3

    def evaluate(self, result: TestRunResult) -> GateDecision:
        """根据测试结果判定门禁。

        Returns:
            PASSED: 全部通过，可展示 diff
            FAILED: 编译失败/安全漏洞 → 触发修复循环
            SUPPLEMENT: 覆盖率或变异不足 → 触发补测试
            FAILED_PERMANENT: 修复次数耗尽 → 转人工
        """
        # 1. 修复次数耗尽 → 永久失败
        if result.repair_attempts >= self.MAX_REPAIR_ATTEMPTS:
            return GateDecision.FAILED_PERMANENT

        # 2. 编译失败 → 立即修复
        if not result.compiled:
            return GateDecision.FAILED

        # 3. 安全漏洞 → 立即修复
        if result.critical_vulnerabilities > 0:
            return GateDecision.FAILED

        # 4. 框架阻塞项（循环依赖）→ 立即修复
        if result.framework_blockings:
            return GateDecision.FAILED

        # 5. 覆盖率不足 → 补测试
        if result.coverage_pct < self.BRANCH_COVERAGE_MIN:
            return GateDecision.SUPPLEMENT

        # 6. 变异评分不足 → 补测试（仅核心模块有 mutation_score）
        if result.mutation_score is not None and result.mutation_score < self.MUTATION_SCORE_MIN:
            return GateDecision.SUPPLEMENT

        return GateDecision.PASSED

    def describe(self, result: TestRunResult) -> str:
        """生成人类可读的门禁判定描述。"""
        decision = self.evaluate(result)
        match decision:
            case GateDecision.PASSED:
                return "全部通过 ✓"
            case GateDecision.FAILED:
                reasons = []
                if not result.compiled:
                    reasons.append("编译失败")
                if result.critical_vulnerabilities > 0:
                    reasons.append(f"{result.critical_vulnerabilities} 个严重漏洞")
                if result.framework_blockings:
                    reasons.append(f"框架冲突: {', '.join(result.framework_blockings)}")
                return f"不通过 ✗ —— {'; '.join(reasons)}"
            case GateDecision.SUPPLEMENT:
                gaps = []
                if result.coverage_pct < self.BRANCH_COVERAGE_MIN:
                    gaps.append(f"覆盖率 {result.coverage_pct:.0%} < {self.BRANCH_COVERAGE_MIN:.0%}")
                if result.mutation_score is not None and result.mutation_score < self.MUTATION_SCORE_MIN:
                    gaps.append(f"变异评分 {result.mutation_score:.0%} < {self.MUTATION_SCORE_MIN:.0%}")
                return f"需补充 —— {'; '.join(gaps)}"
            case GateDecision.FAILED_PERMANENT:
                return f"修复 {result.repair_attempts} 轮仍未通过，转人工处理"
