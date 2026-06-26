"""CC_SWITCH 环境变量解析器。

格式:
    CC_SWITCH="all:deepseek-v3"
    CC_SWITCH="DeveloperAgent:glm-5.2,ArchitectAgent:deepseek-v3"
    CC_SWITCH="DeveloperAgent:glm-5.2,force"
    CC_SWITCH="DeveloperAgent:glm-5.2,no-force"

force 模式: 覆盖环境变量和 RouterAgent 推荐（最高优先级）。
no-force 模式: 仅当没有更高优先级配置时生效。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger("orbit.router.cc_switch")


@dataclass
class CCSwitchEntry:
    agent_name: str  # "all" 表示全部
    model: str  # LiteLLM 模型 ID
    mode: str = "no-force"  # "force" | "no-force"

    @property
    def is_force(self) -> bool:
        return self.mode == "force"


@dataclass
class CCSwitchConfig:
    entries: list[CCSwitchEntry] = field(default_factory=list)
    raw: str = ""


def parse_cc_switch(raw: str | None = None) -> CCSwitchConfig:
    """解析 CC_SWITCH 环境变量。

    预处理：先替换 ',force' / ',no-force' 为临时标记，再按逗号分割。
    格式错误 → WARN 日志 + 跳过该条目，不抛异常。
    """
    if raw is None:
        raw = os.getenv("CC_SWITCH", "")

    if not raw.strip():
        return CCSwitchConfig(raw=raw or "")

    # 预处理：将模式标记替换为分隔符不会拆分的格式
    # ",force" / ",no-force" 只在键值对末尾出现，是模式修饰符而非新条目
    processed = raw.strip()
    processed = processed.replace(",no-force", "|no-force")
    processed = processed.replace(",force", "|force")

    entries: list[CCSwitchEntry] = []
    for segment in processed.split(","):
        segment = segment.strip()
        if not segment:
            continue
        try:
            entries.append(_parse_entry(segment))
        except ValueError as e:
            logger.warning("cc_switch_parse_error", segment=segment, error=str(e))

    return CCSwitchConfig(entries=entries, raw=raw)


def _parse_entry(segment: str) -> CCSwitchEntry:
    """解析单个条目。

    格式:
        'AgentName:model'          → no-force 模式
        'AgentName:model|force'    → force 模式（预处理后）
        'AgentName:model|no-force' → no-force 模式（预处理后）
        'all:model'                → 全部 Agent
    """
    if ":" not in segment:
        raise ValueError(f"缺少冒号分隔符: {segment}")

    mode = "no-force"
    if "|force" in segment:
        mode = "force"
        segment = segment.replace("|force", "")
    elif "|no-force" in segment:
        mode = "no-force"
        segment = segment.replace("|no-force", "")

    agent_name, model = segment.split(":", 1)
    agent_name = agent_name.strip()
    model = model.strip()

    if not agent_name or not model:
        raise ValueError(f"Agent 名或模型名为空: {segment}")

    return CCSwitchEntry(agent_name=agent_name, model=model, mode=mode)
