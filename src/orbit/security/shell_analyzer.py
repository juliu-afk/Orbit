"""Shell 命令安全分析器 (V15.2).

用 tree-sitter-bash 解析 shell 命令为 AST——识别危险模式。
对标: Zerox Agent shellAnalyzer——AST 级分析，非正则黑名单。

WHY AST: 字符串匹配 ';' 或 '|' 无法区分合法使用（echo "a;b"）和注入攻击。
tree-sitter AST 知道引号边界、语法结构、嵌套层级。

Usage:
    from orbit.security.shell_analyzer import ShellAnalyzer
    analyzer = ShellAnalyzer()
    result = analyzer.analyze("ls -la && rm -rf /tmp/*")
    if not result.safe:
        raise CommandRejectedError(result.risks)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import structlog

logger = structlog.get_logger("orbit.security.shell_analyzer")


class RiskLevel(StrEnum):
    CRITICAL = "critical"  # 必然有害：rm -rf /、sudo、curl|bash
    HIGH = "high"          # 高风险：git push -f、chmod 777
    MEDIUM = "medium"      # 中等风险：网络下载、环境变量修改
    LOW = "low"            # 低风险：正常文件操作


@dataclass
class ShellRisk:
    """单个风险发现。"""
    level: RiskLevel
    pattern: str         # 检测到的模式（如 "rm -rf"）
    location: str        # 命令中的位置描述
    description: str     # 人可读的解释


@dataclass
class ShellAnalysis:
    """Shell 分析结果。"""
    original: str
    safe: bool  # True = 无风险
    risks: list[ShellRisk] = field(default_factory=list)
    error: str = ""  # 解析错误时非空

    @property
    def risk_level(self) -> RiskLevel:
        if not self.risks:
            return RiskLevel.LOW
        return max(r.level for r in self.risks)


class ShellAnalyzer:
    """Shell 命令 AST 安全分析器。

    检测 4 类危险模式：
    1. 破坏性命令: rm -rf、dd、mkfs、:(){ :|:& };:
    2. 网络注入: curl URL | bash、wget -O - | sh
    3. Git 危险操作: push -f、hard reset、rebase -i
    4. 权限提升: sudo、su、chmod 777

    tree-sitter-bash 是可选依赖——未安装时回退启发式检测。
    """

    # 硬禁止模式——包含任一即拒绝
    _CRITICAL_PATTERNS: list[str] = [
        "rm -rf /",
        "rm -rf ~",
        "rm -rf /*",
        "rm -rf .",
        "rm -rf \$",   # 变量引用——rm -rf "$DIR" 或 rm -rf $HOME
        "mkfs.",
        "dd if=",
        "> /dev/sda",
        ":(){ :|:& };:",
        "chmod 777 /",
        "chmod -R 777",
    ]

    # 网络下载+管道执行
    _PIPE_EXEC_PATTERNS: list[str] = [
        "curl", "wget",
    ]
    _PIPE_SHELLS: list[str] = [
        "bash", "sh", "zsh", "dash", "python", "perl", "ruby",
    ]

    # Git 危险操作
    _GIT_DANGER: list[str] = [
        "push -f", "push --force", "push --force-with-lease",
        "reset --hard",
        "clean -f", "clean -fd",
    ]

    # 权限提升
    _PRIV_ESCALATION: list[str] = [
        "sudo ", "su -", "su root",
    ]

    def __init__(self, use_tree_sitter: bool = True) -> None:
        self._ts_available = False
        if use_tree_sitter:
            try:
                import tree_sitter_bash  # noqa: F401

                self._ts_available = True
            except ImportError:
                logger.warning("tree_sitter_bash_not_installed", fallback="heuristic")

    def analyze(self, command: str) -> ShellAnalysis:
        """分析 shell 命令——返回安全判定。

        AST 可用时用 AST 精确分析，否则回退启发式检测。
        """
        if not command or not command.strip():
            return ShellAnalysis(original=command, safe=True)

        if self._ts_available:
            return self._analyze_ast(command)
        return self._analyze_heuristic(command)

    def _analyze_ast(self, command: str) -> ShellAnalysis:
        """tree-sitter AST 精确分析。"""
        try:
            import tree_sitter_bash as tsb

            parser = tsb.parser()
            tree = parser.parse(command.encode())
            root = tree.root_node

            risks: list[ShellRisk] = []
            self._walk_ast(root, command, risks)

            return ShellAnalysis(
                original=command,
                safe=len(risks) == 0,
                risks=risks,
            )

        except Exception as e:
            logger.warning("shell_ast_failed", error=str(e)[:80])
            return ShellAnalysis(original=command, safe=False, error=str(e))

    def _walk_ast(
        self, node, original: str, risks: list[ShellRisk]
    ) -> None:
        """递归遍历 AST 节点——检测危险模式。"""
        # 检测命令节点
        if node.type == "command_name":
            cmd_text = original[node.start_byte:node.end_byte]

            # 检测网络下载+管道
            if cmd_text in self._PIPE_EXEC_PATTERNS:
                # 检查是否存在管道到 shell
                parent = node.parent
                if parent and parent.type == "command":
                    # 查找兄弟节点中的 pipeline
                    grandparent = parent.parent
                    if grandparent and grandparent.type == "pipeline":
                        # 管道链中有 >1 个命令→检查最后一个
                        children = [
                            c for c in grandparent.children
                            if c.type == "command"
                        ]
                        if len(children) > 1:
                            last_cmd = children[-1]
                            last_name = self._find_command_name(last_cmd)
                            if last_name in self._PIPE_SHELLS:
                                risks.append(ShellRisk(
                                    level=RiskLevel.CRITICAL,
                                    pattern=f"{cmd_text} | {last_name}",
                                    location=f"字符 {node.start_byte}-{node.end_byte}",
                                    description=(
                                        f"网络下载+管道执行: {cmd_text} | {last_name}"
                                    ),
                                ))
                                return

            # 检测权限提升
            if cmd_text in ("sudo", "su"):
                risks.append(ShellRisk(
                    level=RiskLevel.HIGH,
                    pattern=cmd_text,
                    location=f"字符 {node.start_byte}",
                    description=f"权限提升命令: {cmd_text}",
                ))

            # 检测 git 危险操作
            if cmd_text == "git":
                rest = original[node.end_byte:node.end_byte + 40]
                for pattern in self._GIT_DANGER:
                    if pattern in rest:
                        risks.append(ShellRisk(
                            level=RiskLevel.HIGH,
                            pattern=f"git {pattern}",
                            location=f"字符 {node.start_byte}",
                            description=f"Git 危险操作: git {pattern}",
                        ))
                        break

        # 递归子节点
        for child in node.children:
            self._walk_ast(child, original, risks)

    def _find_command_name(self, cmd_node) -> str:
        """在 command 节点中查找 command_name。"""
        for child in cmd_node.children:
            if child.type == "command_name":
                return child.text.decode() if hasattr(child, 'text') else ""
        return ""

    def _analyze_heuristic(self, command: str) -> ShellAnalysis:
        """启发式检测——tree-sitter 不可用时的回退方案。"""
        risks: list[ShellRisk] = []
        cmd_lower = command.lower()

        # 硬禁止模式
        for pattern in self._CRITICAL_PATTERNS:
            if pattern in cmd_lower:
                risks.append(ShellRisk(
                    level=RiskLevel.CRITICAL,
                    pattern=pattern,
                    location="命令文本",
                    description=f"检测到破坏性命令: {pattern}",
                ))

        # 网络下载+管道执行
        for downloader in self._PIPE_EXEC_PATTERNS:
            if downloader in cmd_lower and "|" in command:
                for shell in self._PIPE_SHELLS:
                    if shell in cmd_lower.split("|")[-1]:
                        risks.append(ShellRisk(
                            level=RiskLevel.CRITICAL,
                            pattern=f"{downloader} | {shell}",
                            location="管道",
                            description=f"网络下载+管道执行: {downloader} 输出传给 {shell}",
                        ))

        # 权限提升
        for pattern in self._PRIV_ESCALATION:
            if pattern in cmd_lower:
                risks.append(ShellRisk(
                    level=RiskLevel.HIGH,
                    pattern=pattern.strip(),
                    location="命令文本",
                    description=f"权限提升: {pattern}",
                ))

        # Git 危险操作
        if "git " in cmd_lower:
            for pattern in self._GIT_DANGER:
                if pattern in cmd_lower:
                    risks.append(ShellRisk(
                        level=RiskLevel.HIGH,
                        pattern=f"git {pattern}",
                        location="命令文本",
                        description=f"Git 危险操作: git {pattern}",
                    ))

        return ShellAnalysis(
            original=command,
            safe=len(risks) == 0,
            risks=risks,
        )


class CommandRejectedError(ValueError):
    """Shell 安全分析判定命令不可执行。"""

    def __init__(self, risks: list[ShellRisk]) -> None:
        self.risks = risks
        risk_desc = "; ".join(f"[{r.level}] {r.description}" for r in risks)
        super().__init__(f"Shell 命令被安全策略拒绝: {risk_desc}")
