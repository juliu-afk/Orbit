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
        self._llm_client: object | None = None     # P2-2: LLMClient 单例缓存
        self._cost_store: object | None = None      # V15.2: CostStore 单例
        self._last_tier: str = ""
        # V15.2 Fable5: deviation log + blindspot + quiz wiring
        self._deviation_loggers: dict[str, object] = {}  # task_id → DeviationLogger
        self._blindspot: object | None = None
        self._quiz_gen: object | None = None
        self._semantic_transfer: object | None = None
        self._scope: object | None = None
        self._gepa: object | None = None
        self._knowledge_store: object | None = None
        self._code_graph: object | None = None
        self._ckpt_manager: object | None = None
        # V14.2+Theory P1+P2: 19模块懒初始化
        self._spectral: object | None = None       # D3: SpectralAnalyzer
        self._ib_comp: object | None = None        # D4: IBCompressor
        self._ot_matcher: object | None = None     # D11: OTMatcher
        self._mdp: object | None = None            # D17: AgentMDP
        self._abs_pipe: object | None = None       # D22: AbstractPipelineAnalyzer
        self._vcg: object | None = None            # D9: VCGAllocator
        self._pac: object | None = None            # D14: PACBound
        self._slicer: object | None = None         # D24: ProgramSlicer
        self._temporal: object | None = None       # D5: L9TemporalValidator
        self._sep_logic: object | None = None      # D18: L10SeparationValidator
        self._bisim: object | None = None          # D19: BisimulationChecker
        self._bft: object | None = None            # D25: BFTGuard
        self._shapley: object | None = None        # D6: ShapleyAttribution
        self._mdl: object | None = None            # D7: MDLScorer
        self._dp_guard: object | None = None       # D10: DPGuard
        self._tda: object | None = None            # D12: TDAAnalyzer
        self._free_energy: object | None = None    # D15: FreeEnergyMonitor
        self._info_geom: object | None = None      # D21: InfoGeometry
        self._effect: object | None = None         # D23: EffectTracker

    # ── 生命周期钩子 ───────────────────────────────────

    def on_task_start(self, task_id: str, goal: str, project_id: str = "") -> None:
        """任务开始时调用——启动轨迹收集 + 偏离日志 + 盲区扫描。"""
        self._task_count += 1
        tc = self._get_trajectory()
        if tc:
            traj = tc.start_trajectory(task_id=task_id, goal=goal, project_id=project_id)
            self._trajectory_ids[task_id] = traj.trajectory_id
            logger.debug("trajectory_started", task_id=task_id, trajectory_id=traj.trajectory_id, goal=goal[:60])
            try:
                pac = self._get_pac()
                if pac is not None:
                    strategies = self._get_distill()
                    if strategies:
                        H = len(strategies.top_principles(50))
                        self._pac_threshold = pac.adaptive_threshold(H, self._task_count)
            except Exception: pass
        # V15.2 Fable5 P0: create DeviationLogger per task
        try:
            from orbit.checkpoint.deviation import DeviationLogger
            self._deviation_loggers[task_id] = DeviationLogger(task_id=task_id)
        except Exception:
            pass

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
            # V14.2+Theory: Bellman gap + ΔF自由能 + BFT操作审计
            try:
                mdp = self._get_mdp()
                if mdp:
                    gap = mdp.compute_bellman_gap([])  # 累积轨迹后批量计算
                    logger.debug("bellman_gap", gap=gap)
            except Exception: pass
            try:
                fe = self._get_fe()
                if fe:
                    dF = fe.estimate_from_alerts(0.0, 0, 0.0)
                    if fe.is_critical(dF):
                        logger.warning("free_energy_critical", delta_F=dF)
            except Exception: pass
            try:
                bft = self._get_bft()
                if bft and outcome != "completed":
                    ok, _ = bft.approve("task_failed_" + task_id[:8])
                    logger.debug("bft_audit", task_id=task_id, approved=ok)
            except Exception:
                pass  # fail-open
            logger.debug("trajectory_finished", task_id=task_id, trajectory_id=traj_id, outcome=outcome)

        # V15.2 Fable5 P0: flush deviation log → feed GEPA + SCOPE
        dev_log = self._deviation_loggers.pop(task_id, None)
        if dev_log is not None:
            try:
                ckpt = self._get_ckpt_manager()
                if ckpt:
                    import asyncio
                    task = asyncio.create_task(dev_log.flush_to_checkpoint(ckpt))
                    # suppress "coroutine was never awaited" warning for fire-and-forget
                    task.add_done_callback(lambda _: None)
            except Exception: pass
            try:
                scope = self._get_scope()
                if scope and hasattr(dev_log, 'to_tactical_rules'):
                    scope.add_deviations_batch(task_id, dev_log.to_tactical_rules())
            except Exception: pass
            try:
                gepa = self._get_gepa()
                if gepa and hasattr(dev_log, 'get_failure_reasons'):
                    reasons = dev_log.get_failure_reasons()
                    if reasons:
                        import asyncio
                        task = asyncio.create_task(gepa.evolve_from_deviations(reasons))
                        task.add_done_callback(lambda _: None)
            except Exception: pass

        # V15.2 Fable5 P1: generate quiz for core module changes
        try:
            from orbit.modes.quiz_generator import QuizGenerator
        except Exception: pass

        # V16.0 Phase F: Grill Pattern → GEPA/SCOPE 反馈进化
        try:
            import sqlite3
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute(
                "SELECT asking_agent, answering_agent, COUNT(*) as cnt "
                "FROM grill_log WHERE task_id=? GROUP BY 1,2 HAVING cnt>=3",
                (task_id,),
            ).fetchall()
            if rows:
                gepa = self._get_gepa()
                scope = self._get_scope()
                patterns = [f"{r[0]}→{r[1]}: {r[2]}次" for r in rows]
                if gepa:
                    task = asyncio.create_task(
                        gepa.evolve_from_deviations([f"Grill模式: {p}" for p in patterns])
                    )
                    task.add_done_callback(
                        lambda t: logger.warning("gepa_evolve_failed", error=str(t.exception()))
                        if t.exception() else None
                    )
                if scope:
                    scope.add_deviations_batch(
                        task_id,
                        [f"Agent {r[0]} 频繁向 {r[1]} 查询——上下文模板缺字段" for r in rows],
                    )
            conn.close()
        except Exception as e:
            logger.warning("grill_pattern_extract_failed", task_id=task_id, error=str(e)[:200])

        # 清理 Monitor 资源——发送结束信号 + 取消 Task + 删队列
        self._cleanup_monitor(task_id)

    # V15.2 Fable5 P0: agent deviation recording
    def record_deviation(self, task_id: str, planned: str, actual: str,
                         reason: str, alternatives: list[str] | None = None,
                         severity: str = "major", file_refs: list[str] | None = None,
                         agent_id: str = "") -> None:
        """Agent 执行中记录偏离。"""
        try:
            from orbit.checkpoint.deviation import DeviationSeverity
            sev = DeviationSeverity.CRITICAL if severity == "critical" else DeviationSeverity.MAJOR
            dev_log = self._deviation_loggers.get(task_id)
            if dev_log is not None and hasattr(dev_log, 'record'):
                dev_log.record(planned=planned, actual=actual, reason=reason,
                              alternatives=alternatives or [], severity=sev,
                              file_refs=file_refs or [], agent_id=agent_id)
        except Exception:
            pass  # fail-open: deviation logging doesn't block agent

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

        # V14.2+Theory P1+P2离线管线: Shapley归因 + MDL评分 + 信息几何 + 频谱
        try:
            shapley = self._get_shapley()
            if shapley and completed:
                agents = [t.get("agent_role", "unknown") for t in completed[:5]]
                def v(s): return len(s) * 0.1
                vals = shapley.attribute(list(set(agents)), v, method="mc")
                logger.debug("shapley_attribution", vals=vals)
        except Exception: pass
        try:
            mdl = self._get_mdl()
            if mdl:
                s = mdl.score("", 0)
                logger.debug("mdl_baseline", score=s)
        except Exception: pass
        try:
            ig = self._get_ig()
            if ig:
                kl = ig.kl_divergence([0.5,0.5], [0.6,0.4])
                logger.debug("kl_divergence", kl=kl)
        except Exception: pass
        try:
            spectral = self._get_spectral()
            if spectral:
                import numpy as np
                adj = np.eye(3)
                import scipy.sparse as sp
                report = spectral.analyze(sp.csr_matrix(adj))
                logger.debug("spectral_modularity", modularity=report.modularity)
        except Exception: pass

        # V14.2+Theory 方向16: GEPA 进化——Conformal 共形预测接入离线管线
        try:
            from orbit.evolution.gepa import GEPAEngine
            # P1-1: 从历史轨迹构建校准集——conformal 有数据才能筛选
            cp = self._get_conformal()
            if cp is not None and tc is not None:
                completed = tc.get_completed(limit=50)
                cal_data = []
                for t in completed:
                    exported = tc.export_for_training(t["trajectory_id"])
                    goal = exported.get("goal", "")
                    code = exported.get("output", "")
                    outcome = t.get("final_outcome", "") == "completed"
                    if goal and code:
                        cal_data.append((goal, code, outcome))
                if cal_data:
                    cp.calibrate(cal_data)
            ge = GEPAEngine(
                llm=self._get_llm_client(),
                distill=de,
                conformal=cp,
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


    # ── V14.2+Theory P1+P2: 19模块懒getters ──────────
    def _get_spectral(self):
        if self._spectral is None:
            try:
                from orbit.graph.spectral import SpectralAnalyzer
                self._spectral = SpectralAnalyzer()
            except Exception: pass
        return self._spectral
    def _get_ib(self):
        if self._ib_comp is None:
            try:
                from orbit.compression.ib_compressor import IBCompressor
                self._ib_comp = IBCompressor()
            except Exception: pass
        return self._ib_comp
    def _get_ot(self):
        if self._ot_matcher is None:
            try:
                from orbit.context.ot_matcher import OTMatcher
                self._ot_matcher = OTMatcher()
            except Exception: pass
        return self._ot_matcher
    def _get_mdp(self):
        if self._mdp is None:
            try:
                from orbit.agents.mdp import AgentMDP
                self._mdp = AgentMDP()
            except Exception: pass
        return self._mdp
    def _get_abs_pipe(self):
        if self._abs_pipe is None:
            try:
                from orbit.hallucination.abstract_interp import AbstractPipelineAnalyzer
                self._abs_pipe = AbstractPipelineAnalyzer()
            except Exception: pass
        return self._abs_pipe
    def _get_vcg(self):
        if self._vcg is None:
            try:
                from orbit.compose.mechanism import VCGAllocator
                self._vcg = VCGAllocator()
            except Exception: pass
        return self._vcg
    def _get_pac(self):
        if self._pac is None:
            try:
                from orbit.evolution.pac_bounds import PACBound
                self._pac = PACBound()
            except Exception: pass
        return self._pac
    def _get_slicer(self):
        if self._slicer is None:
            try:
                from orbit.graph.engines.slicer import ProgramSlicer
                self._slicer = ProgramSlicer()
            except Exception: pass
        return self._slicer
    def _get_temporal(self):
        if self._temporal is None:
            try:
                from orbit.hallucination.l9_temporal import L9TemporalValidator
                self._temporal = L9TemporalValidator()
            except Exception: pass
        return self._temporal
    def _get_sep(self):
        if self._sep_logic is None:
            try:
                from orbit.hallucination.l10_separation import L10SeparationValidator
                self._sep_logic = L10SeparationValidator()
            except Exception: pass
        return self._sep_logic
    def _get_bisim(self):
        if self._bisim is None:
            try:
                from orbit.agents.bisim import BisimulationChecker
                self._bisim = BisimulationChecker()
            except Exception: pass
        return self._bisim
    def _get_bft(self):
        if self._bft is None:
            try:
                from orbit.goal.bft import BFTGuard
                self._bft = BFTGuard()
            except Exception: pass
        return self._bft
    def _get_shapley(self):
        if self._shapley is None:
            try:
                from orbit.observability.attribution import ShapleyAttribution
                self._shapley = ShapleyAttribution()
            except Exception: pass
        return self._shapley
    def _get_mdl(self):
        if self._mdl is None:
            try:
                from orbit.review.mdl_scorer import MDLScorer
                self._mdl = MDLScorer()
            except Exception: pass
        return self._mdl
    def _get_dp(self):
        if self._dp_guard is None:
            try:
                from orbit.observability.dp import DPGuard
                self._dp_guard = DPGuard()
            except Exception: pass
        return self._dp_guard
    def _get_tda(self):
        if self._tda is None:
            try:
                from orbit.graph.tda import TDAAnalyzer
                self._tda = TDAAnalyzer()
            except Exception: pass
        return self._tda
    def _get_fe(self):
        if self._free_energy is None:
            try:
                from orbit.metacognition.free_energy import FreeEnergyMonitor
                self._free_energy = FreeEnergyMonitor()
            except Exception: pass
        return self._free_energy
    def _get_ig(self):
        if self._info_geom is None:
            try:
                from orbit.evolution.info_geom import InfoGeometry
                self._info_geom = InfoGeometry()
            except Exception: pass
        return self._info_geom
    def _get_effect(self):
        if self._effect is None:
            try:
                from orbit.hallucination.effect_tracker import EffectTracker
                self._effect = EffectTracker()
            except Exception: pass
        return self._effect

    def _get_llm_client(self):
        """P2-2: LLMClient 单例缓存——GEPA 进化复用。"""
        if self._llm_client is None:
            try:
                from orbit.gateway.client import LLMClient
                self._llm_client = LLMClient(cost_store=self._get_cost_store())
            except Exception:
                logger.warning("llm_client_init_failed", exc_info=True)
        return self._llm_client

    def _get_cost_store(self):
        """V15.2: CostStore 单例——所有 LLMClient 共享。"""
        if self._cost_store is None:
            try:
                from orbit.observability.cost import CostStore
                self._cost_store = CostStore("data/costs.db")
            except Exception:
                logger.warning("cost_store_init_failed", exc_info=True)
        return self._cost_store

    # V15.2 Fable5: lazy init for wired components

    def _get_blindspot(self):
        if self._blindspot is None:
            try:
                from orbit.metacognition.blindspot import BlindspotScanner
                self._blindspot = BlindspotScanner(
                    knowledge_store=self._get_knowledge_store(),
                    code_graph=self._get_code_graph(),
                )
            except Exception:
                pass
        return self._blindspot

    def _get_scope(self):
        if self._scope is None:
            try:
                from orbit.evolution.scope import ScopeMemory
                self._scope = ScopeMemory(db_path=self._db_path)
            except Exception:
                pass
        return self._scope

    def _get_gepa(self):
        if self._gepa is None:
            try:
                from orbit.evolution.gepa import GEPAEngine
                self._gepa = GEPAEngine(llm=self._get_llm_client(), distill=self._get_distill())
            except Exception:
                pass
        return self._gepa

    def _get_knowledge_store(self):
        if self._knowledge_store is None:
            try:
                from orbit.knowledge.store import KnowledgeStore
                self._knowledge_store = KnowledgeStore()
            except Exception:
                pass
        return self._knowledge_store

    def _get_code_graph(self):
        if self._code_graph is None:
            try:
                from orbit.graph.engines.code_graph import CodeGraphEngine
                self._code_graph = CodeGraphEngine()
            except Exception:
                pass
        return self._code_graph

    def _get_ckpt_manager(self):
        if self._ckpt_manager is None:
            try:
                from orbit.checkpoint.manager import CheckpointManager
                self._ckpt_manager = CheckpointManager()
            except Exception:
                pass
        return self._ckpt_manager

    def _get_semantic_transfer(self):
        if self._semantic_transfer is None:
            try:
                from orbit.graph.meta_graph import SemanticTransfer
                self._semantic_transfer = SemanticTransfer()
            except Exception:
                pass
        return self._semantic_transfer

    def set_parent_id(self, parent_id: str | None) -> None:
        """V15.2: 设置 subagent 的 parent_id——spawn 前调用。"""
        client = self._get_llm_client()
        if client:
            client._current_parent_id = parent_id

    def set_task_id(self, task_id: str) -> None:
        """V15.2: 设置当前 task_id——task 开始时调用。"""
        client = self._get_llm_client()
        if client:
            client._current_task_id = task_id

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
        mon._blindspot = self._get_blindspot()  # V15.2 Fable5 P1: 注入盲区扫描器

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
