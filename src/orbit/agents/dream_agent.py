"""DreamAgent——/dream 自进化 Agent (Phase 2 AC10).

继承 ReActAgent，拥有完整工具访问。
MAX_TURNS=5——dream 周期短，不需长时间循环。
"""

from __future__ import annotations

from orbit.agents.base import AgentInput, AgentOutput, AgentRole
from orbit.agents.react_agent import ReActAgent


class DreamAgent(ReActAgent):
    """/dream 自进化 Agent——定期合并去重记忆文件.

    WHY ReActAgent: 需要 read_file/grep 扫描记忆文件，
    write_file 更新 MEMORY.md。
    """

    role = AgentRole.DREAM
    MAX_TURNS = 5

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """执行 dream 循环——委托给 DreamEngine."""
        from orbit.dream.engine import DreamEngine
        from orbit.dream.models import DreamConfig
        from orbit.memory.store import MemoryStore

        project_path = input_data.context.get("project_path", "")
        memory_store = MemoryStore(project_path=project_path)
        config = DreamConfig()

        engine = DreamEngine(
            llm_client=self.llm,
            memory_store=memory_store,
            config=config,
        )
        result = await engine.run()

        return AgentOutput(
            status="ok" if result.status != "failed" else "error",
            result={
                "dream_status": result.status,
                "output_path": result.output_path,
                "lines": result.lines,
                "bytes": result.bytes,
                "errors": result.errors,
                "verification": result.verification_message,
            },
        )
