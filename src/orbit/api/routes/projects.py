"""Project API 路由 (Session PR #1).

端点:
  POST   /api/v1/projects             注册或更新项目
  GET    /api/v1/projects             列出所有项目
  GET    /api/v1/projects/{name}      查询单个项目
  GET    /api/v1/projects/{name}/brief  获取/生成项目说明书
  POST   /api/v1/projects/{name}/brief/refresh  强制重新生成说明书
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field

from orbit.projects.registry import ProjectRegistry

if TYPE_CHECKING:
    from orbit.gateway.client import LLMClient

router = APIRouter(prefix="/projects", tags=["projects"])

_registry = ProjectRegistry()

# BriefGenerator 依赖——由 api/main.py 在应用启动时注入
# WHY 模块级变量: 路由函数不是类方法，无法通过 __init__ 注入依赖。
# 采用与 _registry 相同的模块级模式。
_brief_llm: "LLMClient | None" = None


def set_brief_llm(llm: "LLMClient") -> None:
    """注入 Brief 生成用的 LLMClient——由 api/main.py 调用。

    WHY 独立 setter: 避免循环 import，main.py 创建 LLMClient 后注入。
    """
    global _brief_llm
    _brief_llm = llm


# ── Pydantic schemas ─────────────────────────────────


class ProjectCreateRequest(BaseModel):
    """注册或更新项目请求。"""

    name: str = Field(..., min_length=1, max_length=200, description="项目名称（文件夹名）")
    local_path: str = Field(..., min_length=1, max_length=1000, description="项目文件夹绝对路径")
    repo_url: str = Field("", max_length=500)
    description: str = Field("", max_length=1000)
    tags: list[str] = Field(default_factory=list)


# ── 路由 ─────────────────────────────────────────────


@router.post(
    "",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="注册或更新项目",
    description="注册新项目或更新已有项目。local_path 必须存在且可读。",
    responses={
        400: {"description": "路径不存在"},
        403: {"description": "路径无读取权限"},
    },
)
async def register_project(req: ProjectCreateRequest, background: BackgroundTasks) -> dict:
    # WHY 服务端验证路径：前端可能绕过或传错误路径，后端必须独立校验
    path = req.local_path
    if not os.path.isdir(path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "detail": f"路径 {path} 不存在，请检查后重试",
                "error_code": "PATH_NOT_FOUND",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
    if not os.access(path, os.R_OK):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "detail": f"路径 {path} 无读取权限",
                "error_code": "PATH_PERMISSION_DENIED",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    rec = _registry.register(
        name=req.name,
        local_path=path,
        repo_url=req.repo_url,
        description=req.description,
        tags=req.tags,
    )

    # 后台异步生成项目说明书——不阻塞注册响应
    # WHY BackgroundTasks: 说明书生成需 5-15 秒（LLM 调用），
    # 注册操作应在 200ms 内返回。
    if _brief_llm is not None:
        background.add_task(_generate_brief_background, req.name, path)

    return {
        "code": 0,
        "data": rec.to_dict(),
        "message": "ok",
    }


async def _generate_brief_background(project_name: str, project_path: str) -> None:
    """后台任务——生成项目说明书 + 边界规则。

    WHY 独立函数: BackgroundTasks.add_task() 需要可序列化的函数引用。
    """
    import structlog

    from orbit.brief.boundaries import BoundaryEngine
    from orbit.brief.generator import BriefGenerator, analyze_directory
    from orbit.brief.storage import write_boundaries, write_brief

    logger = structlog.get_logger("orbit.api.projects")

    try:
        gen = BriefGenerator(_brief_llm)  # type: ignore[arg-type]
        analysis = analyze_directory(project_path)
        brief = await gen.generate(project_path, analysis=analysis)
        write_brief(project_path, brief)

        # 生成边界规则
        engine = BoundaryEngine()
        write_boundaries(project_path, engine.generate_rules_yaml())

        # Part C: 批量生成目录级 CONTEXT.md
        await gen.generate_all_context_md(project_path, brief, min_subdirs=3)

        logger.info("brief_background_done", project=project_name, language=analysis.language)
    except Exception:
        logger.exception("brief_background_failed", project=project_name)


@router.get(
    "",
    response_model=dict,
    summary="列出所有项目",
)
async def list_projects() -> dict:
    projects = _registry.list_all()
    return {
        "code": 0,
        "data": [p.to_dict() for p in projects],
        "message": "ok",
    }


@router.get(
    "/{name}",
    response_model=dict,
    summary="查询单个项目",
    responses={404: {"description": "项目不存在"}},
)
async def get_project(name: str) -> dict:
    project = _registry.get(name)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "detail": f"项目 {name} 不存在",
                "error_code": "PROJECT_NOT_FOUND",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
    return {
        "code": 0,
        "data": project.to_dict(),
        "message": "ok",
    }


# ── 项目说明书端点 ─────────────────────────────────────


@router.get(
    "/{name}/brief",
    response_model=dict,
    summary="获取或生成项目说明书",
    description="返回 .orbit/brief.md 内容。如果不存在则自动生成。",
    responses={404: {"description": "项目不存在"}},
)
async def get_project_brief(name: str) -> dict:
    project = _registry.get(name)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "detail": f"项目 {name} 不存在",
                "error_code": "PROJECT_NOT_FOUND",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    from orbit.brief.checker import check_brief
    from orbit.brief.storage import read_brief

    status_result = check_brief(project.local_path)

    # 已有说明书——直接返回
    if status_result.has_brief:
        brief = read_brief(project.local_path)
        if brief:
            return {
                "code": 0,
                "data": {
                    "project_name": name,
                    "brief_markdown": brief.to_markdown(),
                    "status": status_result,
                    "generated": False,
                },
                "message": "ok",
            }

    # 无说明书 + 有 LLM → 自动生成
    if _brief_llm is not None:
        try:
            from orbit.brief.generator import BriefGenerator, analyze_directory
            from orbit.brief.storage import write_brief
            from orbit.brief.boundaries import BoundaryEngine

            gen = BriefGenerator(_brief_llm)
            analysis = analyze_directory(project.local_path)
            brief = await gen.generate(project.local_path, analysis=analysis)
            write_brief(project.local_path, brief)

            # 同时生成边界规则
            engine = BoundaryEngine()
            from orbit.brief.storage import write_boundaries
            write_boundaries(project.local_path, engine.generate_rules_yaml())

            return {
                "code": 0,
                "data": {
                    "project_name": name,
                    "brief_markdown": brief.to_markdown(),
                    "status": check_brief(project.local_path),
                    "generated": True,
                    "generated_by": brief.generated_by,
                },
                "message": "ok",
            }
        except Exception:
            import structlog
            logger = structlog.get_logger("orbit.api.projects")
            logger.exception("brief_generation_failed", project=name)
            return {
                "code": 0,
                "data": {
                    "project_name": name,
                    "brief_markdown": None,
                    "status": status_result,
                    "generated": False,
                    "error": "生成失败——LLM 调用异常，请稍后重试",
                },
                "message": "brief 生成失败",
            }

    # 无说明书 + 无 LLM → 返回状态
    return {
        "code": 0,
        "data": {
            "project_name": name,
            "brief_markdown": None,
            "status": status_result,
            "generated": False,
        },
        "message": "brief 不存在，且 LLM 客户端未配置——无法自动生成",
    }


@router.post(
    "/{name}/brief/refresh",
    response_model=dict,
    summary="强制重新生成项目说明书",
    responses={404: {"description": "项目不存在"}, 400: {"description": "LLM 未配置"}},
)
async def refresh_project_brief(name: str) -> dict:
    project = _registry.get(name)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "detail": f"项目 {name} 不存在",
                "error_code": "PROJECT_NOT_FOUND",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    if _brief_llm is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "detail": "LLM 客户端未配置，无法生成说明书",
                "error_code": "LLM_NOT_CONFIGURED",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    from orbit.brief.generator import BriefGenerator, analyze_directory
    from orbit.brief.storage import write_brief
    from orbit.brief.boundaries import BoundaryEngine
    from orbit.brief.storage import write_boundaries

    gen = BriefGenerator(_brief_llm)
    analysis = analyze_directory(project.local_path)
    brief = await gen.generate(project.local_path, analysis=analysis)
    write_brief(project.local_path, brief)

    # 刷新边界规则
    engine = BoundaryEngine()
    write_boundaries(project.local_path, engine.generate_rules_yaml())

    return {
        "code": 0,
        "data": {
            "project_name": name,
            "brief_markdown": brief.to_markdown(),
            "generated_by": brief.generated_by,
        },
        "message": "ok",
    }
