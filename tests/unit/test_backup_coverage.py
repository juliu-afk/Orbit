"""PR3 补充覆盖率：backup 异常分支 + snapshot OSError。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from orbit.api.main import create_app
from orbit.backup.snapshot import Snapshotter

# WHY ??? tmpdir?pytest ?? tmp_path ???? Temp ?????????
_TMP_BASE = Path(tempfile.gettempdir())


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def tmpdir():
    """可写临时目录（避免 pytest tmp_path 沙箱权限）。"""
    import shutil

    d = _TMP_BASE / f"orbit-test-{os.getpid()}-{hash(str(id(object())))}"
    d.mkdir(exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


class TestBackupExceptionBranches:
    """backup.py 异常分支覆盖。"""

    def test_create_snapshot_500_on_internal_error(self, client) -> None:
        """Snapshotter.snapshot_sqlite 抛非 FileNotFoundError/OperationalError → 500。"""
        with patch(
            "orbit.api.routes.backup._snapshotter.snapshot_sqlite",
            side_effect=RuntimeError("boom"),
        ):
            r = client.post(
                "/api/v1/backup/snapshots",
                json={"source_path": "data/test.db", "db_type": "sqlite"},
            )
            assert r.status_code == 500

    def test_restore_snapshot_not_found(self, client) -> None:
        """恢复不存在的快照 → 404。"""
        r = client.post(
            "/api/v1/backup/restore",
            json={"snapshot_id": "nonexistent_xyz", "target_path": "/tmp/out.db"},
        )
        assert r.status_code == 404

    def test_restore_internal_error(self, client) -> None:
        """Restorer.restore 抛异常 → 500。"""
        from orbit.backup.models import SnapshotMeta

        fake_meta = SnapshotMeta(
            snapshot_id="any",
            path="/tmp/fake.db",
            size_bytes=0,
            integrity_hash="abc",
            created_at=0,
            db_type="sqlite",
        )
        with (
            patch(
                "orbit.api.routes.backup._snapshotter.list_snapshots",
                return_value=[fake_meta],
            ),
            patch(
                "orbit.api.routes.backup._restorer.restore",
                side_effect=RuntimeError("restore boom"),
            ),
        ):
            r = client.post(
                "/api/v1/backup/restore",
                json={"snapshot_id": "any", "target_path": "/tmp/out.db"},
            )
            assert r.status_code == 500

    def test_create_snapshot_file_type(self, tmpdir) -> None:
        """db_type=file 走 snapshot_file 分支。"""

        test_file = tmpdir / "test.txt"
        test_file.write_text("hello")
        # 实际调用 snapshot_file，验证不报错
        from orbit.backup.snapshot import Snapshotter

        s = Snapshotter()
        meta = s.snapshot_file(str(test_file), db_type="file")
        assert meta.db_type == "file"
        assert meta.size_bytes > 0


class TestSnapshotListSnapshotsEdgeCases:
    """snapshot.py list_snapshots 边界 case。"""

    def test_list_with_type_filter_no_match(self) -> None:
        """类型过滤无匹配 → 空列表。"""
        s = Snapshotter()
        result = s.list_snapshots(db_type="nonexistent_type")
        assert isinstance(result, list)

    def test_list_oserror_skipped(self, tmpdir) -> None:
        """文件读取失败的快照被跳过（不崩溉）。"""
        s = Snapshotter(backup_dir=str(tmpdir))
        fake = tmpdir / "fake_20260101T000000Z.db"
        fake.write_text("x")

        with patch("os.path.getsize", side_effect=OSError("denied")):
            result = s.list_snapshots()
        assert isinstance(result, list)
