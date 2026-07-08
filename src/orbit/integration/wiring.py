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
        # Monitor Tasks 引用——task_id → asyncio.Task（供清理+结束信号）
        self._monitor_tasks: dict[str, asyncio.Task] = {}
        # 轨迹 ID 映射——task_id → trajectory_id（保证 start/end 一致）
        self._trajectory_ids: dict[str, str] = {}

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
        self._bandit: object | None = None       # V14.2+Theory 方向2: ThompsonBandit
        self._drift: object | None = None        # V14.2+Theory 方向20: CUSUMDriftDetector
        self._pid: object | None = None          # V14.2+Theory 方向13: PIDAgentController
        self._conformal: object | None = None    # V14.2+Theory 方向16: ConformalPredictor
        self._router_agent: object | None = None  # P2-3: RouterAgent 单例缓存
        self._last_tier: str = ""

    # ── 生命周期钩子 ───────────────────────────────────

    def on_task_start(self, task_id: str, goal: str, project_id: str = "") -> None:
        """任务开始时调用——启动轨迹收集。"""
        self._task_count += 1
        tc = self._get_trajectory()
        if tc:
            traj = tc.start_trajectory(task_id=task_id, goal=goal, project_id=project_id)
            # 存储 trajectory_id——供 on_task_end 匹配
            self._trajectory_ids[task_id] = traj.trajectory_id
            logger.debug("trajectory_started", task_id=task_id, trajectory_id=traj.trajectory_id, goal=goal[:60])

    def on_model_tier_decided(self, task_id: str, model_tier: str) -> None:
        """V14.2+Theory: RouterAgent 决策模型层级后调用——回填轨迹表。

        任务开始时 model_tier 未知（start_trajectory 先于 RouterAgent），
        RouterAgent 决策后通过此方法回填 tier 到轨迹表。
        """
        tc = self._get_trajectory()
        traj_id = self._trajectory_ids.get(task_id, "")
        if tc and traj_id:
            tc.set_model_tier(traj_id, model_tier)
            self._last_tier = model_tier  # P0-1修复: 回填 wiring 内部——供 on_task_end 反馈 Bandit
            logger.debug("model_tier_recorded", task_id=task_id,
                         trajectory_id=traj_id, tier=model_tier)

    def on_task_end(self, task_id: str, outcome: str, quality_score: float = 0.0,
                    turns: int = 0, tool_calls: int = 0) -> None:
        """任务结束时调用——完成轨迹收集 + Bandit 反馈更新 + 清理 Monitor。"""
        tc = self._get_trajectory()
        traj_id = self._trajectory_ids.pop(task_id, "")
        if tc and traj_id:
            tc.finish_trajectory(traj_id, final_outcome=outcome, quality_score=quality_score,
                                  total_turns=turns, total_tool_calls=tool_calls)
            # V14.2+Theory 方向2: 从轨迹表读取 model_tier→Bandit 学习
            b = self._get_bandit()
            if b:
                try:
                    row = tc._db.execute(
                        "SELECT model_tier FROM trajectories WHERE trajectory_id=?",
                        (traj_id,)).fetchone()
                    tier = (row["model_tier"] if row else "") or self._last_tier
                    if tier:
                        success = outcome == "completed"
                        # P2-2修复: turns=0→默认2000ms（单轮任务估算）
                        est_latency = turns * 2000.0 if turns > 0 else 2000.0
                        b.update(tier, success, latency_ms=est_latency)
                        # V14.2+Theory 方向20: CUSUM 变点检测
                        d = self._get_drift()
                        if d:
                            alert = d.update(model=tier, latency_ms=est_latency, success=success)
                            if alert is not None:
                                b.reset_arm(alert.model)
                                logger.info("drift_reset", model=alert.model)
                        self._last_tier = ""
                except Exception:
                    pass  # fail-open
            logger.debug("trajectory_finished", task_id=task_id, trajectory_id=traj_id, outcome=outcome)

        # 清理 Monitor 资源——发送结束信号 + 取消 Task + 删队列
        self._cleanup_monitor(task_id)

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
                       keywords: list[str] | None = None,
                       type_sig: str = "",  # V14.2+Theory 方向8: 类型签名→生成约束
                       ) -> str:
        """增强 system prompt——注入策略原则 + Agentic 建议 + 类型约束。"""
        result = base_prompt

        # 0. V14.2+Theory 方向8: 类型导向合成——在生成前注入约束
        if type_sig:
            try:
                from orbit.hallucination.l4_type import TypeDirectedSynthesizer
                constraints = TypeDirectedSynthesizer.constrain(type_sig)
                if constraints:
                    lines = ["\n\n## 代码生成约束（类型导向）"]
                    lines.extend(f"- {c}" for c in constraints)
                    result += "\n".join(lines)
            except Exception:
                pass  # fail-open——约束注入失败不阻塞主 prompt 增强

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

        # V14.2+Theory 方向16: GEPA 进化——Conformal 共形预测接入离线管线
        try:
            from orbit.evolution.gepa import GEPAEngine
            from orbit.gateway.client import LLMClient
            llm_client = LLMClient()
            ge = GEPAEngine(
                llm=llm_client,
                distill=de,
                conformal=self._get_conformal(),
            )
            principles = de.top_principles(20) if de else []
            if principles and len(principles) >= 3:
                await ge.evolve_population(principles, category="distilled")
        except Exception:
            logger.debug("gepa_evolution_skipped", exc_info=True)

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
                pid = self._get_pid()  # V14.2+Theory 方向13: PID 连续矫正
                self._monitor = MonitorAgent(pid_controller=pid)
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

    # ── V14.2+Theory P0五方向: 懒初始化 getters ──────────

    def _get_bandit(self):
        """方向2: ThompsonBandit——多臂 Bandit 模型路由器。"""
        if self._bandit is None:
            try:
                from orbit.router.bandit import ThompsonBandit
                self._bandit = ThompsonBandit()
            except Exception:
                logger.warning("bandit_init_failed", exc_info=True)
        return self._bandit

    def _get_drift(self):
        """方向20: CUSUMDriftDetector——LLM 行为变点检测。"""
        if self._drift is None:
            try:
                from orbit.observability.drift_detector import CUSUMDriftDetector
                self._drift = CUSUMDriftDetector()
            except Exception:
                logger.warning("drift_init_failed", exc_info=True)
        return self._drift

    def _get_pid(self):
        """方向13: PIDAgentController——连续矫正替代二元告警。"""
        if self._pid is None:
            try:
                from orbit.metacognition.pid_controller import PIDAgentController
                self._pid = PIDAgentController()
            except Exception:
                logger.warning("pid_init_failed", exc_info=True)
        return self._pid

    def _get_conformal(self):
        """方向16: ConformalPredictor——95% 置信预测集。"""
        if self._conformal is None:
            try:
                from orbit.testing.conformal import ConformalPredictor
                self._conformal = ConformalPredictor(alpha=0.05)
            except Exception:
                logger.warning("conformal_init_failed", exc_info=True)
        return self._conformal

    def set_model_tier(self, tier: str) -> None:
        """记录最近 RouterAgent 选中的 tier——供 on_task_end 反馈 Bandit。"""
        self._last_tier = tier

    def get_router_agent(self):
        """V14.2+Theory 方向2+20: 带 Bandit+Drift 的 RouterAgent 单例。

        P2-3修复: 缓存——避免每次任务重新创建 RouterAgent。
        """
        if self._router_agent is not None:
            return self._router_agent
        try:
            from orbit.router.agent import RouterAgent
            self._router_agent = RouterAgent(
                weights=None,
                bandit=self._get_bandit(),
                drift_detector=self._get_drift(),
            )
            return self._router_agent
        except Exception:
            logger.warning("router_agent_init_failed", exc_info=True)
            return None

    async def start_monitor(self, task_id: str, goal: str = "") -> asyncio.Task | None:
        """启动 MonitorAgent 作为独立 asyncio Task——含 HITLManager 接线。

        返回 Task 对象——调用方负责在任务结束时 cancel。
        Task 引用存储在 self._monitor_tasks，on_task_end 自动清理。
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
        self._monitor_tasks[task_id] = task  # 存储引用——供清理
        logger.debug("monitor_started", task_id=task_id, goal=goal[:60], hitl=hitl is not None)
        return task

    def _cleanup_monitor(self, task_id: str) -> None:
        """清理 Monitor 资源——发送结束信号 + 取消 Task + 删队列。

        fail-safe: 任何步骤失败不抛异常。
        """
        # 1. 发送结束信号（None）让 Monitor.run() 正常退出
        q = self._monitor_queues.pop(task_id, None)
        if q:
            try:
                q.put_nowait(None)
            except (asyncio.QueueFull, Exception):
                pass

        # 2. 取消 Monitor Task
        mon_task = self._monitor_tasks.pop(task_id, None)
        if mon_task and not mon_task.done():
            mon_task.cancel()

    # ── 公开访问方法（P2-2 修复: 替代私有方法 _get_trajectory）──

    def get_trajectory(self):
        """获取 TrajectoryCollector 实例——供外部（如 main.py）访问。"""
        return self._get_trajectory()


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
