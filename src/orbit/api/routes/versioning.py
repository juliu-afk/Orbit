"""Versioning management API (Step 7.4)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from orbit.versioning.registry import VersionRegistry

router = APIRouter(prefix="/versioning", tags=["versioning"])

_registry = VersionRegistry()


class InstallRequest(BaseModel):
    version: str
    description: str = ""


@router.get("/current", summary="Get current version")
async def current_version() -> dict[str, Any]:
    version = _registry.current_version()
    return {"code": 0, "data": {"version": version or ""}, "message": "ok"}


@router.get("/versions", summary="List versions")
async def list_versions(limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    versions = _registry.list_versions(limit=limit)
    return {
        "code": 0,
        "data": [v.to_dict() for v in versions],
        "message": "ok",
    }


@router.post("/install", summary="Install version")
async def install_version(req: InstallRequest) -> dict[str, Any]:
    record = _registry.install_version(req.version, req.description)
    return {"code": 0, "data": record.to_dict(), "message": "ok"}


@router.get("/releases", summary="List releases")
async def list_releases(limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    releases = _registry.list_releases(limit=limit)
    return {
        "code": 0,
        "data": [r.to_dict() for r in releases],
        "message": "ok",
    }
