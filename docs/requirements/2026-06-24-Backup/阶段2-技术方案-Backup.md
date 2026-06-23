# 阶段2 技术方案 —— 备份管理器 (Step 7.4/7.5 PR #1)

基于 `docs/PRD+ADR_Step7.4+7.5_版本迁移与灾难恢复.md`。

## 范围

| 验收标准 | 覆盖 |
|---------|------|
| SC3: Schema 零数据丢失 (backup/restore/verify) | ✅ |
| RPO≤1h (定时快照) | ✅ |
| 备份完整性校验 (SHA256) | ✅ |

## 模块设计

```
src/orbit/backup/
├── __init__.py       # 导出
├── models.py         # SnapshotMeta/RestoreResult
├── snapshot.py       # 快照创建 (SQLite dump + 检查点)
├── integrity.py      # SHA256 校验 + 完整性验证
├── restore.py        # 从快照恢复
```

## 数据流

```
BackupManager.create_snapshot()
  ├── 检查点 → orjson dump → data/backups/checkpoint_<ts>.json
  ├── SQLite DB → sqlite3 .backup → data/backups/
  ├── SHA256 hash → SnapshotMeta 写入
  └── 返回 SnapshotMeta (含 size/hash/timestamp)

BackupManager.verify(snapshot_path)
  → 重算 SHA256 vs 存储的 hash
  → 返回 (valid: bool, reason: str)

BackupManager.restore(snapshot_path, target)
  → 覆盖目标文件
  → SHA256 验证 → RestoreResult
```

## 测试: ~8 用例

- Snapshot: 创建/大小>0/hash 存在
- Integrity: 合法快照/损坏快照检测
- Restore: 恢复+验证/错误路径处理
- 全流程: snapshot → verify → restore 闭环
