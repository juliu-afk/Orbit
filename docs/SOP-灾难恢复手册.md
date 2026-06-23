# Orbit 灾难恢复标准操作流程 (SOP)

> 版本: v1.0 | 最后更新: 2026-06-24 | 演练频率: 每季度

## RPO/RTO 目标

| 指标 | 目标 | 测量方法 |
|------|------|---------|
| RPO (恢复点目标) | ≤1 小时 | 最新备份时间戳与故障时间差 |
| RTO (恢复时间目标) | ≤30 分钟 | 从故障检测到核心功能恢复 |

## 备份策略

| 类型 | 频率 | 存储位置 | 保留期 |
|------|------|---------|--------|
| SQLite 数据库快照 | 每小时 | `data/backups/` + S3 | 30 天 |
| 检查点数据 | 每次状态转换 | Redis (热) + PG (冷) | 7 天 |
| 配置文件 | Git 版本化 | GitHub + ArgoCD | 永久 |

## 灾难场景与恢复流程

### 场景 1: 数据库损坏 (SQLite/PostgreSQL)

**症状**: API 返回 500, 日志显示 "database disk image is malformed"

**恢复步骤** (预期耗时: 5 分钟):

1. **确认故障**
   ```bash
   sqlite3 data/knowledge.db "PRAGMA integrity_check"
   # 应输出 "ok"；若非 ok, 继续恢复
   ```

2. **列出可用快照**
   ```bash
   python scripts/dr/recover.py list --backup-dir data/backups
   ```

3. **验证快照完整性**
   ```bash
   python scripts/dr/recover.py verify data/backups/knowledge_<timestamp>.db
   ```

4. **执行恢复**
   ```bash
   python scripts/dr/recover.py recover \
     --snapshot knowledge_<timestamp> \
     --target data/knowledge.db
   ```

5. **验证恢复**
   ```bash
   sqlite3 data/knowledge.db "SELECT count(*) FROM concepts"
   # 确认数据行数符合预期
   ```

6. **重启服务**
   ```bash
   docker compose restart orbit
   ```

---

### 场景 2: LLM API 全挂 (DeepSeek + Qwen 不可用)

**症状**: 所有 LLM 调用返回 5xx, 熔断器全 OPEN

**恢复步骤** (预期耗时: 2 分钟):

1. **确认故障范围**
   ```bash
   curl -s http://localhost:18888/api/v1/observability/metrics | jq '.data.circuit_breaker_state'
   # 检查所有熔断器状态
   ```

2. **启用纯规则模式** (降级 L2)
   - 修改环境变量: `DEGRADATION_MODE=rule_only`
   - 重启服务: `docker compose restart orbit`

3. **通知用户**
   - 驾驶舱展示维护公告: "LLM 服务暂时不可用, 系统运行在降级模式"

4. **监控恢复**
   - 每 30 秒探测 LLM API: `curl -I https://api.deepseek.com/health`
   - API 恢复后关闭降级模式

---

### 场景 3: 配置错误导致服务不可用

**症状**: 服务启动失败, 日志显示配置解析错误

**恢复步骤** (预期耗时: 3 分钟):

1. **查看最近配置变更**
   ```bash
   git log --oneline -5 -- src/orbit/core/config.py .env.example
   ```

2. **回滚配置文件**
   ```bash
   git checkout <last_known_good_commit> -- src/orbit/core/config.py
   ```

3. **重启服务并验证**
   ```bash
   docker compose restart orbit
   curl http://localhost:18888/health
   ```

---

### 场景 4: 磁盘空间耗尽

**症状**: 写入操作失败, 日志显示 "No space left on device"

**恢复步骤** (预期耗时: 10 分钟):

1. **清理旧备份**
   ```bash
   find data/backups -name "*.db" -mtime +7 -delete
   ```

2. **清理日志**
   ```bash
   find logs/ -name "*.log" -mtime +3 -delete
   ```

3. **扩容 (如清理后仍不足)**
   - 云环境: 修改 EBS/持久卷大小
   - 物理机: 添加磁盘并迁移数据目录

---

## 演练检查清单

每次季度演练完成后填写:

| 日期 | 场景 | 执行人 | RTO 实际 | RPO 实际 | 问题 | 改进 |
|------|------|--------|---------|---------|------|------|
| | | | | | | |

## 紧急联系方式

| 角色 | 联系方式 | 升级条件 |
|------|---------|---------|
| 值班 SRE | TBD | 首次响应 |
| 技术负责人 | TBD | RTO 超过 15 分钟 |
| 产品负责人 | TBD | 影响用户 >50% |

## 备份验证命令

```bash
# 每日自动检查: 最新备份存在且大小 >0
ls -lt data/backups/ | head -5

# SHA256 完整性抽检 (每日随机抽 1 个)
python scripts/dr/recover.py verify data/backups/$(ls data/backups/ | tail -1)

# 季度全量恢复演练 (在隔离环境中)
python scripts/dr/recover.py recover \
  --snapshot <latest> \
  --target /tmp/restore_test.db
```
