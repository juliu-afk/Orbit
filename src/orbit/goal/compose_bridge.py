"""GoalComposeBridge——Goal 模式 → ComposeOrchestrator 桥接。

职责:
1. 首轮: Goal.description → LLM 生成 Spec → ComposeParser → TaskDAG
2. 后续轮: 过滤已完成的子任务 → 生成下一轮 Spec

WHY 桥接而非直接调用: Goal 模式需要自动 Spec 生成（用户不给 Spec），
而 ComposeOrchestrator 假设 Spec 已经存在。桥接层负责转换。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from orbit.compose.models import Spec, Task
    from orbit.gateway.client import LLMClient

logger = structlog.get_logger("orbit.goal")

# Spec 生成 prompt——LLM 将自然语言目标拆解为结构化 Spec
SPEC_GENERATION_PROMPT = """将以下开发目标拆解为结构化的子任务列表。

要求:
1. 每个子任务独立可执行、可验证
2. 子任务间依赖关系明确（depends_on 用 task id）
3. 每个子任务指定合适的 agent_role: developer | architect | reviewer | qa
4. 子任务描述具体——包含文件路径、函数名等细节
5. 不要拆得太碎——每个子任务至少有一定工作量

目标:
{description}

约束条件:
{constraints}

输出 JSON 格式（仅 JSON，不要其他文本）:
{{
  "title": "目标标题",
  "description": "目标描述",
  "tasks": [
    {{
      "id": "task-1",
      "description": "具体任务描述",
      "agent_role": "developer",
      "depends_on": []
    }},
    ...
  ]
}}"""


class GoalComposeBridge:
    """Goal→Compose 桥接层。

    Usage:
        bridge = GoalComposeBridge(llm_client)
        spec = await bridge.generate_spec(goal)
        # spec 可直接传给 ComposeParser → ComposeOrchestrator
    """

    def __init__(self, llm: Any = None) -> None:  # LLMClient
        self._llm = llm

    async def generate_spec(self, goal: Any) -> Any:  # GoalSession → Spec
        """首轮：LLM 自动生成 Spec。

        WHY LLM 生成: 用户输入是自然语言（如"实现认证模块"），
        需 LLM 拆解为结构化 tasks。
        """
        if not self._llm:
            logger.info("compose_bridge_mock_mode")
            return self._mock_spec(goal)

        constraints_text = "\n".join(f"- {c}" for c in getattr(goal, "constraints", []))
        prompt = SPEC_GENERATION_PROMPT.format(
            description=getattr(goal, "description", str(goal)),
            constraints=constraints_text or "无",
        )

        try:
            from orbit.gateway.schemas import LLMRequest

            req = LLMRequest(
                prompt=prompt,
                system_prompt="你是任务拆解专家——将开发目标拆解为结构化子任务列表。",
                temperature=0.3,
                max_tokens=2000,
            )
            response = await self._llm.generate(req, task_id="spec_gen")
            spec = self._parse_spec_response(response.content or "", goal)
            if spec:
                return spec
        except Exception as e:
            logger.warning("spec_generation_failed_fallback_mock", error=str(e))

        return self._mock_spec(goal)

    def filter_pending_tasks(self, spec: Any, progress: dict[str, str]) -> Any:
        """过滤已完成的子任务——生成下一轮 Spec。

        WHY: 避免 Agent 重复执行已完成的任务。
        """
        from orbit.compose.models import Spec, Task

        if isinstance(spec, dict):
            tasks_dicts = spec.get("tasks", [])
            pending = [t for t in tasks_dicts if progress.get(t.get("id", "")) != "done"]
            return {**spec, "tasks": pending}
        elif hasattr(spec, "tasks"):
            pending = [t for t in spec.tasks if progress.get(t.id) != "done"]
            return Spec(
                title=spec.title,
                description=spec.description,
                tasks=pending,
                constraints=spec.constraints if hasattr(spec, "constraints") else [],
            )
        return spec

    # ── 内部 ──────────────────────────────────────────

    def _parse_spec_response(self, content: str, goal: Any) -> Any | None:
        """解析 LLM Spec 响应。"""
        import json

        try:
            clean = content.strip()
            if clean.startswith("```"):
                clean = clean.strip("`")
                if clean.startswith("json"):
                    clean = clean[4:]
            data = json.loads(clean)

            from orbit.compose.models import Spec, Task

            tasks = [
                Task(
                    id=t.get("id", f"task-{i}"),
                    description=t.get("description", ""),
                    agent_role=t.get("agent_role", "developer"),
                    depends_on=t.get("depends_on", []),
                )
                for i, t in enumerate(data.get("tasks", []))
            ]
            return Spec(
                title=data.get("title", getattr(goal, "description", str(goal))[:50]),
                description=data.get("description", ""),
                tasks=tasks,
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("spec_parse_failed", content=content[:200], error=str(e))
            return None

    def _mock_spec(self, goal: Any) -> Any:
        """Mock Spec——无 LLM 时的回退。"""
        from orbit.compose.models import Spec, Task

        desc = getattr(goal, "description", str(goal))
        return Spec(
            title=desc[:50],
            description=desc,
            tasks=[
                Task(
                    id="task-0",
                    description=desc,
                    agent_role="developer",
                    depends_on=[],
                )
            ],
        )
