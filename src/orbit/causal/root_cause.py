"""根因分析器——DoWhy GCM anomaly attribution.

WHY DoWhy 而非相关性排序:
  相关性: P(失败 | developer) 高 ≠ developer 导致了失败（可能是 assignment bias——
  复杂任务更常分配给 developer，真正原因是任务复杂）
  gcm.attribute_anomalies(): 区分"起源节点"和"继承节点"，
  用 Shapley 对称化 + invertible causal mechanisms 重建噪声。

用法:
    analyzer = RootCauseAnalyzer(model_manager, trajectory_collector)
    root_cause = await analyzer.analyze("task-123")
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3
    from orbit.causal.graph import CausalModelManager
    from orbit.observability.trajectory import TrajectoryCollector

import structlog

from orbit.causal.models import CauseCandidate, RootCause

logger = structlog.get_logger("orbit.causal.root_cause")

# 异常分数最低阈值——低于此值标记"无显著根因"
MIN_ANOMALY_SCORE = 0.3


class RootCauseAnalyzer:
    """失败根因分析器。

    DoWhy GCM attribute_anomalies() 三步:
      1. 从轨迹中提取该任务的变量值
      2. gcm.attribute_anomalies(target_node='task_outcome', anomaly_samples=data)
      3. 异常分数排序 + 置信度计算
    """

    def __init__(
        self,
        model: CausalModelManager,
        trajectory_collector: TrajectoryCollector,
    ) -> None:
        self._model = model
        self._tc = trajectory_collector

    async def analyze(self, task_id: str) -> RootCause:
        """分析指定任务的失败根因。

        Args:
            task_id: 失败任务的 ID

        Returns:
            RootCause——含异常分数降序的候选根因列表
        """
        # 0. 检查 GCM 是否已拟合
        gcm_model = self._model.gcm_model
        if gcm_model is None:
            return self._fallback_correlation(task_id)

        # 1. 从轨迹表中提取该任务的特征
        task_data = self._extract_task_features(task_id)
        if task_data is None:
            return RootCause(
                task_id=task_id,
                confidence=0.0,
                missing_variables=["task_not_found_or_incomplete"],
            )

        # 2. 检测缺失变量
        missing = [k for k, v in task_data.items() if v is None or v == ""]
        if "model_tier" in missing:
            logger.debug("model_tier_missing_for_task", task_id=task_id)

        # 3. DoWhy GCM anomaly attribution
        try:
            import pandas as pd
            from dowhy import gcm

            df = pd.DataFrame([task_data])
            # 将分类变量转为 category dtype（与 fit 时一致）
            for col in ["agent_role", "model_tier"]:
                if col in df.columns:
                    df[col] = df[col].astype("category")

            # 归因异常到上游节点
            attribution = gcm.attribute_anomalies(
                gcm_model,
                target_node="task_outcome",
                anomaly_samples=df,
            )
        except Exception as e:
            logger.warning("anomaly_attribution_failed",
                           task_id=task_id, error=str(e))
            return self._fallback_correlation(task_id)

        # 4. 构建结果
        causes: list[CauseCandidate] = []
        for var_name, score_array in attribution.items():
            score = float(score_array[0]) if hasattr(score_array, '__len__') else float(score_array)
            if var_name == "task_outcome":
                continue  # 不把自己列为根因
            causes.append(CauseCandidate(
                variable=var_name,
                anomaly_score=round(score, 4),
            ))

        # 异常分数降序
        causes.sort(key=lambda c: c.anomaly_score, reverse=True)

        # 整体置信度
        confidence = self._calc_confidence(causes, len(missing) == 0)

        # 如果所有节点分数都低
        if not causes or all(c.anomaly_score < MIN_ANOMALY_SCORE for c in causes):
            return RootCause(
                task_id=task_id,
                causes=causes,
                confidence=confidence,
                missing_variables=missing,
                stale=not self._is_model_fresh(),
            )

        return RootCause(
            task_id=task_id,
            causes=causes,
            top_cause=causes[0] if causes else None,
            confidence=confidence,
            missing_variables=missing,
            stale=not self._is_model_fresh(),
        )

    # ── 降级模式 ──────────────────────────────────────

    def _fallback_correlation(self, task_id: str) -> RootCause:
        """GCM 不可用时降级为 Spearman 相关排序。

        从 causal_edges 表读取已存储的边强度，按强度排序。
        """
        try:
            rows = self._tc._db.execute(
                """SELECT source_var, causal_strength FROM causal_edges
                   WHERE target_var = 'task_outcome'
                   ORDER BY causal_strength DESC LIMIT 5"""
            ).fetchall()
            causes = [
                CauseCandidate(
                    variable=r["source_var"],
                    anomaly_score=r["causal_strength"],
                )
                for r in rows
            ]
        except Exception:
            causes = []

        return RootCause(
            task_id=task_id,
            causes=causes,
            top_cause=causes[0] if causes else None,
            confidence=0.3,  # 降级模式置信度低
            stale=True,
        )

    # ── 内部 ──────────────────────────────────────────

    def _extract_task_features(self, task_id: str) -> dict | None:
        """从轨迹表中提取单个任务的特征值。"""
        try:
            row = self._tc._db.execute(
                """SELECT agent_role, model_tier, total_turns, quality_score,
                          final_outcome,
                          (completed_at - started_at) as latency,
                          CAST((
                              SELECT count(*) FROM trajectory_steps s
                              WHERE s.trajectory_id = t.trajectory_id
                              AND s.outcome = 'failed'
                          ) AS REAL) / MAX(CAST(t.total_tool_calls AS REAL), 1.0)
                          as tool_error_rate
                   FROM trajectories t
                   WHERE t.task_id = ? AND t.completed_at > 0
                   ORDER BY t.completed_at DESC LIMIT 1""",
                (task_id,),
            ).fetchone()

            if row is None:
                return None

            return {
                "agent_role": row["agent_role"] or "developer",
                "model_tier": row["model_tier"] or "unknown",
                "total_turns": row["total_turns"],
                "quality_score": row["quality_score"],
                "task_outcome": 1 if row["final_outcome"] == "completed" else 0,
                "latency": row["latency"] or 0.0,
                "tool_error_rate": row["tool_error_rate"] or 0.0,
            }
        except Exception as e:
            logger.warning("extract_task_features_failed",
                           task_id=task_id, error=str(e))
            return None

    def _calc_confidence(self, causes: list[CauseCandidate],
                         all_vars_present: bool) -> float:
        """计算整体置信度。

        因子: ① 是否有显著异常分数 ② 是否所有变量都可用 ③ 因果图是否新鲜
        """
        if not causes:
            return 0.0
        top_score = causes[0].anomaly_score
        # 异常分数越高越可信
        score_conf = min(top_score / 0.8, 1.0) if top_score > 0 else 0.0
        # 变量缺失惩罚
        var_penalty = 1.0 if all_vars_present else 0.7
        # 因果图新鲜度
        freshness = 1.0 if self._is_model_fresh() else 0.6
        return round(score_conf * var_penalty * freshness, 4)

    def _is_model_fresh(self) -> bool:
        """因果图是否在 24 小时内更新过。"""
        graph = self._model.last_graph
        if graph is None:
            return False
        return (time.time() - graph.learned_at) < 86400
