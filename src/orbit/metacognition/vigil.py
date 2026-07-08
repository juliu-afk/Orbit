"""VIGIL 自愈运行时 (Phase D4).

对标: VIGIL (2025)——观察、诊断、修复自身行为

WHY 区别于现有 checkpoint/回滚:
  现有: 出错 → 回滚到检查点 → 重试（可能遇到同样的错——因为病因没修）
  VIGIL: 出错 → 诊断根因 → 修复病因 → 继续（不回滚整个检查点）

设计:
  - FailurePattern: 已知失败模式→修复策略的映射库
  - SelfHealer: 诊断+修复+验证三步闭环
  - 修复策略: 参数修正 / 工具替换 / 上下文补充

V14.2+Theory (因果推理 方向 1):
  - _diagnose_causal(): DoWhy GCM 根因归因——替代规则匹配
  - diagnose_with_causal(): shadow mode——规则诊断 + 因果诊断并行，结果对比审计
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class FailureType(StrEnum):
    TOOL_NOT_FOUND = "tool_not_found"
    INVALID_ARGS = "invalid_args"
    PERMISSION_DENIED = "permission_denied"
    FILE_NOT_FOUND = "file_not_found"
    SYNTAX_ERROR = "syntax_error"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


@dataclass
class FailurePattern:
    """已知失败模式——错误文本→修复策略的映射。"""
    pattern: str           # 正则表达式匹配错误文本
    failure_type: FailureType
    fix_strategy: str      # 修复策略描述
    auto_fix: bool = True  # 是否可以自动修复


@dataclass
class DiagnosisResult:
    failure_type: FailureType
    root_cause: str           # 根因描述
    fix_strategy: str         # 修复策略
    auto_fixable: bool = True
    confidence: float = 0.8
    suggested_fix: dict = field(default_factory=dict)  # 具体的修复参数


@dataclass
class HealResult:
    success: bool = False
    diagnosis: DiagnosisResult | None = None
    action_taken: str = ""
    new_action: str = ""
    new_args: dict | None = None
    message: str = ""


# 已知失败模式库——正则匹配错误文本→修复策略
_FAILURE_PATTERNS: list[FailurePattern] = [
    FailurePattern(
        pattern=r"no such file|FileNotFoundError|ENOENT",
        failure_type=FailureType.FILE_NOT_FOUND,
        fix_strategy="使用 glob 查找实际文件位置",
        auto_fix=True,
    ),
    FailurePattern(
        pattern=r"Permission( denied|Error)|EACCES",
        failure_type=FailureType.PERMISSION_DENIED,
        fix_strategy="检查文件权限，尝试 read_file 代替 exec_command",
        auto_fix=True,
    ),
    FailurePattern(
        pattern=r"invalid (syntax|argument|parameter)|TypeError|ValueError",
        failure_type=FailureType.INVALID_ARGS,
        fix_strategy="修正参数类型或格式，参考工具 schema 重新构造参数",
        auto_fix=True,
    ),
    FailurePattern(
        pattern=r"timed? ?out|TimeoutError|asyncio.TimeoutError",
        failure_type=FailureType.TIMEOUT,
        fix_strategy="增加超时时间或减少请求规模",
        auto_fix=True,
    ),
    FailurePattern(
        pattern=r"(tool|function) not found|unknown tool",
        failure_type=FailureType.TOOL_NOT_FOUND,
        fix_strategy="检查工具名拼写，使用 list_tools 确认可用工具",
        auto_fix=True,
    ),
    FailurePattern(
        pattern=r"SyntaxError|IndentationError",
        failure_type=FailureType.SYNTAX_ERROR,
        fix_strategy="修正语法错误后重新写入文件",
        auto_fix=False,  # 需要确认修正内容
    ),
    FailurePattern(
        pattern=r"ConnectionError|NetworkError|HTTPError|503|502",
        failure_type=FailureType.NETWORK_ERROR,
        fix_strategy="等待后重试，或降级使用本地替代",
        auto_fix=True,
    ),
]


class VigilSelfHealer:
    """VIGIL 自愈运行时——诊断+修复+验证。

    用法:
        healer = VigilSelfHealer()
        result = healer.diagnose("FileNotFoundError: [Errno 2] No such file: 'ar_ledger.csv'")
        if result.auto_fixable:
            heal = healer.heal(result, current_action="read_file", current_args={"path":"ar_ledger.csv"})
            # heal.new_action = "glob", heal.new_args = {"pattern": "**/*ledger*"}
    """

    def __init__(self) -> None:
        self._heal_history: list[HealResult] = []

    def diagnose(self, error_text: str) -> DiagnosisResult:
        """诊断错误——匹配已知模式→确定类型和修复策略。"""
        for fp in _FAILURE_PATTERNS:
            if re.search(fp.pattern, error_text, re.IGNORECASE):
                return DiagnosisResult(
                    failure_type=fp.failure_type,
                    root_cause=f"匹配已知模式: {fp.failure_type.value}",
                    fix_strategy=fp.fix_strategy,
                    auto_fixable=fp.auto_fix,
                    confidence=0.85,
                    suggested_fix={"pattern": fp.pattern},
                )
        return DiagnosisResult(
            failure_type=FailureType.UNKNOWN,
            root_cause="未匹配已知失败模式",
            fix_strategy="回滚到检查点，人工介入",
            auto_fixable=False,
            confidence=0.3,
        )

    # ── V14.2+Theory: 因果诊断 + Shadow Mode ──────────────────

    async def _diagnose_causal(self, task_id: str,
                               causal_analyzer=None) -> DiagnosisResult | None:
        """DoWhy GCM 根因归因——替代规则匹配的因果诊断。

        Args:
            task_id: 失败任务 ID
            causal_analyzer: RootCauseAnalyzer 实例（外部注入）

        Returns:
            DiagnosisResult——因果驱动的诊断，或 None（因果分析不可用）
        """
        if causal_analyzer is None:
            return None
        try:
            root_cause = await causal_analyzer.analyze(task_id)
            if root_cause.top_cause is None or root_cause.confidence < 0.3:
                return None

            # 将因果根因映射为 DiagnosisResult——VIGIL 的 heal() 可直接消费
            cause = root_cause.top_cause
            ft_map: dict[str, FailureType] = {
                "agent_role": FailureType.INVALID_ARGS,      # 换 Agent = 修正参数
                "model_tier": FailureType.TIMEOUT,            # 升级模型层 = 延长超时
                "tool_error_rate": FailureType.TOOL_NOT_FOUND,# 工具序列优化
                "total_turns": FailureType.TIMEOUT,           # 过多轮次 = 时间问题
                "latency": FailureType.NETWORK_ERROR,         # 延迟 = 网络/模型问题
                "quality_score": FailureType.UNKNOWN,         # 低质量 = 需人工
            }
            return DiagnosisResult(
                failure_type=ft_map.get(cause.variable, FailureType.UNKNOWN),
                root_cause=f"[因果] {cause.variable}={cause.anomaly_score:.2f}——"
                           f"{cause.explanation or '见数值报告'}",
                fix_strategy=(
                    f"因果定向修复——变量 {cause.variable} 贡献了 "
                    f"{cause.anomaly_score:.0%} 的异常"
                ),
                auto_fixable=cause.variable != "quality_score",
                confidence=root_cause.confidence,
                suggested_fix={"causal_variable": cause.variable,
                               "anomaly_score": cause.anomaly_score},
            )
        except Exception:
            import structlog
            _logger = structlog.get_logger("orbit.vigil.causal")
            _logger.warning("causal_diagnosis_failed", task_id=task_id, exc_info=True)
            return None

    async def diagnose_with_causal(self, task_id: str, error_text: str,
                                   causal_analyzer=None) -> dict:
        """Shadow mode——规则诊断 + 因果诊断并行，结果对比审计。

        WHY shadow mode:
          因果诊断是新功能——不直接替换规则诊断。
          两条路径并行跑 1 周，对比成功率后数据驱动决策。

        Returns:
            {"rule": DiagnosisResult, "causal": DiagnosisResult|None,
             "winner": "rule"|"causal"|"tie"}
        """
        rule_result = self.diagnose(error_text)
        causal_result = await self._diagnose_causal(task_id, causal_analyzer)

        # 对比——差值 <0.1 视为并列（先检查 tie 避免不对称）
        winner = "rule"
        if causal_result and abs(causal_result.confidence -
                                  rule_result.confidence) < 0.1:
            winner = "tie"
        elif causal_result and causal_result.confidence > rule_result.confidence:
            winner = "causal"

        import structlog
        logger = structlog.get_logger("orbit.vigil.shadow")
        logger.info(
            "vigil_shadow_compare",
            task_id=task_id,
            rule_type=rule_result.failure_type.value,
            rule_conf=rule_result.confidence,
            causal_var=causal_result.suggested_fix.get("causal_variable")
                       if causal_result and causal_result.suggested_fix else None,
            causal_conf=causal_result.confidence if causal_result else 0,
            winner=winner,
        )
        return {"rule": rule_result, "causal": causal_result, "winner": winner}

    def heal(
        self, diagnosis: DiagnosisResult, current_action: str = "",
        current_args: dict | None = None,
    ) -> HealResult:
        """基于诊断结果生成修复方案。

        修复策略：
          - TOOL_NOT_FOUND → 建议用 list_tools 查正确名称
          - INVALID_ARGS → 修正参数格式
          - PERMISSION_DENIED → read_file 代替 exec_command
          - FILE_NOT_FOUND → glob 查找实际路径
          - TIMEOUT → 减小请求规模或拆分任务
          - NETWORK_ERROR → 等待后重试
        """
        args = current_args or {}

        if not diagnosis.auto_fixable:
            return HealResult(
                success=False, diagnosis=diagnosis,
                action_taken="none",
                message=f"无法自动修复: {diagnosis.root_cause}。建议人工介入。",
            )

        ft = diagnosis.failure_type

        if ft == FailureType.PERMISSION_DENIED and current_action == "exec_command":
            # 用 read_file 代替 exec_command
            new_action = "read_file"
            new_args = {"path": args.get("path", args.get("file", ""))}
            msg = f"权限拒绝——用 {new_action} 代替 {current_action}"
        elif ft == FailureType.FILE_NOT_FOUND:
            # 用 glob 查找
            new_action = "glob"
            path = args.get("path", args.get("file", ""))
            new_args = {"pattern": f"**/*{path.rsplit('/',1)[-1] if '/' in path else path}*"}
            msg = f"文件未找到——用 glob 查找: {new_args['pattern']}"
        elif ft == FailureType.INVALID_ARGS:
            # 用 read_file 先确认内容再修正
            new_action = "read_file"
            new_args = {"path": args.get("path", args.get("file", "."))}
            msg = "参数无效——先读取内容确认后修正"
        elif ft == FailureType.TIMEOUT:
            # 拆分或延长超时
            new_action = current_action
            new_args = {**args, "timeout": args.get("timeout", 30) * 2}
            msg = "超时——延长超时时间重试"
        elif ft == FailureType.NETWORK_ERROR:
            new_action = current_action
            new_args = dict(args)
            msg = "网络错误——建议等待后重试"
        else:
            new_action = current_action
            new_args = dict(args)
            msg = f"自动修复: {diagnosis.fix_strategy}"

        result = HealResult(
            success=True, diagnosis=diagnosis,
            action_taken=diagnosis.fix_strategy,
            new_action=new_action, new_args=new_args, message=msg,
        )
        self._heal_history.append(result)
        return result

    async def verify(self, heal: HealResult, sandbox=None) -> bool:
        """验证修复是否成功——在沙箱中试执行修复后的 Action。

        如果 sandbox 不可用，跳过验证——信任修复策略。
        """
        if sandbox is None or not heal.new_action:
            return heal.success
        try:
            result = await sandbox.execute(heal.new_action, heal.new_args or {})
            return result.return_code == 0
        except Exception:
            return False

    @property
    def heal_count(self) -> int:
        return len(self._heal_history)
