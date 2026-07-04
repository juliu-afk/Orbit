"""TaskModelRouter——按任务类型自动选择模型（Inkeep 借鉴 #1）。

WHY: Inkeep 三层模型配置（base/structuredOutput/summarizer）节省 40-60% token 成本。
Orbit 按 TaskType 映射模型——reasoning→Pro, structured_output→Flash, summarization→nano。

映射表默认硬编码，后续 US-5 配置面板可覆盖（YAML 文件 → ~/.orbit/config/model_routing.yaml）。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

# 默认映射——task_type → model
# WHY 三层：Inkeep 的 base/structuredOutput/summarizer 思路，适配 Orbit 模型体系
DEFAULT_TASK_MODEL_MAP: dict[str, str] = {
    "reasoning": "deepseek/deepseek-v4-pro",
    "structured_output": "deepseek/deepseek-v4-flash",
    "summarization": "openai/glm-4.7-flash",
}


class TaskType(StrEnum):
    """任务类型——对标 Inkeep 三层 model 配置。

    REASONING: 架构设计/问题分析/决策——需要最强推理能力。
    STRUCTURED_OUTPUT: JSON Schema 约束输出/代码审查/需求解析——精度要求高但推理量小。
    SUMMARIZATION: 日志摘要/代码diff摘要/长文本压缩——最便宜模型即可。
    """

    REASONING = "reasoning"
    STRUCTURED_OUTPUT = "structured_output"
    SUMMARIZATION = "summarization"


class TaskModelDecision(BaseModel):
    """TaskModelRouter 决策结果。"""

    task_type: TaskType
    model: str
    reason: str = ""


class TaskModelRouter:
    """按任务类型选择模型——纯函数，无副作用。

    用法:
        router = TaskModelRouter()
        decision = router.select(TaskType.REASONING)
        # → TaskModelDecision(task_type=REASONING, model="deepseek/deepseek-v4-pro")
    """

    def __init__(self, model_map: dict[str, str] | None = None) -> None:
        self._map = model_map or dict(DEFAULT_TASK_MODEL_MAP)

    def select(self, task_type: TaskType | str) -> TaskModelDecision:
        """按 task_type 选择模型。

        Args:
            task_type: 任务类型（reasoning/structured_output/summarization）

        Returns:
            TaskModelDecision——包含选中的模型和理由。
        """
        tt = task_type.value if isinstance(task_type, TaskType) else task_type
        model = self._map.get(tt)
        if model:
            return TaskModelDecision(
                task_type=TaskType(tt),
                model=model,
                reason=f"task_type_match_{tt}",
            )
        # 未知 task_type → 回退 Pro
        return TaskModelDecision(
            task_type=TaskType.REASONING,
            model=DEFAULT_TASK_MODEL_MAP["reasoning"],
            reason=f"unknown_task_type_{tt}_fallback_to_pro",
        )

    def update_mapping(self, task_type: str, model: str) -> None:
        """运行时更新映射（US-5 配置面板调用）。"""
        self._map[task_type] = model

    @property
    def current_mapping(self) -> dict[str, str]:
        return dict(self._map)
