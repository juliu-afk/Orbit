"""L8 配置漂移检测测试。使用临时文件。"""

from __future__ import annotations

from pathlib import Path

import pytest

from orbit.hallucination.l8_config import L8ConfigValidator


@pytest.fixture
def config_dirs(tmp_path):
    baseline_dir = tmp_path / "baselines"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    baseline_dir.mkdir()
    return str(baseline_dir), str(config_dir)


@pytest.mark.asyncio
async def test_l8_no_drift(config_dirs):
    """无漂移 → 空报告。"""
    baseline_dir, config_dir = config_dirs
    env_file = Path(config_dir) / "app.env"
    env_file.write_text("DB_PORT=5432")
    validator = L8ConfigValidator(baseline_dir, config_dir)
    reports = await validator.scan()
    assert len(reports) == 0


@pytest.mark.asyncio
async def test_l8_drift_detected(config_dirs):
    """AC5: 配置漂移 → 检测到。"""
    baseline_dir, config_dir = config_dirs
    env_file = Path(config_dir) / "app.env"
    env_file.write_text("DB_PORT=5432")
    validator = L8ConfigValidator(baseline_dir, config_dir)
    await validator.scan()  # 创建基线
    env_file.write_text("DB_PORT=5433")
    reports = await validator.scan()
    assert len(reports) == 1
    assert "app.env" in reports[0].file_path
    assert reports[0].auto_fixed is False


@pytest.mark.asyncio
async def test_l8_empty_config_dir(config_dirs):
    """无配置文件 → 空报告。"""
    baseline_dir, config_dir = config_dirs
    validator = L8ConfigValidator(baseline_dir, config_dir)
    reports = await validator.scan()
    assert len(reports) == 0


@pytest.mark.asyncio
async def test_l8_validate_interface(config_dirs):
    """validate() 统一接口。"""
    baseline_dir, config_dir = config_dirs
    env_file = Path(config_dir) / "app.env"
    env_file.write_text("DB_PORT=5432")
    validator = L8ConfigValidator(baseline_dir, config_dir)
    result = await validator.validate()
    assert result.passed is True  # 首次创建基线
    env_file.write_text("DB_PORT=5433")
    result = await validator.validate()
    assert result.passed is False
    assert result.level.value == "l8_config"
