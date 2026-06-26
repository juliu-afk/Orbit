"""Agent LLM 配置路由（Step 2.3 阶段四）。

GET  /api/v1/agents/{agent_name}/llm        — 查询 Agent 当前 LLM 配置
POST /api/v1/agents/{agent_name}/llm/switch  — 强制切换 Agent 的 LLM 模型
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from orbit.router.agent import ModelTier, RouterDecision
from orbit.router.resolver import AgentModelResolver

router = APIRouter(prefix="/agents", tags=["agents"])

# 已知 Agent 列表（与 scheduler/orchestrator.py 中 role_map 一致）
KNOWN_AGENTS = {"clarifier", "architect", "developer", "reviewer", "qa", "config_manager"}

# ── Response Models ──────────────────────────────


class LLMConfigCurrent(BaseModel):
    model: str
    source: str
    reason: str
    effective_since: str | None = None
    is_forced: bool = False


class LLMConfigResponse(BaseModel):
    agent: str
    current: LLMConfigCurrent | None = None
    available_sources: list[str] = Field(
        default_factory=lambda: [
            "cc_switch_force",
            "environment",
            "cc_switch",
            "router",
            "default",
        ]
    )
    cc_switch_active: bool = False
    cc_switch_config: str = ""


class SwitchRequest(BaseModel):
    model: str = Field(..., min_length=1, description="目标 LiteLLM 模型 ID")
    reason: str = Field("手动切换", description="切换原因")
    expires_at: str | None = Field(None, description="过期时间 ISO8601，到期后自动恢复")


class SwitchResponse(BaseModel):
    status: str  # "switched" | "no_change"
    agent: str
    model: str
    previous_model: str | None = None
    source: str = "manual"
    effective_since: str


# ── Routes ─────────────────────────────────────


@router.get("/{agent_name}/llm", response_model=LLMConfigResponse)
async def get_agent_llm_config(agent_name: str) -> LLMConfigResponse:
    """查询 Agent 当前实际使用的 LLM 配置。"""
    if agent_name.lower() not in KNOWN_AGENTS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未知 Agent: {agent_name}。已知: {', '.join(sorted(KNOWN_AGENTS))}",
        )

    resolver = AgentModelResolver()
    resolved = await resolver.resolve(agent_name)

    cc_config = os.getenv("CC_SWITCH", "")

    return LLMConfigResponse(
        agent=agent_name,
        current=LLMConfigCurrent(
            model=resolved.model or "(local rules)",
            source=resolved.source,
            reason=resolved.reason,
            is_forced=resolved.is_forced,
        ),
        cc_switch_active=bool(cc_config.strip()),
        cc_switch_config=cc_config,
    )


@router.post("/{agent_name}/llm/switch", response_model=SwitchResponse)
async def switch_agent_llm(agent_name: str, body: SwitchRequest) -> SwitchResponse:
    """强制切换 Agent 的 LLM 模型（临时覆盖）。

    将修改 CC_SWITCH 环境变量（进程内），优先级最高。
    expires_at 到期后需手动恢复或重新设置。
    """
    if agent_name.lower() not in KNOWN_AGENTS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未知 Agent: {agent_name}。已知: {', '.join(sorted(KNOWN_AGENTS))}",
        )

    # 获取切换前的模型
    resolver = AgentModelResolver()
    previous = await resolver.resolve(agent_name)
    previous_model = previous.model or None

    # 写入 CC_SWITCH（force 模式 = 最高优先级）
    new_entry = f"{agent_name}:{body.model},force"
    existing = os.getenv("CC_SWITCH", "")

    # 如果已有同 Agent 的 CC_SWITCH 配置，替换之；否则追加
    if existing:
        parts = []
        replaced = False
        for part in existing.split(","):
            part = part.strip()
            if ":" in part and part.split(":")[0].strip().lower() == agent_name.lower():
                parts.append(new_entry)
                replaced = True
            elif part and part not in ("force", "no-force"):
                parts.append(part)
        if not replaced:
            parts.append(new_entry)
        os.environ["CC_SWITCH"] = ",".join(parts)
    else:
        os.environ["CC_SWITCH"] = new_entry

    effective_since = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 记录到审计（如果有审计 logger）
    try:
        from orbit.core.config import settings

        if hasattr(settings, "audit_logger") and settings.audit_logger:
            settings.audit_logger.info(
                "agent_llm_switched",
                agent=agent_name,
                from_model=previous_model,
                to_model=body.model,
                reason=body.reason,
                expires_at=body.expires_at,
            )
    except Exception:
        pass  # 审计失败不阻塞切换

    return SwitchResponse(
        status="switched",
        agent=agent_name,
        model=body.model,
        previous_model=previous_model,
        source="manual",
        effective_since=effective_since,
    )
