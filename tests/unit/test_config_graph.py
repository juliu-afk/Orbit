"""Step 3.3 配置图谱引擎测试。

覆盖：
- compute_hash（5 种格式）
- scan_and_index
- detect_drift
- auto_fix（Test 环境修复 + Prod 禁止）
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from orbit.graph.engines.config_graph import (
    ConfigGraphEngine,
    ConfigGraphError,
    ParseConfigError,
)
from orbit.graph.models.nodes import Base


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def config_engine(session_factory, tmp_path):
    return ConfigGraphEngine(
        session_factory=session_factory,
        base_dir=str(tmp_path),
        env="test",
        backup_dir=str(tmp_path / ".backups"),
    )


def test_compute_hash_env(config_engine, tmp_path):
    """SC3: .env 文件 hash 计算。"""
    f = tmp_path / ".env"
    f.write_text("DB_PORT=5432\n", encoding="utf-8")
    h = config_engine.compute_hash(f)
    assert len(h) == 64  # SHA256


def test_compute_hash_yaml(config_engine, tmp_path):
    """YAML 文件 hash 计算。"""
    f = tmp_path / "config.yml"
    f.write_text("port: 5432\nhost: localhost\n", encoding="utf-8")
    h = config_engine.compute_hash(f)
    assert len(h) == 64


def test_compute_hash_json(config_engine, tmp_path):
    """JSON 文件 hash 计算。"""
    f = tmp_path / "app.json"
    f.write_text('{"port": 5432}', encoding="utf-8")
    h = config_engine.compute_hash(f)
    assert len(h) == 64


def test_compute_hash_nginx(config_engine, tmp_path):
    """nginx.conf hash 计算。"""
    f = tmp_path / "nginx.conf"
    f.write_text("server { listen 80; }", encoding="utf-8")
    h = config_engine.compute_hash(f)
    assert len(h) == 64


def test_compute_hash_ini(config_engine, tmp_path):
    """ini 文件 hash 计算。"""
    f = tmp_path / "php.ini"
    f.write_text("[PHP]\nmemory_limit=128M\n", encoding="utf-8")
    h = config_engine.compute_hash(f)
    assert len(h) == 64


def test_hash_deterministic(config_engine, tmp_path):
    """相同内容（不同格式）hash 相同。"""
    f1 = tmp_path / "a.yml"
    f1.write_text("port: 5432\nhost: localhost\n", encoding="utf-8")
    f2 = tmp_path / "b.yml"
    f2.write_text("host: localhost\nport: 5432\n", encoding="utf-8")  # 顺序不同
    # 排序后应一致
    assert config_engine.compute_hash(f1) == config_engine.compute_hash(f2)


@pytest.mark.asyncio
async def test_scan_and_index(config_engine, tmp_path):
    """扫描目录索引配置文件。"""
    (tmp_path / ".env").write_text("DB_PORT=5432\n", encoding="utf-8")
    (tmp_path / "config.yml").write_text("port: 5432\n", encoding="utf-8")
    count = await config_engine.scan_and_index()
    assert count == 2


@pytest.mark.asyncio
async def test_scan_skips_unsupported(config_engine, tmp_path):
    """不支持格式的文件跳过。"""
    (tmp_path / ".env").write_text("X=1\n", encoding="utf-8")
    (tmp_path / "readme.txt").write_text("not config", encoding="utf-8")
    count = await config_engine.scan_and_index()
    assert count == 1


@pytest.mark.asyncio
async def test_detect_drift(config_engine, tmp_path):
    """SC1: 修改配置后检测到漂移。"""
    f = tmp_path / ".env"
    f.write_text("DB_PORT=5432\n", encoding="utf-8")
    await config_engine.scan_and_index()
    # 修改文件
    f.write_text("DB_PORT=5433\n", encoding="utf-8")
    drifts = await config_engine.detect_drift()
    assert len(drifts) == 1
    assert ".env" in drifts[0]["file"]


@pytest.mark.asyncio
async def test_detect_no_drift(config_engine, tmp_path):
    """无变更时无漂移。"""
    f = tmp_path / ".env"
    f.write_text("DB_PORT=5432\n", encoding="utf-8")
    await config_engine.scan_and_index()
    drifts = await config_engine.detect_drift()
    assert drifts == []


@pytest.mark.asyncio
async def test_auto_fix_test_env(config_engine, tmp_path):
    """SC2: Test 环境自动修复。"""
    f = tmp_path / ".env"
    f.write_text("DB_PORT=5432\n", encoding="utf-8")
    await config_engine.scan_and_index()
    # 修改
    f.write_text("DB_PORT=5433\n", encoding="utf-8")
    # 修复
    ok = await config_engine.auto_fix(str(f))
    assert ok is True
    assert "5432" in f.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_auto_fix_prod_forbidden(session_factory, tmp_path):
    """生产环境禁止自动修复。"""
    eng = ConfigGraphEngine(session_factory=session_factory, base_dir=str(tmp_path), env="prod")
    with pytest.raises(ConfigGraphError, match="禁止"):
        await eng.auto_fix(str(tmp_path / ".env"))


@pytest.mark.asyncio
async def test_auto_fix_creates_backup(config_engine, tmp_path):
    """自动修复前创建备份。"""
    f = tmp_path / ".env"
    f.write_text("DB_PORT=5432\n", encoding="utf-8")
    await config_engine.scan_and_index()
    f.write_text("DB_PORT=5433\n", encoding="utf-8")
    await config_engine.auto_fix(str(f))
    backup = tmp_path / ".backups" / ".env.bak"
    assert backup.exists()
    assert "5433" in backup.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_parse_error_skipped(config_engine, tmp_path):
    """解析失败的文件跳过，不阻断扫描。"""
    (tmp_path / ".env").write_text("DB_PORT=5432\n", encoding="utf-8")
    bad = tmp_path / "bad.yml"
    bad.write_text(": invalid yaml : :", encoding="utf-8")
    count = await config_engine.scan_and_index()
    # bad.yml 解析失败跳过，只索引 .env
    assert count == 1


def test_unsupported_file_raises(config_engine, tmp_path):
    """不支持的文件类型抛 ParseConfigError。"""
    f = tmp_path / "data.xyz"
    f.write_text("xxx", encoding="utf-8")
    with pytest.raises(ParseConfigError):
        config_engine.compute_hash(f)
