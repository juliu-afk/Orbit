"""ReActAgent 基类——think→act→observe 循环.

对标: OpenCode prompt.ts:1400 runLoop()
     + Claude Code while loop + tool_calls
     + Hermes conversation_loop.py:496

WHY ReAct 而非单次 LLM 调用:
  单次调用只能输出文本，不能读文件/写代码/跑测试。
  ReAct 循环让 Agent 真正干活——观察→思考→行动→验证。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.compression.budget import TokenBudgetTracker
    from orbit.compression.compressor import ContextCompressor
    from orbit.events.bus import EventBus
    from orbit.gateway.client import LLMClient
    from orbit.goal_judge.judge import GoalJudge
    from orbit.goal_judge.models import Goal
    from orbit.graph.engines.code_graph import CodeGraphEngine
    from orbit.sandbox.executor import Sandbox

import structlog

from orbit.agents.base import AgentInput, AgentOutput, AgentRole, BaseAgent
from orbit.agents.preact import PreActEngine
from orbit.agents.reflection import ReflectionEngine
from orbit.events.schemas import DashboardEvent
from orbit.gateway.schemas import LLMRequest
from orbit.memory.decision_log import DecisionLog, parse_decision_marker
from orbit.stream.cancellation import CancellationToken
from orbit.stream.events import StreamEvent, StreamEventType
from orbit.tools.registry import DoomLoopError, ToolRegistry

logger = structlog.get_logger("orbit.agents.react")

# 最大 tool call 结果长度（截断前）
MAX_RESULT_CHARS = 10000



from orbit.agents.react_agent.agent import ReActAgent
from orbit.agents.react_agent.models import IterationBudget
from orbit.agents.react_agent.utils import _truncate_output

__all__ = ["ReActAgent", "IterationBudget", "_truncate_output"]
