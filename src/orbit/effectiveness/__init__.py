"""模块效能测量——消融实验 + benchmark 运行器。

WHY 这个模块存在:
  现有测试全是 L0/L1 correctness（功能是否正常），零 L2 效能测量（模块是否提升了系统表现）。
  消融实验 (ablation study) 是证明模块有效性的金标准：拿掉模块 → 系统变差 → 模块有效。

模块:
  - ablation: 消融上下文管理器——临时禁用模块以测量贡献度
"""

from orbit.effectiveness.ablation import AblationContext, ABLATION_TARGETS

__all__ = ["AblationContext", "ABLATION_TARGETS"]
