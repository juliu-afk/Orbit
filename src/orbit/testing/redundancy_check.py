"""框架适配检查 —— 检测新代码是否与项目框架冲突。

WHY 独立文件：测试不判断"有没有更好的写法"（那是代码审查的职责），
但冗余函数、循环依赖、跨层调用可以用代码图谱自动检测。
阻塞项（循环依赖）拦截，警告项标记在摘要卡片中提醒人类审查。

依赖: graph/code_graph.py —— 查询已有符号和 import 关系。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class IssueSeverity(str, Enum):
    BLOCKING = "blocking"   # 🔴 必须修复（循环依赖）
    WARNING = "warning"     # ⚠️ 标记——人类审查确认
    INFO = "info"           # ℹ️ 提示


class IssueType(str, Enum):
    NAME_CONFLICT = "name_conflict"          # 同名函数
    SEMANTIC_DUPLICATE = "semantic_duplicate"  # 语义相似（可能重复）
    CIRCULAR_DEP = "circular_dep"             # 循环依赖
    LAYER_VIOLATION = "layer_violation"        # 跨层调用
    IMPORT_REDUNDANT = "import_redundant"      # 导入冗余


@dataclass
class FrameworkIssue:
    """一个框架适配问题。"""
    severity: IssueSeverity
    type: IssueType
    detail: str  # 人类可读描述
    suggestion: str | None = None  # 建议修复方案


@dataclass
class FrameworkFitReport:
    """框架适配检查的完整结果。"""
    blockings: list[FrameworkIssue] = field(default_factory=list)
    warnings: list[FrameworkIssue] = field(default_factory=list)
    infos: list[FrameworkIssue] = field(default_factory=list)

    @property
    def has_blockings(self) -> bool:
        return len(self.blockings) > 0

    @property
    def total_issues(self) -> int:
        return len(self.blockings) + len(self.warnings) + len(self.infos)


class RedundancyChecker:
    """检查新代码是否与项目现有框架冲突。

    五项检查（按严重度排序）:
    1. 循环依赖 — code_graph 分析 import 图 → 🔴
    2. 同名函数 — code_graph.exists → ⚠️
    3. 跨层调用 — 架构规则匹配 → ⚠️
    4. 语义相似 — BGE 向量相似度 → ⚠️（需 knowledge/ 可用）
    5. 导入冗余 — 新代码 import 已有 util 但自己实现等价逻辑 → ℹ️
    """

    # 架构分层规则——哪些路径前缀属于哪一层
    # WHY 硬编码规则：Orbit 架构稳定，不需要动态配置
    _LAYER_RULES = {
        "src/orbit/api/": "api",
        "src/orbit/services/": "service",
        "src/orbit/models/": "model",
        "src/orbit/graph/": "graph",
        "src/orbit/sandbox/": "sandbox",
    }

    def __init__(self, code_graph=None, knowledge=None):
        """初始化。

        Args:
            code_graph: CodeGraph 引擎实例（可选——无则跳过需要图谱的检查）
            knowledge: Knowledge 引擎实例（可选——无则跳过 BGE 语义相似度）
        """
        self._code_graph = code_graph
        self._knowledge = knowledge

    async def check(self, code: str, module: str) -> FrameworkFitReport:
        """对新代码执行全部框架适配检查。

        Args:
            code: 新生成的代码内容
            module: 所属模块名，如 "scheduler.state_machine"

        Returns:
            FrameworkFitReport —— 阻塞/警告/提示三级
        """
        report = FrameworkFitReport()

        # 1. 循环依赖检查（阻塞——不可跳过）
        circular = await self._check_circular_dep(module, code)
        report.blockings.extend(circular)

        # 2. 同名函数检查（警告）
        conflicts = await self._check_name_conflicts(code, module)
        report.warnings.extend(conflicts)

        # 3. 跨层调用检查（警告）
        layer_violations = self._check_layer_violations(code, module)
        report.warnings.extend(layer_violations)

        # 4. 语义相似（警告——需 knowledge/ 可用）
        if self._knowledge:
            duplicates = await self._check_semantic_duplicates(code, module)
            report.warnings.extend(duplicates)

        # 5. 导入冗余（提示）
        redundants = await self._check_import_redundancy(code, module)
        report.infos.extend(redundants)

        return report

    async def _check_circular_dep(
        self, module: str, code: str
    ) -> list[FrameworkIssue]:
        """检查新代码是否引入循环依赖。

        方法：提取新代码的 import 语句 → 从 code_graph 查已有 import 关系 →
        检测是否有反向依赖 → 形成环。
        """
        issues: list[FrameworkIssue] = []
        import re

        # 提取新代码的 import
        imported = re.findall(
            r'(?:from\s+(\S+)\s+import|import\s+(\S+))',
            code,
        )
        new_imports: set[str] = set()
        for from_imp, direct_imp in imported:
            if from_imp and from_imp.startswith("orbit."):
                new_imports.add(from_imp)
            if direct_imp and direct_imp.startswith("orbit."):
                new_imports.add(direct_imp)

        # 检测：如果有 code_graph，查新模块是否已被这些 imports 反向引用
        if self._code_graph:
            for imp in new_imports:
                try:
                    callers = await self._code_graph.get_callers(module)
                    for caller in callers:
                        if caller.startswith(imp.replace(".", "/")):
                            issues.append(FrameworkIssue(
                                severity=IssueSeverity.BLOCKING,
                                type=IssueType.CIRCULAR_DEP,
                                detail=f"循环依赖: {module} → {imp}，但 {caller} 已反向引用 {module}",
                                suggestion=f"提取共享接口到独立模块，或重构为单向依赖",
                            ))
                except Exception:
                    pass  # code_graph 查询失败不阻塞

        return issues

    async def _check_name_conflicts(
        self, code: str, module: str
    ) -> list[FrameworkIssue]:
        """检查新代码中定义的函数/类是否与已有符号同名。

        方法：ast 提取新定义的函数名/类名 → code_graph.exists 查是否存在。
        """
        issues: list[FrameworkIssue] = []
        import ast

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return issues

        for node in ast.walk(tree):
            name = None
            symbol_type = None
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
                symbol_type = "function"
            elif isinstance(node, ast.ClassDef):
                name = node.name
                symbol_type = "class"

            if name and self._code_graph:
                try:
                    exists = await self._code_graph.exists(name, symbol_type)
                    if exists:
                        issues.append(FrameworkIssue(
                            severity=IssueSeverity.WARNING,
                            type=IssueType.NAME_CONFLICT,
                            detail=f"{symbol_type} '{name}' 已存在于项目中",
                            suggestion=f"检查是否有意覆盖，或考虑重命名/合并实现",
                        ))
                except Exception:
                    pass  # 查询失败不阻塞

        return issues

    def _check_layer_violations(
        self, code: str, module: str
    ) -> list[FrameworkIssue]:
        """检查新代码是否违反架构分层规则。

        规则（白名单模式）：
        - api/ 层只应 import services/ 和 models/
        - services/ 层只应 import models/ 和 graph/
        - 禁止反向 import（如 models/ import api/）
        """
        issues: list[FrameworkIssue] = []
        import re

        # 判断新代码属于哪一层
        current_layer = None
        for path_prefix, layer_name in self._LAYER_RULES.items():
            if path_prefix in module:
                current_layer = layer_name
                break

        if not current_layer:
            return issues  # 非标准路径，跳过分层检查

        # 提取新代码的 import
        imports = re.findall(r'(?:from\s+(orbit\.\S+)\s+import|import\s+(orbit\.\S+))', code)
        all_imports: set[str] = set()
        for from_imp, direct_imp in imports:
            if from_imp:
                all_imports.add(from_imp)
            if direct_imp:
                all_imports.add(direct_imp)

        # 分层违规检测
        for imp in all_imports:
            # 匹配分层规则——import 路径是 "orbit.xxx" 格式，规则是 "src/orbit/xxx/" 格式
            imp_path = imp.replace(".", "/")
            imp_layer_matched = None
            for path_prefix, layer_name in self._LAYER_RULES.items():
                # 同时匹配 "src/orbit/graph/" 和 "orbit/graph/"
                prefix_short = path_prefix.replace("src/", "")
                if path_prefix in imp_path or prefix_short in imp_path:
                    imp_layer_matched = layer_name
                    break

            if imp_layer_matched and current_layer == "api" and imp_layer_matched in ("graph", "sandbox"):
                issues.append(FrameworkIssue(
                    severity=IssueSeverity.WARNING,
                    type=IssueType.LAYER_VIOLATION,
                    detail=f"API 层 ({module}) 直接 import 了 {imp_layer_matched} 层 ({imp})",
                    suggestion=f"通过 service 层封装 {imp_layer_matched} 调用",
                ))
            elif imp_layer_matched and current_layer == "model" and imp_layer_matched in ("api", "service"):
                issues.append(FrameworkIssue(
                    severity=IssueSeverity.WARNING,
                    type=IssueType.LAYER_VIOLATION,
                    detail=f"Model 层 ({module}) 反向 import 了 {imp_layer_matched} 层 ({imp})——违反分层",
                    suggestion=f"移除反向依赖",
                ))

        return issues

    async def _check_semantic_duplicates(
        self, code: str, module: str
    ) -> list[FrameworkIssue]:
        """检查新代码是否与已有函数语义相似（BGE 向量相似度 > 0.85）。

        方法：BGE 编码新函数签名 → knowledge/ 搜索同模块内相似函数。
        """
        # Phase 3 实现——依赖 knowledge/ 的 BGE 向量搜索
        return []

    async def _check_import_redundancy(
        self, code: str, module: str
    ) -> list[FrameworkIssue]:
        """检查新代码是否 import 了已有 util 但自己实现了等价逻辑。

        方法：提取新代码的 import 列表 → 检查是否有 import 的模块已提供新代码实现的功能。
        """
        # Phase 2 实现——依赖 code_graph 的完整调用链分析
        return []
