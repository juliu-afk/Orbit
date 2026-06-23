## Step 5.3：动态任务分片与降级

| PRD · 动态任务分片 |  |
| --- | --- |
| **背景** | 当用户提交的任务规模超出单次LLM调用能力范围时（如生成1000行代码、处理10000条数据），系统需要将大任务自动拆分为可管理的子任务批次，并行处理后合并结果。直接提交给LLM会导致超时、资源耗尽或输出截断。 |
| **用户故事** | 作为V14.1系统，当我接收到超大规模任务（如代码生成行数>500、数据处理>10000条记录）时，应自动触发任务分片——将大任务按逻辑边界（文件、模块、数据批次）拆分为多个子任务，通过调度器并发执行，最后合并子任务结果输出给用户。 |
| **需求描述** | ① 任务规模检测：在任务提交时，基于Token预估（输入+输出）和步骤数预估判断是否需要分片。<br>② 分片策略：支持按逻辑边界分片（文件级、函数级、数据批次级）和强制分片（Token超限）。<br>③ 子任务调度：分片后的子任务作为独立任务入队，调度器按优先级并发执行（参考Step 5.6）。<br>④ 结果合并：按原始顺序合并子任务结果，保持输出完整性。<br>⑤ 降级策略：当分片执行中某个子任务失败时：自动重试（最多3次）→ 跳过该分片继续执行 → 标记失败分片并通知用户。<br>⑥ 进度可视化：向用户展示分片进度（已完成/总数）和预估剩余时间。<br>⑦ 断点续传：支持从最后一个成功分片继续（基于检查点机制）。 |
| **范围 (Do/Don't)** | **Do：**自动检测并分片；按逻辑边界分片；子任务并发执行；结果合并。<br>**Don't：**不保证分片边界完全等同（部分边界可能存在重复处理）；不处理跨分片的分布式事务（那是应用层职责）。 |
| **数据契约** | **TaskShard:** `{ shard_id, parent_task_id, shard_index, content, token_count, status(pending/running/completed/failed), retry_count, result, started_at, completed_at }`<br>**ShardManifest:** `{ parent_task_id, total_shards, shards[], checkpoint_id, created_at }`<br>**ShardResult:** `{ shard_id, status, output, error, duration_ms }` |
| **异常定义** | `ShardExecutionError`（子任务执行失败）；`ShardTimeoutError`（子任务超时）；`MaxRetriesExceededError`（重试次数超限）；`ShardLimitExceededError`（分片数量超限）。 |
| **SC→AC** | **SC1:** 分片后输出与不分片输出一致性 ≥99% → **AC1:** 对10个已知正确答案的大任务，分片处理后结果与不分片结果内容一致率 ≥99%。<br>**SC2:** 分片失败不影响其他分片 → **AC2:** 模拟单个分片失败，其他分片仍正常完成并合并。<br>**SC3:** 进度可视化准确性 ≥90% → **AC3:** 进度预估与实际执行时间偏差 ≤10%。 |
| **待定决策** | **Q:** 分片数量上限如何设定？ → **决议：** 默认上限50个分片，超限时提示用户手动拆分或降低分片粒度。 |

---

| ADR · 分片架构决策 |  |
| --- | --- |
| **决策** | 任务分片采用**调度器统一管理 + 检查点续传 + 结果流式合并**架构，而非将分片管理下放到LLM层。 |
| **理由** | ① 调度器统一管理确保全局优先级和资源配额生效（Step 5.6的资源调度器统一视图）。<br>② 检查点机制保证分片失败后可从断点恢复，无需重头开始。<br>③ 结果流式合并避免内存峰值，适合超大规模任务。<br>④ 分片边界由系统决定，不依赖LLM的自我感知能力。 |
| **备选方案** | ① LLM自我分片（让LLM自己决定何时分片）→ LLM缺乏全局视角，分片边界不稳定 → 放弃。<br>② 固定大小分片（如每500行一个分片）→ 无法保证逻辑边界完整 → 放弃。 |
| **技术栈版本** | Python asyncio（内置）；AST分析（Python内置ast模块）；JSON Lines（内置）；复用Step 2.2检查点机制；复用Step 5.6 ResourceScheduler。 |
| **架构位置** | 分片层 `/src/sharding/task_sharding.py`（分片决策与执行）+ `/src/sharding/result_merger.py`（结果合并）+ `/src/sharding/checkpoint_manager.py`（断点管理）。 |
| **实施细节** | **分片触发条件：** 预估Token > 8192（单次LLM上下文窗口安全阈值）× 0.8，或用户显式指定。<br>**分片边界识别（代码）：** AST遍历，按函数/类/文件边界切分，优先保证边界完整。<br>**分片边界识别（数据）：** 按主键范围分片（如 ID%N），确保无重复无遗漏。<br>**失败处理：** 子任务失败写入 task_audit_trail（失败原因、分片ID、重试次数），不影响其他分片。 |
| **风险与缓解** | 风险：分片边界不完美（部分逻辑被切断）。缓解：优先按逻辑边界分片，仅在必要时强制按Token阈值切分。<br>风险：子任务数量过多导致调度开销超过收益。缓解：设置分片上限（如最多50个分片），超限时提示用户手动拆分。 |
| **依赖链** | 依赖Step 5.6（ResourceScheduler）；依赖Step 2.2（检查点持久化）；依赖Step 5.4（通信协议）。 |

---

🧪 原子化测试用例 (pytest)：

```python
import pytest, asyncio, hashlib
from src.sharding.task_sharding import TaskShardingEngine, TaskShard, ShardManifest, ShardStatus
from src.sharding.result_merger import ResultMerger
from src.scheduler.resource_scheduler import ResourceScheduler, TaskPriority, ResourceQuota

class TestStep53DynamicTaskSharding:
    """Step 5.3 动态任务分片与降级 - 验收测试"""

    def test_output_consistency(self):
        """SC1: 分片后输出一致性 ≥99%"""
        # 对10个已知正确答案的大任务，分片处理后结果与不分片结果内容一致率 ≥99%
        pass

    def test_shard_isolation(self):
        """SC2: 分片失败不影响其他分片"""
        # 模拟单个分片失败，其他分片仍正常完成并合并
        pass

    def test_progress_visibility(self):
        """SC3: 进度可视化准确性 ≥90%"""
        # 进度预估与实际执行时间偏差 ≤10%
        pass

    def test_shard_boundary_logical(self):
        """按逻辑边界（函数/文件）正确分片"""
        # AST遍历确保函数/类边界完整，不在函数中部切断
        pass

    def test_checkpoint_resume(self):
        """断点续传：最后一个成功分片恢复"""
        # 模拟第N个分片失败，恢复后从第N+1个分片继续，不重试已完成分片
        pass

    def test_result_merge_ordered(self):
        """结果按原始顺序合并"""
        # 并发执行的子任务结果，按shard_index顺序合并，保证输出顺序与输入一致
        pass

    def test_audit_integration(self):
        """分片失败事件记录到审计表"""
        # task_audit_trail正确记录shard_id、失败原因、重试次数
        pass

    def test_shard_limit_enforced(self):
        """分片数量超限时抛出ShardLimitExceededError"""
        # 超过50个分片时提示用户手动拆分
        pass

    def test_retry_before_skip(self):
        """失败处理顺序：重试→跳过→标记"""
        # 第1次失败重试，第2次失败重试，第3次失败跳过并标记
        pass

    def test_token_based_trigger(self):
        """Token预估超限时触发分片"""
        # 预估Token > 8192 × 0.8 = 6556 时自动分片
        pass
```
