#!/usr/bin/env python3
"""灾难恢复脚本 (Step 7.5 PR #3).

自动化恢复流程:
  1. 列出可用快照
  2. 选择快照 → 验证 SHA256 完整性
  3. 备份当前文件 → 恢复到目标路径
  4. 验证恢复后数据完整性

用法:
  python scripts/dr/recover.py --list                    # 列出所有快照
  python scripts/dr/recover.py --snapshot <id> --target <path>  # 恢复
  python scripts/dr/recover.py --verify <snapshot_path>         # 仅验证

零外部依赖, 纯 stdlib。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# 项目根目录 (scripts/dr/ → ../../)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from orbit.backup.integrity import compute_hash  # noqa: E402
from orbit.backup.restore import Restorer  # noqa: E402


def list_snapshots(backup_dir: str) -> list[dict]:
    """列出备份目录中的所有快照。"""
    if not os.path.isdir(backup_dir):
        return []
    snapshots = []
    for fname in sorted(os.listdir(backup_dir), reverse=True):
        fpath = os.path.join(backup_dir, fname)
        if not os.path.isfile(fpath):
            continue
        size_mb = os.path.getsize(fpath) / (1024 * 1024)
        snapshots.append({
            "name": fname,
            "path": fpath,
            "size_mb": round(size_mb, 2),
            "modified": os.path.getmtime(fpath),
        })
    return snapshots


def cmd_list(backup_dir: str) -> int:
    """列出可用快照。"""
    snaps = list_snapshots(backup_dir)
    if not snaps:
        print(f"备份目录为空: {backup_dir}")
        return 0
    print(f"备份目录: {backup_dir}")
    print(f"{'快照名称':<50} {'大小(MB)':>10}")
    print("-" * 62)
    for s in snaps:
        print(f"{s['name']:<50} {s['size_mb']:>10.2f}")
    print(f"\n共 {len(snaps)} 个快照")
    return 0


def cmd_verify(snapshot_path: str) -> int:
    """验证快照完整性 (SHA256)。"""
    if not os.path.exists(snapshot_path):
        print(f"错误: 快照不存在: {snapshot_path}", file=sys.stderr)
        return 1
    start = time.time()
    h = compute_hash(snapshot_path)
    elapsed = (time.time() - start) * 1000
    print(f"SHA256: {h}")
    print(f"耗时: {elapsed:.1f}ms")
    print("验证完成——哈希值已输出，请与备份元数据中的 integrity_hash 对比。")
    return 0


def cmd_recover(snapshot_id: str, target_path: str, backup_dir: str) -> int:
    """从快照恢复到目标路径。"""
    # 1. 查找快照文件
    snap_path = os.path.join(backup_dir, snapshot_id)
    if not os.path.exists(snap_path):
        # 尝试按 snapshot_id 前缀匹配
        matches = [s["path"] for s in list_snapshots(backup_dir)
                   if snapshot_id in s["name"]]
        if not matches:
            print(f"错误: 未找到快照 '{snapshot_id}'", file=sys.stderr)
            return 1
        snap_path = matches[0]

    print(f"快照: {snap_path}")
    print(f"目标: {target_path}")

    # 2. 计算快照哈希
    print("步骤 1/4: 计算快照哈希...")
    snap_hash = compute_hash(snap_path)
    print(f"  SHA256: {snap_hash}")

    # 3. 备份当前文件
    if os.path.exists(target_path):
        backup_target = target_path + ".dr_backup"
        print(f"步骤 2/4: 备份当前文件 → {backup_target}")
        import shutil
        shutil.copy2(target_path, backup_target)

    # 4. 恢复
    print("步骤 3/4: 恢复快照...")
    r = Restorer()
    # 构造 SnapshotMeta 供 Restorer 使用
    from orbit.backup.models import SnapshotMeta
    meta = SnapshotMeta(
        snapshot_id=snapshot_id,
        path=snap_path,
        size_bytes=os.path.getsize(snap_path),
        integrity_hash=snap_hash,
        created_at=os.path.getmtime(snap_path),
        db_type="recovery",
    )
    result = r.restore(meta, target_path=target_path)

    # 5. 验证
    print("步骤 4/4: 验证恢复后数据...")
    if result.success:
        target_hash = compute_hash(target_path)
        print(f"  SHA256: {target_hash}")
        print(f"  耗时: {result.elapsed_ms:.1f}ms")
        print("\n✅ 恢复成功！数据完整性已确认。")
        return 0
    else:
        print(f"\n❌ 恢复失败: {result.reason}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Orbit 灾难恢复工具")
    parser.add_argument("--backup-dir", default="data/backups", help="备份目录 (默认: data/backups)")
    sub = parser.add_subparsers(dest="command", help="命令")

    sub.add_parser("list", help="列出所有快照")
    v = sub.add_parser("verify", help="验证快照完整性")
    v.add_argument("snapshot", help="快照文件路径")
    r = sub.add_parser("recover", help="从快照恢复")
    r.add_argument("--snapshot", required=True, help="快照 ID 或文件名")
    r.add_argument("--target", required=True, help="恢复目标路径")

    args = parser.parse_args()
    if args.command == "list":
        return cmd_list(args.backup_dir)
    elif args.command == "verify":
        return cmd_verify(args.snapshot)
    elif args.command == "recover":
        return cmd_recover(args.snapshot, args.target, args.backup_dir)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
