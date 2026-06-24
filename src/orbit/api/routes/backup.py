"""???? API?Step 7.4/7.5??

??:
  GET  /api/v1/backup/snapshots        ????
  POST /api/v1/backup/snapshots        ?????SQLite/???
  POST /api/v1/backup/restore          ????
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from orbit.backup.models import RestoreResult
from orbit.backup.restore import Restorer
from orbit.backup.snapshot import Snapshotter

router = APIRouter(prefix="/backup", tags=["backup"])

_snapshotter = Snapshotter()
_restorer = Restorer()


class SnapshotCreateRequest(BaseModel):
    """???????"""

    source_path: str
    db_type: str = "sqlite"  # sqlite | knowledge | checkpoint | file


class RestoreRequest(BaseModel):
    """???????"""

    snapshot_id: str
    target_path: str


@router.get("/snapshots", summary="??????")
async def list_snapshots(db_type: str = Query("", description="?????")) -> dict[str, Any]:
    """????????????????"""
    snapshots = _snapshotter.list_snapshots(db_type=db_type)
    return {
        "code": 0,
        "data": [s.to_dict() for s in snapshots],
        "message": "ok",
    }


@router.post("/snapshots", summary="??????")
async def create_snapshot(req: SnapshotCreateRequest) -> dict[str, Any]:
    """?????SQLite ? .backup API????????"""
    try:
        if req.db_type in ("sqlite", "knowledge", "checkpoint"):
            meta = _snapshotter.snapshot_sqlite(req.source_path, db_type=req.db_type)
        else:
            meta = _snapshotter.snapshot_file(req.source_path, db_type=req.db_type)
    except (FileNotFoundError, sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        raise HTTPException(status_code=404, detail=f"???????: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"??????: {e}") from e
    return {"code": 0, "data": meta.to_dict(), "message": "ok"}


@router.post("/restore", summary="????")
async def restore_snapshot(req: RestoreRequest) -> dict[str, Any]:
    """???????????"""
    snapshots = _snapshotter.list_snapshots()
    target = next((s for s in snapshots if s.snapshot_id == req.snapshot_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"?? {req.snapshot_id} ???")
    try:
        result: RestoreResult = _restorer.restore(target, req.target_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"????: {e}") from e
    if not result.success:
        raise HTTPException(status_code=500, detail=result.reason)
    return {"code": 0, "data": {"restored": True, "target": req.target_path}, "message": "ok"}
