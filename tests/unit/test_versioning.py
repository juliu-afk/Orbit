"""Step 7.4/7.5 PR #2——版本注册表单元测试。

覆盖: VersionRegistry / 版本管理 / 迁移追踪 / 发布审计
"""

import tempfile
from pathlib import Path

import pytest

from orbit.versioning.registry import VersionRegistry


@pytest.fixture
def reg():
    """每个测试独立的 VersionRegistry——临时 SQLite 文件，避免跨测试状态泄漏。"""
    tmpdir = tempfile.mkdtemp(prefix="orbit_test_versioning_")
    db_path = Path(tmpdir) / "versioning.db"
    r = VersionRegistry(db_path=str(db_path))
    yield r
    r.close()
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


class TestVersionRegistry:
    """版本注册表——CRUD + 查询。"""

    def test_install_and_current_version(self, reg) -> None:
        reg.install_version("v0.15.0", "新增备份管理器")
        assert reg.current_version() == "v0.15.0"

    def test_install_replaces_active(self, reg) -> None:
        reg.install_version("v0.14.0")
        reg.install_version("v0.15.0")
        assert reg.current_version() == "v0.15.0"
        versions = reg.list_versions()
        assert len(versions) == 2
        v14 = [v for v in versions if v.version == "v0.14.0"][0]
        assert v14.is_active is False

    def test_list_versions_order_desc(self, reg) -> None:
        reg.install_version("v0.1.0")
        reg.install_version("v0.2.0")
        reg.install_version("v0.3.0")
        versions = reg.list_versions()
        assert versions[0].version == "v0.3.0"


class TestMigrationTracking:
    """Schema 迁移追踪。"""

    def test_record_and_check_migration(self, reg) -> None:
        reg.record_migration("V001__init", "v0.1.0", checksum="abc123")
        assert reg.is_migration_applied("V001__init") is True
        assert reg.is_migration_applied("V999__nonexistent") is False

    def test_failed_migration_not_applied(self, reg) -> None:
        reg.record_migration("V002__fail", "v0.2.0", success=False, error_message="OOM")
        assert reg.is_migration_applied("V002__fail") is False

    def test_list_migrations(self, reg) -> None:
        reg.record_migration("V001", "v0.1.0")
        reg.record_migration("V002", "v0.2.0")
        migrations = reg.list_migrations()
        assert len(migrations) == 2
        assert migrations[0].migration_id == "V001"
        assert migrations[1].migration_id == "V002"


class TestReleaseAudit:
    """发布审计事件。"""

    def test_record_release_deploy(self, reg) -> None:
        reg.record_release("deploy", "v0.15.0", previous_version="v0.14.0", trigger="manual")
        last = reg.last_release()
        assert last is not None
        assert last.event_type == "deploy"
        assert last.version == "v0.15.0"
        assert last.trigger == "manual"

    def test_record_release_rollback(self, reg) -> None:
        reg.record_release(
            "rollback",
            "v0.14.0",
            previous_version="v0.15.0",
            trigger="auto_slo",
            success=True,
            details="错误率>5%触发自动回滚",
        )
        last = reg.last_release()
        assert last is not None
        assert last.event_type == "rollback"
        assert last.trigger == "auto_slo"
        assert "错误率" in last.details

    def test_list_releases(self, reg) -> None:
        reg.record_release("deploy", "v0.1.0")
        reg.record_release("deploy", "v0.2.0")
        reg.record_release("rollback", "v0.1.0")
        events = reg.list_releases()
        assert len(events) == 3

    def test_canary_events(self, reg) -> None:
        reg.record_release("canary_start", "v0.15.0", traffic_ratio=0.01)
        reg.record_release("canary_end", "v0.15.0", traffic_ratio=1.0)
        events = reg.list_releases()
        assert events[0].event_type == "canary_end"
        assert events[1].event_type == "canary_start"
        assert events[1].traffic_ratio == 0.01
