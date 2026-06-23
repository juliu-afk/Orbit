"""AgentOps 配置——阈值、开关、冷却时间。

WHY 独立文件：AgentOps 配置项与核心 config.py 关注点不同——
核心配置管系统启动（DB/Redis/LLM），AgentOps 管运维阈值。
放在 observability/ 内聚，避免 core/config.py 膨胀。
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _get_bool(key: str, default: bool = False) -> bool:
    return _get(key, str(default)).lower() in ("1", "true", "yes")


def _get_int(key: str, default: int = 0) -> int:
    try:
        return int(_get(key, str(default)))
    except ValueError:
        return default


def _get_float(key: str, default: float = 0.0) -> float:
    try:
        return float(_get(key, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class AgentOpsConfig:
    """AgentOps 全局配置（frozen 防运行时篡改）。

    所有阈值可通过环境变量 AGENTOPS_* 覆盖。
    """

    # 告警阈值
    TOKEN_THRESHOLD_WARNING: int = _get_int("AGENTOPS_TOKEN_THRESHOLD_WARNING", 50)
    TOKEN_THRESHOLD_CRITICAL: int = _get_int("AGENTOPS_TOKEN_THRESHOLD_CRITICAL", 100)
    Z3_TIMEOUT_RATE_THRESHOLD: float = _get_float("AGENTOPS_Z3_TIMEOUT_RATE_THRESHOLD", 5.0)
    ENTROPY_BITS_THRESHOLD: float = _get_float("AGENTOPS_ENTROPY_BITS_THRESHOLD", 2.5)

    # 冷却时间（秒）：同一告警规则触发后，冷却期内不重复推送
    ALERT_COOLDOWN_SECONDS: int = _get_int("AGENTOPS_ALERT_COOLDOWN_SECONDS", 300)

    # 审计
    AUDIT_LOG_ENABLED: bool = _get_bool("AGENTOPS_AUDIT_LOG_ENABLED", True)
    LESSON_STORE_ENABLED: bool = _get_bool("AGENTOPS_LESSON_STORE_ENABLED", True)

    # 自动修复（生产默认关闭——只告警不自动执行修复脚本）
    AUTO_FIX_ENABLED: bool = _get_bool("AGENTOPS_AUTO_FIX_ENABLED", False)

    # 采样率：审计日志采样比例（0.0-1.0），生产可降采样控制成本
    AUDIT_SAMPLE_RATE: float = _get_float("AGENTOPS_AUDIT_SAMPLE_RATE", 1.0)


agentops_config = AgentOpsConfig()
