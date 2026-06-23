"""Step 7.5 PR #3——DR 恢复脚本单元测试。"""

import os
import tempfile

from scripts.dr.recover import cmd_recover, cmd_verify, list_snapshots


class TestListSnapshots:
    """快照列表功能。"""

    def test_empty_dir(self) -> None:
        snaps = list_snapshots(tempfile.mkdtemp())
        assert snaps == []

    def test_lists_files(self) -> None:
        tmp = tempfile.mkdtemp()
        Path = os.path.join
        open(Path(tmp, "knowledge_20260624T120000Z.db"), "w").close()
        open(Path(tmp, "checkpoint_20260624T110000Z.json"), "w").close()
        snaps = list_snapshots(tmp)
        assert len(snaps) == 2

    def test_order_newest_first(self) -> None:
        tmp = tempfile.mkdtemp()
        Path = os.path.join
        open(Path(tmp, "a_old.db"), "w").close()
        open(Path(tmp, "z_new.db"), "w").close()
        snaps = list_snapshots(tmp)
        assert snaps[0]["name"] == "z_new.db"


class TestCmdVerify:
    """快照完整性验证 CLI。"""

    def test_verify_valid_file(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
            f.write(b"recovery test data")
            path = f.name
        try:
            exit_code = cmd_verify(path)
            assert exit_code == 0
        finally:
            os.unlink(path)

    def test_verify_missing_file(self) -> None:
        exit_code = cmd_verify("/nonexistent/snap.db")
        assert exit_code == 1


class TestCmdRecover:
    """恢复 CLI 命令。"""

    def test_recover_success(self) -> None:
        tmp = tempfile.mkdtemp()
        # 创建快照
        snap_path = os.path.join(tmp, "test_snap.db")
        with open(snap_path, "w") as f:
            f.write("snapshot content v1")

        target = os.path.join(tmp, "target.db")
        # 创建现有目标
        with open(target, "w") as f:
            f.write("old data")

        exit_code = cmd_recover(
            snapshot_id="test_snap.db",
            target_path=target,
            backup_dir=tmp,
        )
        assert exit_code == 0
        with open(target) as f:
            assert f.read() == "snapshot content v1"
        # 验证备份文件已被创建
        assert os.path.exists(target + ".dr_backup")

    def test_recover_missing_snapshot(self) -> None:
        exit_code = cmd_recover(
            snapshot_id="nonexistent.db",
            target_path="/tmp/irrelevant",
            backup_dir="/nonexistent",
        )
        assert exit_code == 1
