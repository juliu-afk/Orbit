"""Agent 执行上下文 + 结果模型 (Step 5.1/5.2 补充——MCP/A2A抽象分层).

定义三层调用规范:
  Layer 1 (系统→Agent): Orchestrator → await agent.run(context)
  Layer 2 (Agent→工具): Agent → ToolRegistry.invoke()
  Layer 3 (Agent→Agent): Agent → MessageBus.request()

TaskContext: L1-L5 五层上下文, 每次 Agent.run() 前由 Orchestrator 构建。
AgentResult: Agent 执行完成后的标准化返回。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskContext:
    """Agent 执行上下文——L1-L5 五层信息。

    L1: 协作宪法——任务约束/会计准则/安全规则
    L2: 四图谱——代码/数据库/配置/知识的查询结果
    L3: 任务状态——当前调度器状态/进度/依赖
    L4: 私有工作记忆——该 Agent 的短期记忆/中间结果
    L5: 长期记忆——知识库/教训库的历史检索结果
    """

    task_id: str
    # Step 2.3: Agent 名称 + 模型 Tier
    agent_name: str = ""
    model_tier: str = ""
    # L1: 协作宪法——高层约束 (str)
    l1: str = ""
    # L2: 四图谱事实 (代码/DB/配置/知识)
    l2: dict[str, Any] = field(default_factory=dict)
    # L3: 任务状态——当前进度
    l3: dict[str, Any] = field(default_factory=dict)
    # L4: Agent 私有工作记忆——跨步骤传递
    l4: dict[str, Any] = field(default_factory=dict)
    # L5: 长期记忆——知识检索结果
    l5: list[dict[str, Any]] = field(default_factory=list)
    # Phase 2 Token节省: 每个字符串字段硬上限——防止单字段撑爆 context window
    max_chars_per_field: int = 5000

    def to_dict(self) -> dict[str, Any]:
        raw = {
            "task_id": self.task_id,
            "l1": self.l1,
            "l2": self.l2,
            "l3": self.l3,
            "l4": self.l4,
            "l5": self.l5,
        }
        return self._truncate_all(raw)

    def _truncate_all(self, d: dict[str, Any]) -> dict[str, Any]:
        """递归截断所有字符串值到 max_chars_per_field。

        WHY: 防止大段原始数据（完整 diff、日志、代码）撑爆 context window。
        截断保留头尾——中间插入截断标记，保持可读性。
        """
        result: dict[str, Any] = {}
        limit = self.max_chars_per_field
        for k, v in d.items():
            if isinstance(v, str) and len(v) > limit:
                half = limit // 2
                cut = len(v) - limit
                result[k] = v[:half] + f"\n... [{cut} chars truncated] ...\n" + v[-half:]
            elif isinstance(v, dict):
                result[k] = self._truncate_all(v)
            elif isinstance(v, list):
                result[k] = [
                    self._truncate_all(item) if isinstance(item, dict)
                    else (item[:limit] + f"\n... [{len(item) - limit} chars truncated] ..."
                          if isinstance(item, str) and len(item) > limit else item)
                    for item in v
                ]
            else:
                result[k] = v
        return result


@dataclass
class AgentResult:
    """Agent 执行结果——标准化返回。

    output: 任意类型——Agent 可返回 dict/str/list/None
    error: 失败时记录错误信息
    duration_ms: 执行耗时
    """

    success: bool = True
    output: Any = None
    error: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }
