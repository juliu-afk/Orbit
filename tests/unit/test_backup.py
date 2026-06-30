"""Step 7.4/7.5 PR #1——备份管理器单元测试。

覆盖: Snapshotter / Integrity / Restorer / 全流程闭环
"""

import os
import tempfile

from orbit.backup.integrity import compute_hash, verify_integrity
from orbit.backup.restore import Restorer
from orbit.backup.snapshot import Snapshotter

# ── Integrity ────────────────────────────────────────────


class TestIntegrity:
    """SHA256 哈希计算 + 完整性验证。"""

    def test_compute_hash_consistent(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"hello orbit backup")
            path = f.name
        try:
            h1 = compute_hash(path)
            h2 = compute_hash(path)
            assert h1 == h2
            assert len(h1) == 64  # SHA256 hex = 64 chars
        finally:
            os.unlink(path)

    def test_compute_hash_different_content(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"content A")
            path_a = f.name
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"content B")
            path_b = f.name
        try:
            assert compute_hash(path_a) != compute_hash(path_b)
        finally:
            os.unlink(path_a)
            os.unlink(path_b)

    def test_verify_integrity_match(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"test data")
            path = f.name
        try:
            h = compute_hash(path)
            assert verify_integrity(path, h) is True
        finally:
            os.unlink(path)

    def test_verify_integrity_mismatch(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"test data")
            path = f.name
        try:
            assert verify_integrity(path, "abc123wronghash") is False
        finally:
            os.unlink(path)

    def test_verify_integrity_file_missing(self) -> None:
        assert verify_integrity("/nonexistent/path.db", "abc123") is False


# ── Snapshotter ───────────────────────────────────────────


class TestSnapshotter:
    """快照创建——文件 + SQLite。"""

    def test_snapshot_file_creates_copy(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
            f.write(b'{"key":"value"}')
            source = f.name
        try:
            s = Snapshotter(backup_dir=tempfile.mkdtemp())
            meta = s.snapshot_file(source, db_type="checkpoint")
            assert meta.size_bytes > 0
            assert len(meta.integrity_hash) == 64
            assert os.path.exists(meta.path)
        finally:
            os.unlink(source)

    def test_snapshot_sqlite_creates_valid_copy(self) -> None:
        import sqlite3

        tmpdir = tempfile.mkdtemp()
        source = os.path.join(tmpdir, "test.db")
        # 创建 SQLite 测试文件
        conn = sqlite3.connect(source)
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO test VALUES (1, 'backup_test')")
        conn.commit()
        conn.close()

        try:
            s = Snapshotter(backup_dir=tmpdir)
            meta = s.snapshot_sqlite(source, db_type="knowledge")
            assert meta.size_bytes > 0
            assert meta.db_type == "knowledge"
            # 验证快照是有效的 SQLite 数据库
            conn2 = sqlite3.connect(meta.path)
            row = conn2.execute("SELECT name FROM test WHERE id=1").fetchone()
            assert row is not None
            assert row[0] == "backup_test"
            conn2.close()
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_snapshot_has_correct_metadata(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"metadata test")
            source = f.name
        try:
            s = Snapshotter(backup_dir=tempfile.mkdtemp())
            meta = s.snapshot_file(source, db_type="config")
            assert meta.db_type == "config"
            assert meta.created_at > 0
            d = meta.to_dict()
            assert "snapshot_id" in d
            assert "integrity_hash" in d
        finally:
            os.unlink(source)


# ── Restorer ─────────────────────────────────────────────


class TestRestorer:
    """快照恢复——完整流程。"""

    def test_restore_success(self) -> None:
        tmpdir = tempfile.mkdtemp()
        # 创建源文件
        source = os.path.join(tmpdir, "source.txt")
        with open(source, "w") as f:
            f.write("original content for restore test")

        # 创建快照
        s = Snapshotter(backup_dir=tmpdir)
        meta = s.snapshot_file(source, db_type="test")

        # 修改源文件
        with open(source, "w") as f:
            f.write("modified content")

        # 恢复
        r = Restorer()
        result = r.restore(meta, target_path=source)
        assert result.success is True
        assert result.integrity_ok is True
        # 验证内容已恢复
        with open(source) as f:
            assert f.read() == "original content for restore test"

    def test_restore_invalid_snapshot(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"snapshot data")
            snap_path = f.name
        target = tempfile.mktemp(suffix=".txt")
        try:
            meta = type(
                "FakeMeta",
                (),
                {
                    "snapshot_id": "fake",
                    "path": snap_path,
                    "integrity_hash": "badhash",
                    "size_bytes": 13,
                    "created_at": 1.0,
                    "db_type": "test",
                    "verified": False,
                },
            )()
            r = Restorer()
            result = r.restore(meta, target_path=target)
            assert result.success is False
            assert "SHA256" in result.reason
        finally:
            os.unlink(snap_path)

    def test_restore_creates_backup_of_existing(self) -> None:
        tmpdir = tempfile.mkdtemp()
        target = os.path.join(tmpdir, "target.db")
        snap_source = os.path.join(tmpdir, "snap.db")

        # 创建目标文件
        with open(target, "w") as f:
            f.write("existing data")
        # 创建快照
        with open(snap_source, "w") as f:
            f.write("snapshot data")
        s = Snapshotter(backup_dir=tmpdir)
        meta = s.snapshot_file(snap_source, db_type="test")

        # 恢复——原数据被快照覆盖，.backup 成功后清理（P2-2 PR#133）
        r = Restorer()
        result = r.restore(meta, target_path=target)
        assert result.success is True
        backup_path = target + ".backup"
        # P2-2: 成功恢复后清理 .backup——不残留临时文件
        assert not os.path.exists(backup_path)
        # 验证目标文件已是快照数据
        with open(target) as f:
            assert f.read() == "snapshot data"

    def test_end_to_end_snapshot_verify_restore(self) -> None:
        """全流程闭环: 创建快照 → 验证 → 修改 → 恢复 → 验证。"""
        import sqlite3

        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "original.db")

        # 创建数据库
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE data (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO data VALUES (1, 'before')")
        conn.commit()
        conn.close()

        # 快照
        s = Snapshotter(backup_dir=tmpdir)
        meta = s.snapshot_sqlite(db_path, db_type="e2e_test")

        # 验证完整性
        assert verify_integrity(meta.path, meta.integrity_hash) is True

        # 修改数据
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE data SET value='after' WHERE id=1")
        conn.commit()
        conn.close()

        # 恢复
        r = Restorer()
        result = r.restore(meta, target_path=db_path)
        assert result.success is True

        # 验证恢复后数据
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT value FROM data WHERE id=1").fetchone()
        assert row is not None
        assert row[0] == "before"
        conn.close()
