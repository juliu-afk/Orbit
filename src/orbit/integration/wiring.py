"""Orbit 全模块集成接线器 (Phase F).

将 Phase A-E 的独立模块接入 Agent 执行生命周期。
单文件接线——最小化对 task_runner/factory 的侵入。

用法:
    wiring = OrbitWiring()
    # task start
    wiring.on_task_start(task_id, goal, project_id)
    # task end
    wiring.on_task_end(task_id, outcome, quality_score)
    # agent created
    enhanced_prompt = wiring.enhance_prompt(base_prompt, category, keywords)
    # record event
    wiring.record_event(task_id, title, outcome, tags)
    # periodic
    await wiring.maybe_distill()
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.agents.react_agent import ReActAgent

import structlog

logger = structlog.get_logger("orbit.integration.wiring")

# 每 N 个完成任务触发一次离线蒸馏
DISTILL_EVERY_N_TASKS = 10


class OrbitWiring:
    """全模块集成接线器——单例，懒初始化所有可选组件。

    用法:
        wiring = OrbitWiring(db_path="orbit_wiring.db")
        wiring.on_task_start("t1", "audit AR", "client_001")
        wiring.record_event("t1", "AR cutoff error", "rejected", ["audit","AR"])
        wiring.on_task_end("t1", "completed", 0.85)
        await wiring.maybe_distill()
        prompt = wiring.enhance_prompt(base, "audit", ["AR","cutoff"])
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._task_count = 0

        # 懒初始化组件
        self._trajectory: object | None = None
        self._episodic: object | None = None
        self._profile: object | None = None
        self._agentic: object | None = None
        self._distill: object | None = None
        self._anchor: object | None = None
        self._grpo: object | None = None
        self._injector: object | None = None
        self._llm_distill: object | None = None
        self._monitor: object | None = None
        self._mcts: object | None = None

    # ── 生命周期钩子 ───────────────────────────────────

    def on_task_start(self, task_id: str, goal: str, project_id: str = "") -> None:
        """任务开始时调用——启动轨迹收集。"""
        self._task_count += 1
        tc = self._get_trajectory()
        if tc:
            tc.start_trajectory(task_id=task_id, goal=goal, project_id=project_id)
            logger.debug("trajectory_started", task_id=task_id, goal=goal[:60])

    def on_task_end(self, task_id: str, outcome: str, quality_score: float = 0.0,
                    turns: int = 0, tool_calls: int = 0) -> None:
        """任务结束时调用——完成轨迹收集。"""
        tc = self._get_trajectory()
        if tc:
            # 需要 trajectory_id——从 task_id 推算
            import hashlib, time
            tid = hashlib.sha256(f"{task_id}:".encode()).hexdigest()[:16]
            tc.finish_trajectory(tid, final_outcome=outcome, quality_score=quality_score,
                                  total_turns=turns, total_tool_calls=tool_calls)
            logger.debug("trajectory_finished", task_id=task_id, outcome=outcome)

    def record_event(self, task_id: str, title: str, outcome: str = "",
                     tags: list[str] | None = None) -> None:
        """记录情节事件。"""
        em = self._get_episodic()
        if em:
            from orbit.memory.episodic import EventImportance
            imp = EventImportance.HIGH if outcome == "failure" else EventImportance.MEDIUM
            em.record_event(task_id=task_id, title=title, outcome=outcome,
                            importance=imp, tags=tags or [])
            logger.debug("event_recorded", task_id=task_id, title=title[:60])

    def enhance_prompt(self, base_prompt: str, category: str = "",
                       keywords: list[str] | None = None) -> str:
        """增强 system prompt——注入策略原则 + Agentic 建议。"""
        result = base_prompt

        # 1. 注入高效用策略原则
        inj = self._get_injector()
        if inj:
            result = inj.inject(result, category=category, task_keywords=keywords)

        # 2. 注入 Agentic Memory 建议
        am = self._get_agentic()
        if am and keywords:
            query = " ".join(keywords)
            suggestions = am.suggest(query, limit=3)
            if suggestions:
                lines = ["\n\n## 相关行动建议"]
                for s in suggestions:
                    lines.append(f"- {s.action} (效用: {s.utility:.0%})")
                result += "\n".join(lines)

        return result

    async def maybe_distill(self) -> None:
        """每 N 个任务触发一次离线蒸馏（规则 + LLM）。"""
        if self._task_count % DISTILL_EVERY_N_TASKS != 0:
            return

        tc = self._get_trajectory()
        de = self._get_distill()
        if tc is None or de is None:
            return

        completed = tc.get_completed(limit=20)
        if len(completed) < 3:
            return

        # 规则蒸馏
        for t in completed[:10]:
            exported = tc.export_for_training(t["trajectory_id"])
            de.distill_from_trajectory(exported)

        logger.info("distill_triggered", task_count=self._task_count, trajectories=len(completed))

        # LLM 蒸馏（可选——需要 LLM client）
        lld = self._get_llm_distill()
        if lld:
            await lld.distill_batch(completed[:10], category="")

        # GRPO 评分
        grpo = self._get_grpo()
        if grpo:
            grpo.update_utilities()

    # ── 懒初始化 ───────────────────────────────────────

    def _get_trajectory(self):
        if self._trajectory is None:
            try:
                from orbit.observability.trajectory import TrajectoryCollector
                self._trajectory = TrajectoryCollector(self._db_path)
            except Exception:
                pass
        return self._trajectory

    def _get_episodic(self):
        if self._episodic is None:
            try:
                from orbit.memory.episodic import EpisodicMemory
                self._episodic = EpisodicMemory(self._db_path)
            except Exception:
                pass
        return self._episodic

    def _get_profile(self):
        if self._profile is None:
            try:
                from orbit.memory.profile import ProfileStore
                self._profile = ProfileStore(self._db_path)
            except Exception:
                pass
        return self._profile

    def _get_agentic(self):
        if self._agentic is None:
            try:
                from orbit.memory.agentic import AgenticMemory
                self._agentic = AgenticMemory(self._db_path)
            except Exception:
                pass
        return self._agentic

    def _get_distill(self):
        if self._distill is None:
            try:
                from orbit.evolution.distill import DistillationEngine
                self._distill = DistillationEngine(self._db_path)
            except Exception:
                pass
        return self._distill

    def _get_anchor(self):
        if self._anchor is None:
            try:
                from orbit.evolution.anchor import AnchorGuard
                self._anchor = AnchorGuard(self._db_path)
            except Exception:
                pass
        return self._anchor

    def _get_grpo(self):
        if self._grpo is None:
            try:
                from orbit.evolution.grpo import GRPOScorer
                self._grpo = GRPOScorer(engine=self._get_distill())
            except Exception:
                pass
        return self._grpo

    def _get_injector(self):
        if self._injector is None:
            try:
                from orbit.evolution.inject import PromptInjector
                self._injector = PromptInjector(engine=self._get_distill())
            except Exception:
                pass
        return self._injector

    def _get_llm_distill(self):
        if self._llm_distill is None:
            try:
                from orbit.evolution.llm_distill import LLMDistiller
                self._llm_distill = LLMDistiller(anchor=self._get_anchor(), engine=self._get_distill())
            except Exception:
                pass
        return self._llm_distill

    def _get_monitor(self):
        if self._monitor is None:
            try:
                from orbit.metacognition.monitor import MonitorAgent
                self._monitor = MonitorAgent()
            except Exception: pass
        return self._monitor

    def _get_mcts(self):
        if self._mcts is None:
            try:
                from orbit.agents.mcts import MCTSPlanner
                self._mcts = MCTSPlanner()
            except Exception: pass
        return self._mcts

    def get_mcts_planner(self):
        """获取 MCTSPlanner——供 react_agent 在规划阶段使用。"""
        return self._get_mcts()

    async def start_monitor(self, task_id: str, goal: str = "") -> asyncio.Task | None:
        """启动 MonitorAgent 作为独立 asyncio Task。

        返回 Task 对象——调用方负责在任务结束时 cancel。
        """
        mon = self._get_monitor()
        if mon is None:
            return None
        mon._goal = goal
        mon._task_id = task_id
        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(mon.run(queue, task_id=task_id))
        task._monitor_queue = queue  # type: ignore[attr-defined]  # 供主 Agent 推送事件
        logger.debug("monitor_started", task_id=task_id, goal=goal[:60])
        return task
