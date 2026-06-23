"""Step 5.3 动态任务分片。

大任务自动拆分为子任务——Token 预估 + 边界识别 + 并发调度 + 结果合并。
"""

from orbit.sharding.engine import ShardResult, ShardStatus, TaskShardingEngine

__all__ = ["ShardResult", "ShardStatus", "TaskShardingEngine"]
