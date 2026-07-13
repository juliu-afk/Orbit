"""Skills API——Skill CRUD + 版本管理。

端点:
    GET    /skills           → 列出所有 ChatSkill
    GET    /skills/{name}    → 单个 Skill 详情
    POST   /skills           → 创建新 Skill
    PUT    /skills/{name}    → 更新 Skill
    DELETE /skills/{name}    → 删除 Skill
    GET    /skills/{name}/versions → 版本历史
    POST   /skills/{name}/rollback → 回滚到指定版本
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from orbit.skills.registry import get_skill_registry

router = APIRouter(prefix="/skills", tags=["skills"])


# ── 请求/响应模型 ──────────────────────────────────


class SkillCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str = ""
    triggers: list[str] = Field(default_factory=list)
    phase: str = "chat"
    tools: list[str] = Field(default_factory=list)
    agent_role: str = "developer"
    body: str = ""


class SkillUpdateRequest(BaseModel):
    description: str | None = None
    triggers: list[str] | None = None
    phase: str | None = None
    tools: list[str] | None = None
    agent_role: str | None = None
    body: str | None = None
    is_chat_skill: bool | None = None
    is_chainable: bool | None = None
    version_bump: str = "patch"  # "major" | "minor" | "patch"
    change_summary: str = ""


class SkillSummaryResponse(BaseModel):
    name: str
    description: str
    phase: str
    version: str
    triggers: list[str]


class SkillListResponse(BaseModel):
    skills: list[SkillSummaryResponse]


class RollbackRequest(BaseModel):
    version: str = Field(..., description="目标版本号")


class VersionListResponse(BaseModel):
    name: str
    versions: list[dict]


# ── 端点 ───────────────────────────────────────────


@router.get("")
async def list_skills():
    """列出所有聊天框可调用的 Skill——用于前端 / 补全 + 管理面板。"""
    registry = get_skill_registry()
    skills = registry.list_all()
    return {
        "code": 0,
        "data": {
            "skills": [
                {
                    "name": s.name,
                    "description": s.description,
                    "phase": s.phase,
                    "version": s.version,
                    "triggers": s.triggers,
                }
                for s in skills
            ],
        },
    }


@router.get("/{name}")
async def get_skill(name: str):
    """获取单个 Skill 详情——含 body。"""
    registry = get_skill_registry()
    skill = registry.get(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {name} 不存在")
    return {
        "code": 0,
        "data": skill.model_dump(),
    }


@router.post("", status_code=201)
async def create_skill(body: SkillCreateRequest):
    """创建新 Skill——写 SKILL.md 到 definitions/ 目录。"""
    registry = get_skill_registry()
    try:
        skill = registry.create(body.name, body.model_dump())
        return {"code": 0, "data": skill.model_dump()}
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/{name}")
async def update_skill(name: str, body: SkillUpdateRequest):
    """更新已有 Skill——写回 SKILL.md。"""
    registry = get_skill_registry()
    try:
        data = {k: v for k, v in body.model_dump().items() if v is not None}
        skill = registry.update(name, data)
        return {"code": 0, "data": skill.model_dump()}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{name}")
async def delete_skill(name: str):
    """删除 Skill + 对应 SKILL.md 文件。"""
    registry = get_skill_registry()
    deleted = registry.delete(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Skill {name} 不存在")
    return {"code": 0, "message": f"Skill {name} 已删除"}


@router.get("/{name}/versions")
async def get_skill_versions(name: str):
    """获取 Skill 版本历史。"""
    registry = get_skill_registry()
    skill = registry.get(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {name} 不存在")
    versions = registry.get_versions(name)
    return {
        "code": 0,
        "data": {
            "name": name,
            "versions": [v.model_dump() for v in versions],
        },
    }


@router.post("/{name}/rollback")
async def rollback_skill(name: str, body: RollbackRequest):
    """回滚 Skill 到指定版本。"""
    registry = get_skill_registry()
    try:
        skill = registry.rollback(name, body.version)
        return {"code": 0, "data": skill.model_dump()}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
