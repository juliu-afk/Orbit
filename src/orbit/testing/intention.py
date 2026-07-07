"""Test Intention 提取器 —— 从 Goal/PRD/代码中提取可测试意图。

WHY 独立文件：意图提取是 L1 层的核心，不依赖 LLM（纯静态分析+模板），
可独立测试、可被阶段 1/2/3 复用。

参考：IntUT 框架——显式测试意图可提升分支覆盖 94%（ICSE 2025）。
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field


@dataclass
class TestIntention:
    """一条可测试意图——告诉 Agent 要测什么。

    WHY dataclass: 纯数据结构，后续可序列化注入 Prompt。
    """
    __test__ = False  # 非 pytest 测试类
    target: str = ""  # 被测目标，如 "users.py::create_user"
    positive: list[str] = field(default_factory=list)  # 正向路径
    negative: list[str] = field(default_factory=list)  # 异常/错误路径
    invariants: list[str] = field(default_factory=list)  # 不变量（用于 PBT）
    edge_cases: list[str] = field(default_factory=list)  # 边界条件
    dependencies: list[str] = field(default_factory=list)  # 外部依赖（需要 mock）
    gherkin_scenarios: list[str] = field(default_factory=list)  # 从 PRD 提取的 Gherkin 场景


class IntentionExtractor:
    """从多种输入源提取 TestIntention。

    支持：
    - PRD/Markdown 文本 → Gherkin 场景 + 业务规则
    - Python 源代码 → 函数签名 + 分支路径
    - Goal 描述 → 验收标准 → 测试意图
    """

    # 验收标准关键词——从 PRD 文本中识别可测试条件
    _AC_KEYWORDS = [
        "验收标准", "Acceptance Criteria", "AC:", "必须", "应该", "should", "must",
        "验证", "verify", "确认", "ensure", "检查", "check",
    ]

    # 函数签名提取正则
    _FUNC_RE = re.compile(
        r'(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)(?:\s*->\s*(\S+))?\s*:'
    )

    def extract_from_prd(self, prd_text: str) -> list[TestIntention]:
        """从 PRD/Markdown 文本中提取测试意图。

        识别：
        - 以 "验收标准" / "AC:" 开头的行 → Gherkin Scenario
        - 含 "必须"/"should"/"must" 的行 → 业务规则
        """
        intentions: list[TestIntention] = []
        lines = prd_text.split("\n")
        current_ac: list[str] = []
        in_ac_section = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # 检测验收标准段开始
            if any(kw in stripped for kw in ["验收标准", "Acceptance Criteria"]):
                in_ac_section = True
                continue
            # 检测段结束（下一个 # 标题或空行后的非列表行）
            if in_ac_section and stripped.startswith("#"):
                in_ac_section = False
                continue

            if in_ac_section and (stripped.startswith("-") or stripped.startswith("*") or stripped[0].isdigit()):
                # 去掉列表标记
                ac_text = re.sub(r'^[\s]*[-*\d.]+\s*', '', stripped)
                current_ac.append(ac_text)

        if current_ac:
            intention = TestIntention(
                target="from_prd",
                positive=current_ac,
                gherkin_scenarios=[self._ac_to_gherkin(ac) for ac in current_ac],
            )
            intentions.append(intention)

        return intentions

    def extract_from_code(self, code: str, module: str = "") -> TestIntention:
        """从 Python 源代码中提取测试意图。

        分析：函数签名 → 参数类型/默认值 → 正向/异常/边界路径。
        """
        intention = TestIntention(target=module or "unknown")

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return intention  # 代码有语法错误，返回空意图

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_name = node.name
                full_name = f"{module}::{func_name}" if module else func_name
                intention.target = full_name

                # 提取参数信息
                params = node.args
                arg_names = [a.arg for a in params.args if a.arg != "self" and a.arg != "cls"]

                # 有默认值的参数 → 边界 case 候选
                defaults_start = len(params.args) - len(params.defaults)
                for i, default in enumerate(params.defaults):
                    param_idx = defaults_start + i
                    if param_idx < len(params.args):
                        param_name = params.args[param_idx].arg
                        if param_name not in ("self", "cls"):
                            intention.edge_cases.append(
                                f"{param_name}=默认值({ast.unparse(default)})的边界行为"
                            )

                if arg_names:
                    # 正向路径——正常参数
                    intention.positive.append(f"{func_name}(valid_args) → 正常返回")
                    # 异常路径——空值/错误类型
                    intention.negative.append(f"{func_name}(None) → 应抛异常或返回错误")
                    # 依赖检测——参数中有外部类型
                    for ann in [params.args[i].annotation for i in range(len(params.args))
                                if params.args[i].arg not in ("self", "cls")]:
                        if ann and hasattr(ann, 'id'):
                            intention.dependencies.append(ann.id)  # type: ignore[attr-defined]

        return intention

    def extract_gherkin(self, prd_text: str, feature_name: str = "") -> list[str]:
        """从 PRD 验收标准生成 Gherkin 场景骨架（阶段 1 产出）。"""
        intentions = self.extract_from_prd(prd_text)
        all_scenarios: list[str] = []
        for intention in intentions:
            all_scenarios.extend(intention.gherkin_scenarios)
        return all_scenarios

    def extract_contract_tests(self, api_design: str) -> list[dict[str, str]]:
        """从 API 设计文本生成契约测试骨架（阶段 2 产出）。

        Returns:
            [{"method": "POST", "path": "/users", "positive": "...", "negative": "..."}, ...]
        """
        contracts: list[dict[str, str]] = []
        # 识别 HTTP 方法和路径
        method_path_re = re.compile(
            r'(GET|POST|PUT|DELETE|PATCH)\s+(/\S+)',
            re.IGNORECASE,
        )
        for match in method_path_re.finditer(api_design):
            method = match.group(1).upper()
            path = match.group(2)
            contracts.append({
                "method": method,
                "path": path,
                "positive": f"{method} {path} → 200/201",
                "negative": f"{method} {path} 缺少必填字段 → 422",
            })
        return contracts

    def _ac_to_gherkin(self, ac_text: str) -> str:
        """将一条验收标准文本转为 Gherkin Scenario 格式。"""
        # 简洁转换——保持中文原样
        return f"Scenario: {ac_text}"
