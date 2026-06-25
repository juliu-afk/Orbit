"""Step 5.2 AgentFactory + 5 Agent å®ç°ã

WHY åæä»¶èé 5 æä»¶ï¼æ¯ä¸ª Agent MVP é¶æ®µæ¯è½»é Prompt å
è£
å¨ï¼
æ ¸å¿å·®å¼å¨ System Prompt åè¾åºè§£æãè¿æ©ææä»¶å¢å ç»´æ¤ææ¬ã
Step 5.x å Agent é»è¾å¤æååå¯æåã
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from orbit.agents.base import AgentInput, AgentOutput, AgentRole, BaseAgent
from orbit.agents.clarifier import ClarifierAgent

logger = structlog.get_logger()


class ArchitectAgent(BaseAgent):
    """æ¶æå¸ Agentï¼ç³»ç»è®¾è®¡ã

    WHY èè´£åç¦»ï¼æ¶æå¸åªåé«å±è®¾è®¡ï¼ç»ä»¶/æ°æ®æµ/ææ¯éåï¼ï¼
    ä¸åä»£ç ãè®¾è®¡ç»æä¾ Developer Agent æ¶è´¹ã
    """

    role = AgentRole.ARCHITECT

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        prompt = self._build_prompt(input_data.task, input_data.context)
        if self.llm is None:
            return AgentOutput(result={"design": f"[mock] æ¶æè®¾è®¡: {input_data.task}"})
        resp = await self.llm.generate(prompt, task_id=input_data.context.get("task_id", ""))
        return AgentOutput(result={"design": resp.content})

    def _build_prompt(self, task: str, context: dict[str, Any]) -> str:
        return f"""åºäºä»¥ä¸éæ±è®¾è®¡ç³»ç»æ¶æï¼

éæ±ï¼{task}
ä¸ä¸æï¼{json.dumps(context, ensure_ascii=False)}

è¾åºè¦æ±ï¼
1. ç»ä»¶åè¡¨ï¼æ¨¡å/ç±»ï¼
2. æ°æ®æµæè¿°
3. ææ¯éåå»ºè®®
"""

    def system_prompt(self) -> str:
        return (
            f"ä½ æ¯ V14.1 å¤æºè½ä½åä½ç½ç»ä¸­ç {self.role.value} Agentã"
            "ä¸æ³¨äºç³»ç»æ¶æè®¾è®¡ï¼è¾åºç»æåçè®¾è®¡ææ¡£ã"
        )


class DeveloperAgent(BaseAgent):
    """å¼åè
    Agentï¼ä»£ç å®ç°ã

       WHY èè´£åç¦»ï¼Developer æ¥æ¶æ¶æå¸çè®¾è®¡ï¼è¾åºå¯æ§è¡ä»£ç ã
       ä¸è´è´£æµè¯ï¼QA Agentï¼åå®¡æ¥ï¼Reviewer Agentï¼ã
    """

    role = AgentRole.DEVELOPER

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        design = input_data.context.get("design", input_data.task)
        prompt = self._build_prompt(design, input_data.context)
        if self.llm is None:
            return AgentOutput(
                result={"code": f"# [mock] code for: {input_data.task}", "language": "python"}
            )
        resp = await self.llm.generate(prompt, task_id=input_data.context.get("task_id", ""))
        return AgentOutput(result={"code": resp.content, "language": "python"})

    def _build_prompt(self, design: str, context: dict[str, Any]) -> str:
        code_context = context.get("code_context", "")
        return f"""åºäºè®¾è®¡æ¹æ¡çæä»£ç ï¼

è®¾è®¡ï¼{design}
ä»£ç ä¸ä¸æï¼å·²æä»£ç ï¼ï¼{code_context}

è¾åºå¯ç´æ¥è¿è¡ç Python ä»£ç ï¼åå«å½æ°å®ä¹åç±»åæ³¨è§£ã
"""

    def system_prompt(self) -> str:
        return (
            f"ä½ æ¯ V14.1 å¤æºè½ä½åä½ç½ç»ä¸­ç {self.role.value} Agentã"
            "ä¸æ³¨äºç¼åé«è´¨é Python ä»£ç ï¼ä¸¥æ ¼ç±»åæ³¨è§£ï¼ç¬¦å PEP è§èã"
        )


class ReviewerAgent(BaseAgent):
    """å®¡æ¥å Agentï¼ä»£ç è´¨éæ£æ¥ã

        WHY èè´£åç¦»ï¼ç¬ç«å®¡æ¥é¿å
     Developer èªå®¡ç²åºã
    """

    role = AgentRole.REVIEWER

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        code = input_data.context.get("code", input_data.task)
        prompt = self._build_prompt(code, input_data.context)
        if self.llm is None:
            return AgentOutput(result={"review": "[mock] å®¡æ¥éè¿", "issues": []})
        resp = await self.llm.generate(prompt, task_id=input_data.context.get("task_id", ""))
        return AgentOutput(result={"review": resp.content, "issues": []})

    def _build_prompt(self, code: str, context: dict[str, Any]) -> str:
        return f"""å®¡æ¥ä»¥ä¸ä»£ç çè´¨éåå®å¨æ§ï¼

ä»£ç ï¼
{code}

æ£æ¥é¡¹ï¼ç±»åæ³¨è§£ãå¼å¸¸å¤çãSQLæ³¨å¥ãå½ä»¤æ³¨å¥ãç©ºå¼å¤çãé»è¾éè¯¯ã
è¾åºæ ¼å¼ï¼éæ¡ååºé®é¢ï¼ä¸¥é/ä¸è¬ï¼ï¼æ é®é¢åå"å®¡æ¥éè¿"ã
"""

    def system_prompt(self) -> str:
        return (
            f"ä½ æ¯ V14.1 å¤æºè½ä½åä½ç½ç»ä¸­ç {self.role.value} Agentã"
            "ä¸æ³¨äºä»£ç å®¡æ¥ï¼åç°æ½å¨ç¼ºé·ãå®å¨éæ£ãæ§è½é®é¢ã"
        )


class QAAgent(BaseAgent):
    """QA éªè¯å Agentï¼æµè¯ä¸éªè¯ã

    WHY èè´£åç¦»ï¼QA ç¬ç«ç¼åæµè¯ç¨ä¾ï¼ä¸ Developer å½¢æåäººå¼åæ¨¡å¼ã
    """

    role = AgentRole.QA

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        code = input_data.context.get("code", input_data.task)
        prompt = self._build_prompt(code, input_data.context)
        if self.llm is None:
            return AgentOutput(
                result={"tests": f"# [mock] tests for: {input_data.task}", "passed": True}
            )
        resp = await self.llm.generate(prompt, task_id=input_data.context.get("task_id", ""))
        return AgentOutput(result={"tests": resp.content, "passed": True})

    def _build_prompt(self, code: str, context: dict[str, Any]) -> str:
        return f"""ä¸ºä»¥ä¸ä»£ç çæ pytest æµè¯ç¨ä¾ï¼

ä»£ç ï¼
{code}

è¦æ±ï¼è¦çæ­£å¸¸è·¯å¾åå¼å¸¸æåµï¼ä½¿ç¨ pytest é£æ ¼ã
"""

    def system_prompt(self) -> str:
        return (
            f"ä½ æ¯ V14.1 å¤æºè½ä½åä½ç½ç»ä¸­ç {self.role.value} Agentã"
            "ä¸æ³¨äºæµè¯ç¨ä¾çæï¼è¦çè¾¹çåå¼å¸¸åºæ¯ã"
        )


class ConfigManagerAgent(BaseAgent):
    """é
    ç½®ç®¡çå Agentï¼ç¯å¢é
    ç½®ç®¡çã

        WHY èè´£åç¦»ï¼é
    ç½®æ¼ç§»æ£æµï¼L8ï¼éè¦ Agent ä¸»å¨ç®¡çé
    ç½®æä»¶ï¼
        èä¸æ¯è¢«å¨åè­¦ã
    """

    role = AgentRole.CONFIG_MANAGER

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        prompt = self._build_prompt(input_data.task, input_data.context)
        if self.llm is None:
            return AgentOutput(result={"config": f"# [mock] config for: {input_data.task}"})
        resp = await self.llm.generate(prompt, task_id=input_data.context.get("task_id", ""))
        return AgentOutput(result={"config": resp.content})

    def _build_prompt(self, task: str, context: dict[str, Any]) -> str:
        return f"""ç®¡çä»¥ä¸ç¯å¢éç½®ï¼

ä»»å¡ï¼{task}
å½åç¯å¢åéï¼{json.dumps(context.get('env', {}), ensure_ascii=False)}

è¾åºéç½®åæ´å»ºè®®ææ§è¡éç½®æ´æ°ã
"""

    def system_prompt(self) -> str:
        return (
            f"ä½ æ¯ V14.1 å¤æºè½ä½åä½ç½ç»ä¸­ç {self.role.value} Agentã"
            "ä¸æ³¨äºç¯å¢éç½®ç®¡çï¼ç¡®ä¿éç½®ä¸è´æ§ã"
        )


class AgentFactory:
    """Agent å·¥åï¼æ ¹æ®è§è²è¿åå®ä¾ã

        WHY å·¥åæ¨¡å¼ï¼è°åº¦å¨ä¸å
    ³å¿å
    ·ä½ Agent ç±»ï¼åªéè°ç¨ get_agent(role)ã
        æ·»å æ°è§è²ä¸æ¹è°åº¦å¨ä»£ç ã
    """

    _registry: dict[AgentRole, type[BaseAgent]] = {
        AgentRole.ARCHITECT: ArchitectAgent,
        AgentRole.DEVELOPER: DeveloperAgent,
        AgentRole.REVIEWER: ReviewerAgent,
        AgentRole.QA: QAAgent,
        AgentRole.CONFIG_MANAGER: ConfigManagerAgent,
        AgentRole.CLARIFIER: ClarifierAgent,  # éæ±æ¾æ¸ Agent
    }

    @classmethod
    def create(
        cls,
        role: AgentRole | str,
        llm: Any = None,
        graph: Any = None,
        sandbox: Any = None,
    ) -> BaseAgent:
        """create = get_agent alias."""
        return cls.get_agent(role, llm=llm, graph=graph, sandbox=sandbox)

    @classmethod
    def get_agent(
        cls,
        role: AgentRole | str,
        llm: Any = None,
        graph: Any = None,
        sandbox: Any = None,
    ) -> BaseAgent:
        """æè§è²åå»º Agent å®ä¾ã

        Args:
            role: AgentRole æä¸¾æå­ç¬¦ä¸²
            llm: LLMClient å®ä¾ï¼å¯éï¼mock æ¨¡å¼ä¸ä¼ ï¼
            graph: CodeGraphEngine å®ä¾ï¼å¯éï¼
            sandbox: Sandbox å®ä¾ï¼å¯éï¼

        Returns:
            å¯¹åºè§è²ç BaseAgent å®ä¾

        Raises:
            ValueError: æªç¥è§è²
        """
        if isinstance(role, str):
            role = AgentRole(role)
        agent_cls = cls._registry.get(role)
        if agent_cls is None:
            raise ValueError(f"Unknown agent role: {role}")
        return agent_cls(llm=llm, graph=graph, sandbox=sandbox)

    @classmethod
    def register(cls, role: AgentRole, agent_cls: type[BaseAgent]) -> None:
        """æ³¨åæ° Agentï¼æ©å±ç¨ï¼ã"""
        cls._registry[role] = agent_cls
