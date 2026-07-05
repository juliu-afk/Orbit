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

# 模块级单例——所有调用方共享同一实例
_wiring_instance: OrbitWiring | None = None


def get_wiring(db_path: str = ":memory:") -> "OrbitWiring":
    """获取模块级单例。react_agent/task_runner 等不同调用方共享同一实例。"""
    global _wiring_instance
    if _wiring_instance is None:
        _wiring_instance = OrbitWiring(db_path=db_path)
    return _wiring_instance


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
        self._gepa: object | None = None
        self._scope: object | None = None

    # ── 生命周期钩子 ───────────────────────────────────

    def on_task_start(self, task_id: str, goal: str, project_id: str = "") -> None:
        """任务开始时调用——启动轨迹收集 + 自动创建用户画像。"""
        self._task_count += 1
        tc = self._get_trajectory()
        if tc:
            tc.start_trajectory(task_id=task_id, goal=goal, project_id=project_id)
            logger.debug("trajectory_started", task_id=task_id, goal=goal[:60])
        # 自动创建 ProfileStore 条目（如果不存在）
        if project_id:
            ps = self._get_profile()
            if ps:
                try:
                    from orbit.memory.profile import UserProfile
                    existing = ps.get_profile(project_id)
                    if existing is None:
                        ps.upsert_profile(UserProfile(profile_id=project_id, display_name=project_id))
                except Exception: pass

    def on_task_end(self, task_id: str, outcome: str, quality_score: float = 0.0,
                    turns: int = 0, tool_calls: int = 0, monitor_task: object = None) -> None:
        """任务结束时调用——完成轨迹收集 + GRPO基线记录 + 取消Monitor。"""
        tc = self._get_trajectory()
        if tc:
            import hashlib
            tid = hashlib.sha256(f"{task_id}:".encode()).hexdigest()[:16]
            tc.finish_trajectory(tid, final_outcome=outcome, quality_score=quality_score,
                                  total_turns=turns, total_tool_calls=tool_calls)
            logger.debug("trajectory_finished", task_id=task_id, outcome=outcome)
        # GRPO 基线记录——每次任务结果都记录
        grpo = self._get_grpo()
        if grpo:
            category = self._infer_category_from_task(task_id)
            grpo.record_baseline(category, outcome == "completed")
        # 取消 Monitor——防止 task 泄露
        if monitor_task is not None:
            try: monitor_task.cancel()
            except Exception: pass

    def record_event(self, task_id: str, title: str, outcome: str = "",
                     tags: list[str] | None = None, category: str = "") -> None:
        """记录情节事件 + AgenticMemory 自动记住失败模式。"""
        em = self._get_episodic()
        if em:
            from orbit.memory.episodic import EventImportance
            imp = EventImportance.HIGH if outcome == "failure" else EventImportance.MEDIUM
            em.record_event(task_id=task_id, title=title, outcome=outcome,
                            importance=imp, tags=tags or [])
            logger.debug("event_recorded", task_id=task_id, title=title[:60])
        # 失败事件 → AgenticMemory 自动记住
        if outcome == "failure":
            am = self._get_agentic()
            if am:
                am.remember(trigger=title, action=f"避免: {title}",
                            expected_outcome="下次不再重复此错误",
                            category=category, tags=tags or [])
        # SCOPE 战术记忆——每次事件都记录为战术规则
        scope = self._get_scope()
        if scope:
            scope.add_tactical(task_id, title)

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

        # GEPA Prompt 进化——GRPO 评分后对低效用原则进行遗传优化
        gepa = self._get_gepa()
        if gepa and de:
            low_utility = [p for p in de.top_principles(50) if p.utility_score < 0.6]
            if len(low_utility) >= 3:
                try:
                    await gepa.evolve_population(low_utility, failure_reason="原则效用低于0.6，需进化", category="")
                except Exception as e:
                    logger.debug("gepa_evolution_failed", error=str(e))

        # SCOPE 战术→战略升级检查——高频战术规则自动升级
        scope = self._get_scope()
        if scope:
            try:
                from orbit.evolution.scope import ScopeMemory
                # 触发升级检查——add_tactical已在record_event中调用
                strategies = scope.get_strategic_all()
                if strategies:
                    logger.debug("scope_strategies_active", count=len(strategies))
            except Exception as e:
                logger.debug("scope_check_failed", error=str(e))

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
            except Exception as e:
                logger.debug("monitor_init_failed", error=str(e))
        return self._monitor

    def _get_mcts(self):
        if self._mcts is None:
            try:
                from orbit.agents.mcts import MCTSPlanner
                self._mcts = MCTSPlanner()
            except Exception as e:
                logger.debug("mcts_init_failed", error=str(e))
        return self._mcts

    def get_mcts_planner(self):
        return self._get_mcts()

    async def start_monitor(self, task_id: str, goal: str = "") -> object | None:
        mon = self._get_monitor()
        if mon is None: return None
        mon._goal = goal
        mon._task_id = task_id
        import asyncio
        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(mon.run(queue, task_id=task_id))
        task._monitor_queue = queue
        logger.debug("monitor_started", task_id=task_id, goal=goal[:60])
        return task

    def _get_gepa(self):
        if self._gepa is None:
            try:
                from orbit.evolution.gepa import GEPAEngine
                self._gepa = GEPAEngine(llm=None, distill=self._get_distill())
            except Exception as e:
                logger.debug("gepa_init_failed", error=str(e))
        return self._gepa

    def _get_scope(self):
        if self._scope is None:
            try:
                from orbit.evolution.scope import ScopeMemory
                self._scope = ScopeMemory(self._db_path)
            except Exception as e:
                logger.debug("scope_init_failed", error=str(e))
        return self._scope

    def _infer_category_from_task(self, task_id: str) -> str:
        """从 task_id 推断任务类别——供 GRPO 基线分类。"""
        tl = task_id.lower()
        if any(kw in tl for kw in ["audit","审计","AR","底稿","函证"]): return "审计"
        if any(kw in tl for kw in ["test","测试","pytest","coverage"]): return "测试"
        if any(kw in tl for kw in ["code","代码","fix","bug","实现"]): return "编码"
        return "通用"
