"""配置面板 API（Inkeep 借鉴 #5）。

Git 后端——branch/merge/diff/log/rollback 全部通过 git CLI。
"""

from __future__ import annotations

from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from orbit.core.config_store import ConfigError, ConfigSection, ConfigStore

router = APIRouter(prefix="/config", tags=["config"])

_store = ConfigStore()
# WHY try-except: PyInstaller 打包后工作目录不对/git 不可用，init 可能失败
# 不能阻塞整个应用启动，路由可用后再延迟初始化
try:
    _store.init()  # 幂等——首次调用自动初始化 Git 仓库
except Exception:
    pass  # 首次 API 调用时会重试


class WriteConfigRequest(BaseModel):
    content: str = Field(..., description="YAML 文本内容")
    author: str = Field(default="ui", description="提交者标识")


class RollbackRequest(BaseModel):
    commit_hash: str
    author: str = Field(default="ui")


class BranchRequest(BaseModel):
    name: str
    from_branch: str = "main"


class MergeRequest(BaseModel):
    from_branch: str
    into_branch: str = "main"
    author: str = Field(default="ui")


class ConflictResolveRequest(BaseModel):
    resolved_content: str
    author: str = Field(default="ui")


# ── 配置读写 ──────────────────────────────────────────────

@router.get("/{section}", summary="读取配置")
async def read_config(section: str) -> dict[str, Any]:
    """读取指定 section 的 YAML 配置。"""
    try:
        data = _store.read(section)
    except ConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"code": 0, "data": data, "message": "ok"}


@router.put("/{section}", summary="保存配置")
async def write_config(section: str, req: WriteConfigRequest) -> dict[str, Any]:
    """保存配置——YAML 校验 → 写入文件 → git commit。"""
    # YAML 语法校验
    try:
        data = yaml.safe_load(req.content)
        if not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="配置内容必须是 YAML mapping")
    except yaml.YAMLError as e:
        # 提取行号/列号
        detail = str(e)
        if hasattr(e, "problem_mark") and e.problem_mark:
            mark = e.problem_mark  # type: ignore[attr-defined]
            detail = f"第 {mark.line + 1} 行, 第 {mark.column + 1} 列: {e.problem}"
        raise HTTPException(status_code=400, detail=detail)

    try:
        commit_hash = _store.write(section, data, author=req.author)
    except ConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"code": 0, "data": {"commit_hash": commit_hash, "section": section}, "message": "ok"}


# ── 版本历史 ──────────────────────────────────────────────

@router.get("/{section}/history", summary="版本历史")
async def config_history(
    section: str, limit: int = Query(default=20, ge=1, le=100)
) -> dict[str, Any]:
    """返回 section 的 Git log。"""
    try:
        commits = _store.history(section, limit=limit)
    except ConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "code": 0,
        "data": [
            {
                "hash": c.hash,
                "full_hash": c.full_hash,
                "message": c.message,
                "author": c.author,
                "timestamp": c.timestamp,
            }
            for c in commits
        ],
        "message": "ok",
    }


@router.get("/{section}/diff", summary="版本对比")
async def config_diff(
    section: str,
    from_hash: str = Query(..., alias="from"),
    to_hash: str = Query(..., alias="to"),
) -> dict[str, Any]:
    """返回两个 commit 之间的 unified diff。"""
    try:
        diff_text = _store.diff(from_hash, to_hash, section)
    except ConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"code": 0, "data": {"unified_diff": diff_text}, "message": "ok"}


# ── 回滚 ──────────────────────────────────────────────────

@router.post("/{section}/rollback", summary="回滚配置")
async def config_rollback(section: str, req: RollbackRequest) -> dict[str, Any]:
    """回滚到指定 commit——checkout 旧版本 + 新 commit。"""
    try:
        new_hash = _store.rollback(section, req.commit_hash, author=req.author)
    except ConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"code": 0, "data": {"new_commit_hash": new_hash}, "message": "ok"}


# ── 分支操作 ──────────────────────────────────────────────

@router.get("/branches/list", summary="分支列表")
async def config_branches() -> dict[str, Any]:
    """列出所有分支。"""
    try:
        branches = _store.branches()
    except ConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "code": 0,
        "data": [
            {"name": b.name, "is_current": b.is_current} for b in branches
        ],
        "message": "ok",
    }


@router.post("/branches", summary="创建分支")
async def config_create_branch(req: BranchRequest) -> dict[str, Any]:
    """创建新分支。"""
    try:
        _store.create_branch(req.name)
    except ConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"code": 0, "data": {"name": req.name}, "message": "ok"}


@router.post("/branches/switch", summary="切换分支")
async def config_switch_branch(name: str = Query(...)) -> dict[str, Any]:
    """切换到指定分支。"""
    try:
        _store.switch_branch(name)
    except ConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"code": 0, "data": {"current_branch": name}, "message": "ok"}


# ── 合并 ──────────────────────────────────────────────────

@router.post("/merge", summary="合并分支")
async def config_merge(req: MergeRequest) -> dict[str, Any]:
    """合并分支——冲突时返回冲突文件列表。"""
    try:
        result = _store.merge(req.from_branch, author=req.author)
    except ConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "code": 0,
        "data": {
            "success": result.success,
            "conflict_files": result.conflict_files,
            "message": result.message,
        },
        "message": "ok",
    }


@router.get("/conflict/{section}", summary="读取冲突文件")
async def config_conflict_content(section: str) -> dict[str, Any]:
    """读取冲突文件原始内容（含 <<<<<<< 标记）。"""
    try:
        content = _store.conflict_content(section)
    except ConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"code": 0, "data": {"content_with_markers": content}, "message": "ok"}


@router.put("/conflict/{section}", summary="解决冲突")
async def config_resolve_conflict(section: str, req: ConflictResolveRequest) -> dict[str, Any]:
    """手动解决冲突——写文件 + git add + git commit。"""
    try:
        commit_hash = _store.resolve_conflict(section, req.resolved_content, author=req.author)
    except ConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"code": 0, "data": {"commit_hash": commit_hash}, "message": "ok"}
