"""PR3 备份/版本 API 集成测试。

每个测试独立，不依赖模块级 VersionRegistry 单例的跨测试状态。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orbit.api.main import create_app


@pytest.fixture
def client():
    """每个测试独立 client。"""
    with TestClient(create_app()) as c:
        yield c


class TestBackupAPI:
    """备份管理 API。"""

    def test_list_snapshots_empty(self, client) -> None:
        """列出快照（空列表也正常）。"""
        r = client.get("/api/v1/backup/snapshots")
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == 0
        assert isinstance(data["data"], list)

    def test_create_snapshot_not_found(self, client) -> None:
        """源文件不存在 → 404。"""
        r = client.post(
            "/api/v1/backup/snapshots",
            json={"source_path": "/nonexistent/db.sqlite", "db_type": "sqlite"},
        )
        assert r.status_code == 404

    def test_list_snapshots_with_type_filter(self, client) -> None:
        """按类型过滤。"""
        r = client.get("/api/v1/backup/snapshots?db_type=knowledge")
        assert r.status_code == 200
        assert r.json()["code"] == 0


class TestVersioningAPI:
    """版本管理 API。"""

    def test_current_version(self, client) -> None:
        """获取当前版本。"""
        r = client.get("/api/v1/versioning/current")
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == 0
        assert "version" in data["data"]

    def test_install_then_current(self, client) -> None:
        """安装版本 → 当前版本变为该版本（同一 client 内验证）。"""
        r = client.post(
            "/api/v1/versioning/install",
            json={"version": "v-pr3-test", "description": "pr3 test"},
        )
        assert r.status_code == 200
        assert r.json()["code"] == 0

        r2 = client.get("/api/v1/versioning/current")
        assert r2.status_code == 200
        assert r2.json()["data"]["version"] == "v-pr3-test"

    def test_list_versions(self, client) -> None:
        """版本列表可访问。"""
        r = client.get("/api/v1/versioning/versions")
        assert r.status_code == 200
        assert r.json()["code"] == 0

    def test_list_releases(self, client) -> None:
        """发布事件时间线。"""
        r = client.get("/api/v1/versioning/releases")
        assert r.status_code == 200
        assert r.json()["code"] == 0


class TestSnapshotterListSnapshots:
    """Snapshotter.list_snapshots 单元测试。"""

    def test_list_returns_list(self) -> None:
        """list_snapshots 返回 list（即使空）。"""
        from orbit.backup.snapshot import Snapshotter

        s = Snapshotter()
        result = s.list_snapshots()
        assert isinstance(result, list)
