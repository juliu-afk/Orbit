"""消融实验上下文管理器——临时禁用模块以测量贡献度。

WHY 消融是金标准:
  证明模块有效的唯一方法 = 拿掉它 → 系统变差。
  F1 贡献 < 0.03 的模块应降级或移除（doc §17 原则 2）。

用法:
    from orbit.effectiveness import AblationContext

    # 方式1: 上下文管理器（推荐——自动清理）
    with AblationContext(["hallucination_L3", "reflection_engine"]):
        result = await orchestrator.run(goal)
    # 退出 with 块后自动恢复

    # 方式2: 手动控制
    AblationContext.disable("hallucination_L1")
    result = await pipeline.validate(code)
    AblationContext.reset()

检测点（在目标模块中插入）:
    from orbit.effectiveness import AblationContext
    if AblationContext.is_disabled("hallucination_L3"):
        continue  # 跳过该层
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import ClassVar


# 可消融的模块注册表——key 为消融目标名，value 为人读描述
ABLATION_TARGETS: dict[str, str] = {
    # 防幻觉各层
    "hallucination_L1": "防幻觉 L1 图谱验证——符号存在性检查",
    "hallucination_L2": "防幻觉 L2 动态追踪——运行时依赖分析",
    "hallucination_L3": "防幻觉 L3 熵监控——LLM 输出熵值检测",
    "hallucination_L4": "防幻觉 L4 类型检查——静态类型验证",
    "hallucination_L5": "防幻觉 L5 Z3 形式化——纯函数性质证明",
    "hallucination_L6": "防幻觉 L6 合约验证——输入/输出契约检查",
    "hallucination_L7": "防幻觉 L7 运行时沙箱——代码执行验证",
    "hallucination_L8": "防幻觉 L8 配置漂移——环境变量一致性",
    # 认知引擎
    "reflection_engine": "ReflectionEngine 反思——ReAct 轮次间自我修正",
    "goal_judge": "GoalJudge 自检——子任务完成后目标对齐检查",
    "preact_guard": "PreAct 风险预测——工具调用前安全评估",
    "vigil_healer": "VIGIL SelfHealer——工具失败后自动修复",
    # 流程门禁
    "critique_gate": "CritiqueAgent 门禁——CODING 后代码审查",
    "regression_guard": "RegressionGuard 回归检查——合并前全量测试",
    # 上下文系统
    "context_stage2": "Stage2 上下文——中等深度（~3000-8000t）",
    "context_stage3": "Stage3 上下文——最深（~12000-50000t）",
    "context_prebuilder": "ContextPrebuilder——5 个预构建器",
    "context_builder": "ContextBuilder——7 个上下文构建器",
    "context_scanner": "ContextScanner——5 个文件扫描器",
    "compression_pipeline": "CompressionPipeline——上下文压缩",
}


class AblationContext:
    """消融上下文管理器——类级别控制模块启用/禁用。

    线程安全: 使用 ClassVar + set 存储禁用列表。
    所有实例共享同一状态——同一时刻只有一个消融配置生效。

    WHY 类级别而非实例: 消融检查点分布在多个模块中，
    实例传递会增加耦合。类级别 = 全局开关，各模块自主查询。
    """

    _disabled: ClassVar[set[str]] = set()

    # ── 公共 API ──────────────────────────────────────

    @classmethod
    def disable(cls, *targets: str) -> None:
        """禁用指定模块。

        Args:
            targets: 消融目标名——必须是 ABLATION_TARGETS 中定义的 key。
                     未定义的 key 会被静默忽略（fail-safe）。
        """
        for t in targets:
            if t in ABLATION_TARGETS:
                cls._disabled.add(t)

    @classmethod
    def enable(cls, *targets: str) -> None:
        """重新启用指定模块。"""
        for t in targets:
            cls._disabled.discard(t)

    @classmethod
    def is_disabled(cls, target: str) -> bool:
        """检查模块是否被消融禁用。

        各模块在关键检查点调用此方法决定是否跳过自身逻辑。
        """
        return target in cls._disabled

    @classmethod
    def reset(cls) -> None:
        """清除所有禁用——恢复全部模块。"""
        cls._disabled.clear()

    @classmethod
    def active_targets(cls) -> set[str]:
        """返回当前被禁用的目标集合（只读副本）。"""
        return set(cls._disabled)

    # ── 上下文管理器 ──────────────────────────────────

    def __init__(self, targets: list[str]) -> None:
        """创建消融上下文。

        Args:
            targets: 要禁用的模块名列表
        """
        self._targets = targets
        self._entered = False

    def __enter__(self) -> AblationContext:
        """进入消融上下文——禁用指定模块。"""
        self.disable(*self._targets)
        self._entered = True
        return self

    def __exit__(self, *args: object) -> None:
        """退出消融上下文——恢复所有模块。"""
        self.enable(*self._targets)
        self._entered = False


# 便捷别名——with AblationContext.disable_and_scope([...])
AblationContext.disable_and_scope = AblationContext  # type: ignore[attr-defined]
