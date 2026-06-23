# PRD+ADR_Step7.4+7.5：版本升级与迁移 · 灾难恢复策略

## Step 7.4：版本升级与迁移

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | V14.1 在生产环境运行中需要持续迭代（从 V14.1 到 V15），直接全量更新生产环境 Agent 风险极高——新版本 Bug 可能影响所有用户，导致服务中断。需要完善的版本管理能力，实现零停机发布和快速回滚。 |
| **用户故事** | 作为运维工程师，我希望在发布新版本时先以小比例流量验证（金丝雀发布），并设置自动回滚条件，确保新版本问题不会影响所有用户；我希望回滚操作在 60 秒内完成，最大程度减少影响范围。 |
| **需求描述** | ① **容器化与版本标签**：所有核心组件（调度器、图谱服务、API 网关）容器化，每个版本构建独立镜像并打标签（`v14.1`、`v14.2-canary`）。<br>② **蓝绿部署**：保留旧版本（蓝）作为备份，新版本（绿）并行验证后切换流量，秒级回滚。<br>③ **金丝雀发布**：按比例（1%→5%→20%→50%→100%）或按内容（特定 User-ID、项目标签）分流验证。<br>④ **自动回滚条件**：错误率 >5%、P99 延迟 >基线×1.5、Token 消耗异常 >基线×2，触发自动回滚。<br>⑤ **数据库 Schema 迁移**：支持前滚 + 后滚，增量迁移脚本，不破坏现有数据。<br>⑥ **发布审计**：每次发布/回滚事件记录到 `task_audit_trail`（含版本号、流量比例、触发原因）。 |
| **范围 (Do/Don't)** | **Do：** 版本发布管理；蓝绿/金丝雀流量切换；自动回滚；Schema 迁移。<br>**Don't：** 不处理应用层代码缺陷（那是测试和 CI 职责）；不替代多活架构（两地三中心是更高层次设计）。 |
| **数据契约** | **ReleaseEvent:** `{"version": str, "previous_version": str, "traffic_ratio": float, "trigger": "manual\|auto", "rollback_trigger": str\|null, "timestamp": float}` |
| **异常定义** | ① **金丝雀流量异常**：即使未达到回滚阈值，也发送 WARNING 告警给运维。<br>② **Schema 迁移失败**：停止发布流程，不切换流量，要求人工介入。<br>③ **蓝绿切换超时（>60s）**：回退操作，中止发布。 |
| **成功标准→验收** | **SC1:** 金丝雀发布成功率 ≥99% → **AC1:** 100 次金丝雀发布验证，≥99 次无需人工干预完成全流程。<br>**SC2:** 回滚时间 <60s → **AC2:** 从触发回滚到流量切回旧版本 <60s（含网关路由 + 健康检查）。<br>**SC3:** Schema 迁移零数据丢失 → **AC3:** 10 次迁移测试（包含失败注入），0 次数据损坏或丢失。 |
| **待定决策** | **Q:** 金丝雀流量递增步长是固定还是自适应？ → **决议：** Phase 0 采用固定步长（1%→5%→20%→50%→100%），Phase 1 升级为自适应（根据指标自动调整步长）。 |

---

## Step 7.5：灾难恢复策略

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | V14.1 作为生产级 Agent 系统，面临硬件故障、数据中心级灾难或外部依赖（LLM API、数据库）不可用的极端场景。需要完善的灾难恢复能力，保障业务连续性，将故障影响降到最低。 |
| **用户故事** | 作为 V14.1 系统，我希望在面临灾难时能在最短时间内恢复服务，数据丢失不超过 RPO（恢复点目标），中断时间不超过 RTO（恢复时间目标）。我希望每个灾难场景都有对应的标准操作流程（SOP），让任何运维人员都能执行恢复。 |
| **需求描述** | ① **RPO/RTO 目标**：RPO ≤1 小时（审计数据），RTO ≤30 分钟（核心功能）。<br>② **多级备份**：PostgreSQL 实时备份（ WAL 连续归档）+ 图谱数据每小时快照 + 配置文件版本化（Git）。<br>③ **故障切换**：主数据中心不可用时，DNS/负载均衡器自动切换到备用数据中心。<br>④ **恢复流程文档化**：每个灾难场景（RDS 宕机、K8s 集群崩溃、LLM API 全挂）有对应 SOP，支持任何运维人员执行。<br>⑤ **定期演练**：每季度执行一次灾难恢复演练，验证备份可用性和 RTO 达标。<br>⑥ **跨区域复制**：PostgreSQL 跨区域流复制，图谱数据异地快照。 |
| **范围 (Do/Don't)** | **Do：** 多级备份；自动化故障切换；SOP 文档化；定期演练。<br>**Don't：** 不替代多活架构（两地三中心是更高层次设计）；不自动修复应用层 Bug（那是 CI/CD 和开发流程职责）。 |
| **数据契约** | **BackupMeta:** `{"type": "wal\|snapshot\|git", "timestamp": float, "location": str, "size_bytes": int, "integrity_hash": str}`<br>**DisasterEvent:** `{"scenario": str, "detected_at": float, "recovered_at": float\|null, "rpo_actual": float, "rto_actual": float, "sop_executed": str}` |
| **异常定义** | ① **备份不可用**：定期检查发现备份损坏，发送 CRITICAL 告警，立即重做备份。<br>② **RTO 超限**：实际恢复时间超过 30 分钟，触发事件复盘要求（Postmortem）。<br>③ **演练失败**：季度演练未能在 RTO 内恢复，冻结发布流程直到问题解决。 |
| **成功标准→验收** | **SC1:** RTO ≤30 分钟 → **AC1:** 模拟核心组件故障（注入故障），恢复时间 ≤30 分钟（10 次演练取最大值）。<br>**SC2:** RPO ≤1 小时 → **AC2:** 验证备份点与故障点间隔 ≤1 小时（每日检查）。<br>**SC3:** SOP 可执行性 → **AC3:** 任意运维人员（非值班）能在 RTO 内按 SOP 完成恢复（盲测验证）。 |
| **待定决策** | **Q:** 备用数据中心是冷备还是热备？ → **决议：** Phase 0 采用温热备（定时同步，非实时），Phase 1 升级为热备（实时流复制）。 |

---

## ADR：版本发布与灾难恢复架构

| ADR (架构决策记录) |  |
| --- | --- |
| **决策（版本发布）** | 采用"蓝绿部署 + 金丝雀流量切换 + APISIX 网关路由"的零停机发布方案。 |
| **理由（版本发布）** | 1. **蓝绿部署**保留旧版本，回滚代价最低（仅切网关路由，无需重新部署）。<br>2. **金丝雀**在小比例验证新版本，避免全量故障影响所有用户。<br>3. **APISIX/Traefik 网关层**实现流量控制，无需改应用代码，解耦清晰。<br>4. 自动回滚基于 SLO 指标（错误率、延迟、Token 消耗），客观且快速。 |
| **技术栈（版本发布）** | Kubernetes（容器编排）；APISIX / Traefik（流量网关）；Argo Rollouts / Flagger（渐进式交付）；PostgreSQL（Migrate 或 Flyway 进行 Schema 迁移）。 |
| **架构位置（版本发布）** | 位于 API 网关层之下、调度器之上，是流量分配的决策节点。 |
| **实施细节（版本发布）** | **蓝绿环境：** 两个独立命名空间（`v14-namespace-blue`, `v14-namespace-green`），共享 ConfigMap 和 Secret。<br>**金丝雀策略：** Argo Rollouts 定义 `analysisTemplate`，每步进后自动查询 Prometheus 指标，超过阈值则中止并回滚。<br>**Schema 迁移：** 使用 Flyway，migration 脚本按版本号命名（`V1__init.sql`, `V2__add_column.sql`），确保有序和可重复。 |
| **风险与缓解（版本发布）** | 风险：网关层成为单点。缓解：APISIX 本身集群化部署，无单点。<br>风险：数据库迁移与代码部署不匹配。缓解：严格遵循"迁移脚本先行，代码部署在后"的顺序。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **决策（灾难恢复）** | 采用"连续归档 + 每小时快照 + Git 配置版本化"的多级备份策略。 |
| **理由（灾难恢复）** | 1. **PostgreSQL WAL 连续归档**实现点时间恢复（PITR），RPO 接近零。<br>2. **图谱数据（SQLite）每小时快照**，增量备份简单可靠，适合只读场景。<br>3. **配置文件 Git 版本化**，任何误修改可秒级回退，且有审计日志。<br>4. 不依赖商业备份软件，开源可控，成本低。 |
| **技术栈（灾难恢复）** | PostgreSQL（连续归档 + pgBackRest）；S3 / MinIO（快照存储）；GitOps（ArgoCD 管理配置）；Chaos Engineering（定期演练）。 |
| **架构位置（灾难恢复）** | 位于基础设施层，被调度器和所有 Agent 依赖，是系统的最后防线。 |
| **实施细节（灾难恢复）** | **备份策略：** WAL 归档持续上传至 S3（15 分钟 RPO）；每小时快照上传至 S3；配置文件通过 ArgoCD 自动同步。<br>**恢复流程 SOP：** 1. 确认灾难类型 → 2. 启动备用数据中心 → 3. 从最新快照恢复数据库 → 4. 验证数据完整性 → 5. DNS 切换 → 6. 逐步恢复流量。<br>**演练：** 每季度 Chaos Engineering 实验，模拟各类故障，验证 SOP 可执行性和 RTO 达标。 |
| **风险与缓解（灾难恢复）** | 风险：S3 也不可用（区域级灾难）。缓解：跨区域复制快照到第二个云厂商的 S3。<br>风险：SOP 过时或执行失败。缓解：每次演练后更新 SOP，并指定备用运维人员也熟悉流程。 |
| **依赖链** | 前置：Step 7.1（灰度发布基础）；Step 2.2（检查点持久化）。<br>依赖：无（独立基础设施层）。<br>被依赖：所有 Phase 的核心组件（Step 5.1 调度器、Step 3.x 图谱等）。 |

---

### ✅ 验收测试 · pytest

```python
import pytest

class TestStep7475VersionMigrationAndDR:
    """Step 7.4 + 7.5 版本迁移 · 灾难恢复 — 验收测试"""

    # === Step 7.4 版本升级与迁移 ===

    def test_canary_deployment_success_rate(self):
        """SC1: 金丝雀发布成功率 ≥99%"""
        # 模拟100次金丝雀发布
        successes = 0
        for _ in range(100):
            result = simulate_canary_release()
            if result["completed_without_intervention"]:
                successes += 1
        rate = successes / 100
        assert rate >= 0.99, f"Canary success rate {rate:.2%} below 99%"

    def test_rollback_time(self):
        """SC2: 回滚时间 <60s"""
        start = pytest.perf_counter()
        execute_rollback()
        elapsed = pytest.perf_counter() - start
        assert elapsed < 60, f"Rollback took {elapsed:.1f}s, exceeds 60s limit"

    def test_schema_migration_safety(self):
        """SC3: Schema 迁移零数据丢失"""
        for _ in range(10):
            result = simulate_migration_with_failure_injection()
            assert result["data_loss_occurred"] is False
            assert result["integrity_check_passed"] is True

    def test_blue_green_switch(self):
        """蓝绿切换：流量从蓝切到绿，回滚后切回"""
        # 切换到绿
        switch_to_green()
        assert get_active_version() == "green"
        # 回滚到蓝
        rollback_to_blue()
        assert get_active_version() == "blue"

    def test_auto_rollback_on_slo_violation(self):
        """自动回滚：错误率超标时自动触发"""
        inject_errors(rate=0.10)  # 10% 错误率
        time.sleep(5)  # 等待指标采集
        assert was_auto_rollback_triggered() is True
        assert get_active_version() == "blue"  # 回滚到旧版本

    # === Step 7.5 灾难恢复 ===

    def test_rto_compliance(self):
        """灾难恢复 RTO ≤30分钟"""
        start = pytest.perf_counter()
        execute_dr_recovery_scenario("core_component_failure")
        elapsed = pytest.perf_counter() - start
        assert elapsed <= 30 * 60, f"RTO {elapsed/60:.1f}min exceeds 30min"

    def test_rpo_compliance(self):
        """灾难恢复 RPO ≤1小时"""
        # 验证最新备份点与当前时间差 ≤1小时
        latest_backup = get_latest_backup_timestamp()
        current_time = pytest.perf_counter()
        gap_seconds = current_time - latest_backup
        assert gap_seconds <= 3600, f"RPO gap {gap_seconds/60:.1f}min exceeds 1h"

    def test_disaster_recovery_sop_executable(self):
        """SOP 可执行性：任意运维人员能按 SOP 在 RTO 内完成恢复"""
        # 模拟非值班运维人员（盲测）
        operator = naive_operator()
        start = pytest.perf_counter()
        result = operator.execute_sop("rds_failure")
        elapsed = pytest.perf_counter() - start
        assert result["success"] is True
        assert elapsed <= 30 * 60

    def test_cross_region_snapshot_replication(self):
        """跨区域快照复制：备份在另一个区域可用"""
        snapshot = create_snapshot()
        replicate_to_secondary_region(snapshot)
        assert is_snapshot_available_in_secondary_region(snapshot) is True

    def test_backup_integrity_check(self):
        """备份完整性检查：校验哈希值匹配"""
        backup = get_latest_backup()
        assert backup["integrity_hash"] == compute_hash(backup["data"])
        assert backup["size_bytes"] > 0

    def test_failover_dns_switch(self):
        """DNS 故障切换：主数据中心不可用时自动切换"""
        make_primary_unavailable()
        time.sleep(60)  # DNS TTL 传播
        assert is_secondary_now_primary() is True
        assert is_traffic_routing_to_secondary() is True
```
