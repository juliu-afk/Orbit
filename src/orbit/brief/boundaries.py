"""边界规则引擎——解析 rules.yaml + 生成 lint/pre-commit 配置。

五层边界执行体系:
  L1: 声明层 — rules.yaml（数据）
  L2: Prompt 层 — 规则文本注入 Agent system prompt
  L3: 静态分析层 — 自动生成 ruff/eslint/bandit 配置
  L4: Pre-commit 层 — 自动生成 .pre-commit-config.yaml hooks
  L5: ReviewAgent 层 — 审查维度自动包含边界合规

本模块负责 L1/L3/L4/L5——L2 由 injector.py 和 PromptBuilder 协作完成。
"""

from __future__ import annotations

import structlog

from orbit.brief.models import BoundaryRule

logger = structlog.get_logger("orbit.brief.boundaries")

# ── 默认边界规则（所有项目通用）────────────────────────────
# WHY 默认值: 安全类规则不应依赖 LLM 生成——确定性定义保证零遗漏。

DEFAULT_RULES: list[BoundaryRule] = [
    BoundaryRule(
        rule_id="no-eval",
        description="禁止 eval/exec/compile——动态代码执行",
        severity="error",
        category="security",
        enforcement={
            "static_analysis": {"ruff_rules": ["S307"]},
            "pre_commit": True,
            "review_checklist": True,
        },
    ),
    BoundaryRule(
        rule_id="no-sql-injection",
        description="禁止字符串拼接 SQL——必须用参数化查询",
        severity="error",
        category="security",
        enforcement={
            "static_analysis": {"bandit_rules": ["B608"]},
            "pre_commit": True,
            "review_checklist": True,
        },
    ),
    BoundaryRule(
        rule_id="no-hardcoded-secrets",
        description="密钥/密码/Token 一律从环境变量读取，禁止硬编码",
        severity="error",
        category="security",
        enforcement={
            "static_analysis": {"ruff_rules": ["S105"], "grep_pattern": "sk-.*=.*['\"][A-Za-z0-9]"},
            "pre_commit": True,
            "review_checklist": True,
        },
    ),
    BoundaryRule(
        rule_id="no-unapproved-dependency",
        description="新增依赖需人工确认——不要为一个小功能引入一个包",
        severity="warning",
        category="governance",
        enforcement={
            "review_checklist": True,
        },
    ),
    BoundaryRule(
        rule_id="write-comments",
        description="业务逻辑、财务计算、会计规则必须注释 WHY——面向非编程人员审计",
        severity="warning",
        category="style",
        enforcement={
            "review_checklist": True,
        },
    ),
]


class BoundaryEngine:
    """边界规则引擎——解析 + 生成执行配置。"""

    def __init__(self) -> None:
        self._rules: list[BoundaryRule] = list(DEFAULT_RULES)

    @property
    def rules(self) -> list[BoundaryRule]:
        return self._rules

    def add_rule(self, rule: BoundaryRule) -> None:
        """添加自定义规则——避免 ID 重复。"""
        if any(r.rule_id == rule.rule_id for r in self._rules):
            logger.warning("duplicate_rule_id", rule_id=rule.rule_id)
            return
        self._rules.append(rule)

    def add_rules(self, rules: list[BoundaryRule]) -> None:
        for r in rules:
            self.add_rule(r)

    # ── 代码生成 ────────────────────────────────────────

    def generate_rules_yaml(self) -> str:
        """生成 .orbit/boundaries/rules.yaml 的 YAML 内容。

        WHY YAML 而非 JSON: 对非编程人员更可读，方便手动编辑。
        """
        lines = [
            "# Orbit 边界规则——自动生成，手动可编辑",
            f"# 规则数: {len(self._rules)}",
            "version: \"1.0\"",
            "rules:",
        ]
        for rule in self._rules:
            lines.append(f"  - id: \"{rule.rule_id}\"")
            lines.append(f"    description: \"{rule.description}\"")
            lines.append(f"    severity: {rule.severity}")
            lines.append(f"    category: {rule.category}")
            enf = rule.enforcement
            if enf:
                lines.append("    enforcement:")
                if enf.get("static_analysis"):
                    sa = enf["static_analysis"]
                    lines.append("      static_analysis:")
                    for k, v in sa.items():
                        if isinstance(v, list):
                            lines.append(f"        {k}: [{', '.join(repr(x) for x in v)}]")
                        else:
                            lines.append(f"        {k}: {v!r}")
                for bool_key in ("pre_commit", "review_checklist", "runtime_assert"):
                    if enf.get(bool_key):
                        lines.append(f"      {bool_key}: true")
            lines.append("")
        return "\n".join(lines)

    def generate_ruff_config(self) -> str:
        """从边界规则生成 ruff.toml 配置片段。

        WHY 自动生成: 边界规则声明了 lint 要求，手动翻译容易遗漏。
        """
        ruff_rules: set[str] = set()
        for rule in self._rules:
            sa = rule.enforcement.get("static_analysis", {})
            ruff_list = sa.get("ruff_rules", [])
            for r in ruff_list:
                ruff_rules.add(r)

        if not ruff_rules:
            return ""

        rules_str = ", ".join(sorted(ruff_rules))
        return (
            "# 由 Orbit 边界规则自动生成\n"
            "# 来源: .orbit/boundaries/rules.yaml\n\n"
            "[lint]\n"
            f"select = [{rules_str}]\n"
        )

    def generate_pre_commit_hooks(self) -> list[dict]:
        """生成 .pre-commit-config.yaml 的 hooks 列表。

        WHY 只生成 hooks 列表而非完整文件: 项目可能已有 pre-commit 配置，
        应追加而非覆盖。
        """
        hooks: list[dict] = []

        # 收集需要 pre-commit 的规则
        pre_commit_rules = [r for r in self._rules if r.enforcement.get("pre_commit")]
        if not pre_commit_rules:
            return hooks

        # ruff hook（如果任何规则引用了 ruff）
        has_ruff = any(
            r.enforcement.get("static_analysis", {}).get("ruff_rules")
            for r in pre_commit_rules
        )
        if has_ruff:
            hooks.append({
                "id": "ruff",
                "name": "Ruff (Orbit 边界规则)",
                "entry": "ruff check --fix",
                "language": "system",
                "types": ["python"],
            })

        # 自定义 grep hook
        for rule in pre_commit_rules:
            grep_pattern = rule.enforcement.get("static_analysis", {}).get("grep_pattern")
            if grep_pattern:
                hooks.append({
                    "id": f"orbit-{rule.rule_id}",
                    "name": f"Orbit: {rule.description}",
                    "entry": f'bash -c "! grep -rnE \'{grep_pattern}\' --include=\'*.py\' || '
                             f'{{ echo \'ERROR: {rule.rule_id}\'; exit 1; }}"',
                    "language": "system",
                    "types": ["python"],
                })

        return hooks

    def generate_review_checklist(self) -> list[str]:
        """生成 ReviewAgent 的边界合规检查清单。

        WHY 独立清单: ReviewerAgent 的审查维度按清单逐条检查，
        不依赖记忆。
        """
        checklist: list[str] = []
        for rule in self._rules:
            if rule.enforcement.get("review_checklist"):
                checklist.append(f"[{rule.severity.upper()}] {rule.rule_id}: {rule.description}")
        return checklist
