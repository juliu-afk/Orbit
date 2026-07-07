"""Orbit 全模块集成接线器 (Phase F).

将 Phase A-E 的独立模块接入 Agent 执行生命周期。
单文件接线——最小化对 task_runner/factory 的侵入。

框架级初始化:
    from orbit.integration.wiring import configure_wiring
    configure_wiring(db_path="data/orbit_wiring.db", event_bus=_event_bus)

运行时用法:
    wiring = get_wiring()
    wiring.on_task_start(task_id, goal, project_id)
    wiring.load_profile(project_id)              # 加载用户画像
    wiring.start_monitor(task_id, goal)          # 启动 Monitor + HITL
    wiring.feed_monitor(task_id, event_dict)     # 推送事件到 Monitor
    wiring.record_event(task_id, title, outcome, tags)  # 情节记忆
    wiring.enhance_prompt(base_prompt, category, keywords)  # 策略+Agentic注入
    await wiring.maybe_distill()                # 每N任务离线蒸馏
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.events.bus import EventBus
    from orbit.agents.react_agent import ReActAgent
    from orbit.memory.profile import UserProfile

import structlog

logger = structlog.get_logger("orbit.integration.wiring")

# 每 N 个完成任务触发一次离线蒸馏
# WHY 环境变量: 允许部署时调整蒸馏频率而不改代码
def _get_distill_interval() -> int:
    import os
    try:
        return int(os.environ.get("ORBIT_DISTILL_EVERY_N_TASKS", "10"))
    except (ValueError, TypeError):
        return 10

DISTILL_EVERY_N_TASKS = _get_distill_interval()


class OrbitWiring:
    """全模块集成接线器——单例，懒初始化所有可选组件。

    框架级初始化（main.py）:
        configure_wiring(db_path="data/orbit_wiring.db", event_bus=_event_bus)

    运行时用法:
        wiring = get_wiring()
        wiring.on_task_start("t1", "audit AR", "client_001")
        wiring.record_event("t1", "AR cutoff error", "rejected", ["audit","AR"])
        wiring.on_task_end("t1", "completed", 0.85)
        await wiring.maybe_distill()
        prompt = wiring.enhance_prompt(base, "audit", ["AR","cutoff"])
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._task_count = 0
        self._event_bus: EventBus | None = None  # main.py 注入——供 HITLManager 使用

        # Monitor 事件队列——task_id → asyncio.Queue
        self._monitor_queues: dict[str, asyncio.Queue] = {}

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

    def feed_monitor(self, task_id: str, event: dict) -> None:
        """向 Monitor 队列推送事件——react_agent 在 TOOL_RESULT/TURN_START 后调用。

        fail-open: 队列满或不存在时静默丢弃。
        """
        q = self._monitor_queues.get(task_id)
        if q is None:
            return
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            logger.debug("monitor_queue_full", task_id=task_id)

    def load_profile(self, project_id: str) -> UserProfile | None:
        """加载用户画像——task_runner 在任务开始时调用。

        Returns:
            UserProfile 或 None（项目无画像时）。
        """
        ps = self._get_profile()
        if ps:
            return ps.get_profile(project_id)
        return None

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
        anchor = self._get_anchor()
        for t in completed[:10]:
            exported = tc.export_for_training(t["trajectory_id"])
            # ANCHOR: 蒸馏前检查——拒绝不适合提炼的轨迹
            if anchor:
                verdict = anchor.check_before_distill(exported)
                if verdict.verdict == "rejected":
                    logger.debug("anchor_reject_distill", traj_id=t.get("trajectory_id",""), reason=verdict.reason)
                    continue
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
            except Exception:
                logger.warning("monitor_init_failed", exc_info=True)
        return self._monitor

    def _get_mcts(self):
        if self._mcts is None:
            try:
                from orbit.agents.mcts import MCTSPlanner
                self._mcts = MCTSPlanner()
            except Exception:
                logger.warning("mcts_init_failed", exc_info=True)
        return self._mcts

    def get_mcts_planner(self):
        """获取 MCTSPlanner——供 react_agent 在规划阶段使用。"""
        return self._get_mcts()

    async def start_monitor(self, task_id: str, goal: str = "") -> asyncio.Task | None:
        """启动 MonitorAgent 作为独立 asyncio Task——含 HITLManager 接线。

        返回 Task 对象——调用方负责在任务结束时 cancel。
        """
        mon = self._get_monitor()
        if mon is None:
            return None

        # 创建 HITLManager——有 event_bus 时接线到前端
        hitl = None
        if self._event_bus:
            try:
                from orbit.metacognition.hitl import HITLManager
                hitl = HITLManager(event_bus=self._event_bus)
            except Exception:
                logger.debug("hitl_init_failed", exc_info=True)

        mon._goal = goal
        mon._task_id = task_id
        mon._hitl = hitl  # 注入 HITLManager——Monitor CRITICAL 告警可触发人工介入

        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._monitor_queues[task_id] = queue
        task = asyncio.create_task(mon.run(queue, task_id=task_id))
        logger.debug("monitor_started", task_id=task_id, goal=goal[:60], hitl=hitl is not None)
        return task


# ── 模块级单例 ──

_wiring_instance: OrbitWiring | None = None


def configure_wiring(db_path: str, event_bus: EventBus | None = None) -> OrbitWiring:
    """框架级初始化——main.py 调用，注入依赖。

    替代模块级懒初始化。调用后 get_wiring() 返回已配置的实例。

    Args:
        db_path: SQLite 数据库路径（持久化轨迹/记忆/策略原则）
        event_bus: EventBus 实例——供 HITLManager 推送 WS 通知

    Returns:
        已配置的 OrbitWiring 实例
    """
    global _wiring_instance
    _wiring_instance = OrbitWiring(db_path=db_path)
    _wiring_instance._event_bus = event_bus
    # 确保 data 目录存在
    import os
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    logger.info("orbit_wiring_configured", db_path=db_path, has_event_bus=event_bus is not None)
    return _wiring_instance


def get_wiring() -> OrbitWiring:
    """获取全局 OrbitWiring 单例。

    如果 configure_wiring() 未被调用，回退到 :memory: 模式（向后兼容）。
    """
    global _wiring_instance
    if _wiring_instance is None:
        _wiring_instance = OrbitWiring()
    return _wiring_instance
