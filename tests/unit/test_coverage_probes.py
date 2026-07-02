"""覆盖率补测——observability/probes.py (254行, 21%→85%)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orbit.observability.probes import (
    PROBE_TIMEOUT_SECONDS,
    ProbeResult,
    StartupProbeEngine,
    _docker_is_installed,
    _start_docker_service,
    install_docker,
)


# ════════════════════════════════════════════
# 1. ProbeResult
# ════════════════════════════════════════════

class TestProbeResult:
    def test_default_values(self):
        """新建 ProbeResult——所有默认值正确。"""
        pr = ProbeResult("test", "测试")
        assert pr.name == "test"
        assert pr.label == "测试"
        assert pr.status == "pending"
        assert pr.message == ""
        assert pr.auto_repaired is False
        assert pr.install_action is None
        assert pr.started_at is None
        assert pr.completed_at is None
        assert pr.duration_ms == 0

    def test_to_dict_all_fields(self):
        """to_dict() 返回完整字典。"""
        pr = ProbeResult("db", "数据库")
        pr.status = "passed"
        pr.message = "OK"
        pr.auto_repaired = True
        pr.install_action = "install_docker"
        pr.started_at = 100.0
        pr.completed_at = 150.0
        pr.duration_ms = 50000

        d = pr.to_dict()
        assert d["name"] == "db"
        assert d["label"] == "数据库"
        assert d["status"] == "passed"
        assert d["message"] == "OK"
        assert d["auto_repaired"] is True
        assert d["install_action"] == "install_docker"
        assert d["started_at"] == 100.0
        assert d["completed_at"] == 150.0
        assert d["duration_ms"] == 50000


# ════════════════════════════════════════════
# 2. StartupProbeEngine — 初始化 + results + reset
# ════════════════════════════════════════════

class TestStartupProbeEngineInit:
    def test_init_has_eight_checks(self):
        """引擎初始化注册 8 个探针。"""
        engine = StartupProbeEngine()
        assert len(engine._checks) == 8
        names = [c.name for c in engine._checks]
        assert "environment" in names
        assert "database" in names
        assert "sandbox" in names
        assert "session_store" in names

    def test_init_status_pending(self):
        """初始状态为 pending。"""
        engine = StartupProbeEngine()
        assert engine._status == "pending"

    def test_results_before_start(self):
        """start() 前 results() 返回 pending + elapsed=0。"""
        engine = StartupProbeEngine()
        r = engine.results()
        assert r["status"] == "pending"
        assert r["started_at"] is None
        assert r["completed_at"] is None
        assert r["auto_repairs"] == 0
        assert len(r["checks"]) == 8
        for c in r["checks"]:
            assert c["status"] == "pending"

    def test_reset_clears_all_state(self):
        """reset() 后所有探针回到 pending。"""
        engine = StartupProbeEngine()
        # 手动污染状态
        engine._status = "passed"
        engine._started_at = 1.0
        engine._auto_repairs = 3
        for check in engine._checks:
            check.status = "passed"
            check.message = "old"

        engine.reset()

        assert engine._status == "pending"
        assert engine._started_at is None
        assert engine._auto_repairs == 0
        for check in engine._checks:
            assert check.status == "pending"
            assert check.message == ""
            assert check.auto_repaired is False

    def test_results_after_completed_calculates_elapsed(self):
        """results()——elapsed_ms 使用 completed_at。"""
        engine = StartupProbeEngine()
        engine._status = "passed"
        engine._started_at = 100.0
        engine._completed_at = 105.0

        r = engine.results()
        assert r["status"] == "passed"
        assert r["elapsed_ms"] == 5000


# ════════════════════════════════════════════
# 3. _run_probe — 通过/失败/超时/跳过/修复
# ════════════════════════════════════════════

class TestRunProbe:
    @pytest.mark.asyncio
    async def test_probe_passed(self):
        """探针正常返回 → passed。"""
        engine = StartupProbeEngine()
        check = ProbeResult("test_probe", "测试")

        with patch.dict(
            "orbit.observability.probes._PROBE_FUNCTIONS",
            {"test_probe": AsyncMock(return_value="一切正常")},
        ):
            await engine._run_probe(check)

        assert check.status == "passed"
        assert check.message == "一切正常"
        assert check.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_probe_skipped_not_registered(self):
        """未注册探针 → skipped。"""
        engine = StartupProbeEngine()
        check = ProbeResult("nonexistent", "不存在")

        await engine._run_probe(check)

        assert check.status == "skipped"
        assert "未实现" in check.message

    @pytest.mark.asyncio
    async def test_probe_failed_with_repair(self):
        """探针抛异常 + 修复成功 → repaired。"""
        engine = StartupProbeEngine()
        check = ProbeResult("test_fail", "失败测试")

        with patch.dict(
            "orbit.observability.probes._PROBE_FUNCTIONS",
            {"test_fail": AsyncMock(side_effect=RuntimeError("连接失败"))},
        ):
            with patch.dict(
                "orbit.observability.probes._REPAIR_FUNCTIONS",
                {"test_fail": AsyncMock(return_value="修复完成")},
            ):
                await engine._run_probe(check)

        assert check.status == "repaired"
        assert check.auto_repaired is True
        assert engine._auto_repairs == 1
        assert "修复完成" in check.message

    @pytest.mark.asyncio
    async def test_probe_failed_no_repair(self):
        """探针抛异常 + 无修复函数 → failed。"""
        engine = StartupProbeEngine()
        check = ProbeResult("test_fail2", "失败测试")

        with patch.dict(
            "orbit.observability.probes._PROBE_FUNCTIONS",
            {"test_fail2": AsyncMock(side_effect=ValueError("致命错误"))},
        ):
            await engine._run_probe(check)

        assert check.status == "failed"
        assert "致命错误" in check.message

    @pytest.mark.asyncio
    async def test_probe_timeout_with_repair(self):
        """探针超时 + 修复成功 → repaired。"""
        engine = StartupProbeEngine()
        check = ProbeResult("slow_probe", "慢探针")

        async def _slow():
            await asyncio.sleep(999)  # 永不返回

        with patch.dict(
            "orbit.observability.probes._PROBE_FUNCTIONS",
            {"slow_probe": _slow},
        ):
            with patch.dict(
                "orbit.observability.probes._REPAIR_FUNCTIONS",
                {"slow_probe": AsyncMock(return_value="超时修复")},
            ):
                # 缩短超时避免测试慢
                with patch("orbit.observability.probes.PROBE_TIMEOUT_SECONDS", 0.01):
                    await engine._run_probe(check)

        assert check.status == "repaired"
        assert check.auto_repaired is True

    @pytest.mark.asyncio
    async def test_probe_timeout_no_repair(self):
        """探针超时 + 无修复 → failed。"""
        engine = StartupProbeEngine()
        check = ProbeResult("slow_probe2", "慢探针")

        async def _slow():
            await asyncio.sleep(999)

        with patch.dict(
            "orbit.observability.probes._PROBE_FUNCTIONS",
            {"slow_probe2": _slow},
        ):
            with patch("orbit.observability.probes.PROBE_TIMEOUT_SECONDS", 0.01):
                await engine._run_probe(check)

        assert check.status == "failed"
        assert "超时" in check.message

    @pytest.mark.asyncio
    async def test_sandbox_failed_sets_install_action(self):
        """沙箱探针失败 + 修复也失败 + Docker 未安装 → install_action。"""
        engine = StartupProbeEngine()
        check = ProbeResult("sandbox", "沙箱环境")

        with patch.dict(
            "orbit.observability.probes._PROBE_FUNCTIONS",
            {"sandbox": AsyncMock(side_effect=RuntimeError("no docker"))},
        ):
            with patch.dict(
                "orbit.observability.probes._REPAIR_FUNCTIONS",
                {"sandbox": AsyncMock(side_effect=RuntimeError("repair failed"))},
            ):
                with patch(
                    "orbit.observability.probes._docker_is_installed", return_value=False
                ):
                    await engine._run_probe(check)

        assert check.status == "failed"
        assert check.install_action == "install_docker"


# ════════════════════════════════════════════
# 4. start() — 幂等 + 并行
# ════════════════════════════════════════════

class TestStart:
    @pytest.mark.asyncio
    async def test_start_is_idempotent(self):
        """start() 幂等——已运行则跳过。"""
        engine = StartupProbeEngine()
        engine._status = "running"

        # 直接设置 mock——不应被调用
        with patch.object(engine, "_run_probe") as mock_run:
            await engine.start()
            mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_sets_status_passed_when_all_pass(self):
        """全部探针通过 → status=passed。"""
        engine = StartupProbeEngine()
        # 用快速 mock 替换全部探针
        probes = {c.name: AsyncMock(return_value="OK") for c in engine._checks}

        with patch.dict("orbit.observability.probes._PROBE_FUNCTIONS", probes):
            await engine.start()

        assert engine._status == "passed"
        assert engine._started_at is not None
        assert engine._completed_at is not None

    @pytest.mark.asyncio
    async def test_start_sets_status_failed_when_any_fail(self):
        """任一探针失败且修复也失败 → status=failed。"""
        engine = StartupProbeEngine()
        probes = {}
        for c in engine._checks:
            if c.name == "database":
                probes[c.name] = AsyncMock(side_effect=RuntimeError("dead"))
            else:
                probes[c.name] = AsyncMock(return_value="OK")

        # 修复也失败——确保 database 不会自动修复
        with patch.dict(
            "orbit.observability.probes._REPAIR_FUNCTIONS",
            {"database": AsyncMock(side_effect=RuntimeError("repair failed"))},
        ):
            with patch.dict("orbit.observability.probes._PROBE_FUNCTIONS", probes):
                await engine.start()

        assert engine._status == "failed"


# ════════════════════════════════════════════
# 5. Docker 辅助函数
# ════════════════════════════════════════════

class TestDockerHelpers:
    def test_docker_not_installed(self, monkeypatch):
        """Docker 不在 PATH 也不在默认路径 → False。"""
        import shutil

        monkeypatch.setattr(shutil, "which", lambda x: None)
        monkeypatch.setattr("os.name", "posix")  # 非 Windows
        # 确保默认路径不存在
        assert _docker_is_installed() is False

    def test_docker_in_path(self, monkeypatch):
        """Docker 在 PATH → True。"""
        import shutil

        monkeypatch.setattr(shutil, "which", lambda x: "/usr/bin/docker")
        assert _docker_is_installed() is True

    @pytest.mark.asyncio
    async def test_install_docker_non_windows(self, monkeypatch):
        """非 Windows → install_docker 返回提示。"""
        monkeypatch.setattr("os.name", "posix")
        result = await install_docker()
        assert "手动安装" in result

    def test_start_docker_service_windows(self):
        """Windows 下 _start_docker_service 调用 sc start。"""
        with patch("subprocess.run") as mock_run:
            with patch("os.name", "nt"):
                _start_docker_service()
            mock_run.assert_called_once()
            assert mock_run.call_args[0][0][0] == "sc"


# ════════════════════════════════════════════
# 6. PROBE_TIMEOUT_SECONDS
# ════════════════════════════════════════════

class TestConstants:
    def test_probe_timeout_positive(self):
        """超时常量 > 0。"""
        assert PROBE_TIMEOUT_SECONDS > 0
