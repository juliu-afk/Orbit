"""DoWhy GCM 封装——因果图全生命周期管理.

WHY DoWhy GCM (MIT):
  gcm.attribute_anomalies() 精确命中根因归因场景——
  用 Shapley 对称化区分"起源节点"和"继承节点"，
  避免把从父节点继承异常的子节点误判为根因。

用法:
    mgr = CausalModelManager(db=trajectory_collector._db)
    dag = mgr.build_dag()        # 领域知识构建 DAG
    graph = await mgr.fit()      # DoWhy GCM 拟合
    await mgr.export_json()      # 导出 data/causal_graph.json
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

import structlog

from orbit.causal.models import CausalEdge, CausalGraph

logger = structlog.get_logger("orbit.causal.graph")

# 因果变量——从轨迹数据中可提取的字段映射
VARIABLE_MAP: dict[str, str] = {
    "agent_role": "trajectories.agent_role",
    "model_tier": "trajectories.model_tier",
    "task_outcome": "trajectories.final_outcome",
    "latency": "trajectories.completed_at - trajectories.started_at",
    "tool_error_rate": "COUNT(steps WHERE outcome='failed') / COUNT(steps)",
    "total_turns": "trajectories.total_turns",
    "quality_score": "trajectories.quality_score",
}

# 因果 DAG 结构——领域知识定义（agent_role 影响 outcome，model_tier 影响 latency，等等）
# 边方向: source → target
DOMAIN_DAG: list[tuple[str, str]] = [
    ("agent_role", "task_outcome"),
    ("agent_role", "tool_error_rate"),
    ("model_tier", "latency"),
    ("model_tier", "task_outcome"),
    ("tool_error_rate", "task_outcome"),
    ("total_turns", "latency"),
    ("total_turns", "task_outcome"),
]


class CausalModelManager:
    """DoWhy GCM 因果模型管理器。

    三步配方（DoWhy GCM 标准流程）:
      1. build_dag()——从领域知识构建 nx.DiGraph
      2. fit()——gcm.auto.assign_causal_mechanisms() + gcm.fit()
      3. 查询——attribute_anomalies() / arrow_strength() / causal_effect()
    """

    # GCM 拟合最低样本数——低于此值降级为相关性
    MIN_SAMPLES = 50

    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db
        self._dag: object | None = None    # nx.DiGraph
        self._gcm: object | None = None    # dowhy.gcm.InvertibleStructuralCausalModel
        self._last_graph: CausalGraph | None = None

    # ── 公共 API ──────────────────────────────────────

    def build_dag(self) -> object:
        """从领域知识构建因果 DAG（nx.DiGraph）。

        为什么不用 PC 算法自动发现:
          - 变量数 <10 个，领域知识足够构建结构
          - 轨迹数据量 <5000 条，PC 边定向准确率低
          - 领域知识 DAG + DoWhy 数据校准 = 精确度 > 纯 PC
        """
        import networkx as nx

        dag = nx.DiGraph()
        dag.add_nodes_from(VARIABLE_MAP.keys())
        dag.add_edges_from(DOMAIN_DAG)

        if not nx.is_directed_acyclic_graph(dag):
            # 防御：如果领域知识定义有误（出现环），去掉最后一条边
            logger.warning("dag_has_cycle", edges=list(dag.edges()))
            try:
                cycle_edges = list(nx.find_cycle(dag))
                for u, v in cycle_edges:
                    dag.remove_edge(u, v)
            except nx.NetworkXNoCycle:
                pass  # 竞争条件：检查后图变了，无环=无需修复
            except Exception:
                logger.error("dag_cycle_removal_failed", exc_info=True)

        self._dag = dag
        logger.info("dag_built", nodes=len(dag.nodes), edges=len(dag.edges))
        return dag

    async def fit(self, min_samples: int | None = None) -> CausalGraph:
        """用轨迹数据拟合 GCM 模型。

        Args:
            min_samples: 最低样本数，默认 MIN_SAMPLES=50

        Returns:
            CausalGraph——含边权重 + 拟合质量
        """
        min_samples = min_samples or self.MIN_SAMPLES

        # 1. 检查数据量
        sample_count = self._count_samples()
        if sample_count < min_samples:
            logger.warning("insufficient_samples", count=sample_count, min=min_samples)
            return CausalGraph(sample_size=sample_count, fit_quality=0.0)

        # 2. 提取数据矩阵
        data_df = self._extract_data()
        if data_df is None or len(data_df) < min_samples:
            return CausalGraph(sample_size=len(data_df) if data_df is not None else 0)

        # 3. 构建 DAG
        dag = self.build_dag()

        # 4. DoWhy GCM 拟合
        try:
            from dowhy import gcm

            gcm_model = gcm.InvertibleStructuralCausalModel(dag)
            gcm.auto.assign_causal_mechanisms(gcm_model, data_df)
            gcm.fit(gcm_model, data_df)
            self._gcm = gcm_model
        except Exception as e:
            logger.error("gcm_fit_failed", error=str(e), exc_info=True)
            return CausalGraph(sample_size=sample_count, fit_quality=0.0)

        # 5. 提取边强度 + 置信度
        edges: list[CausalEdge] = []
        fit_scores: list[float] = []
        for u, v in dag.edges():
            try:
                strength = float(gcm.arrow_strength(gcm_model, target=v))
                # 将 arrow_strength 映射到 [0,1] 区间
                normalized = min(strength / max(sum(
                    gcm.arrow_strength(gcm_model, target=v) for _ in [1]
                ) or 1.0, 1.0), 1.0)
                confidence = min(sample_count / 500.0, 1.0)  # 样本越多越可信
                fit_scores.append(normalized)
                edges.append(CausalEdge(
                    source_var=u, target_var=v,
                    causal_strength=normalized, confidence=confidence,
                    sample_count=sample_count,
                ))
            except Exception:
                edges.append(CausalEdge(source_var=u, target_var=v,
                                        sample_count=sample_count))

        fit_quality = sum(fit_scores) / len(fit_scores) if fit_scores else 0.0

        graph = CausalGraph(
            variables=list(dag.nodes()),
            edges=edges,
            learned_at=time.time(),
            sample_size=sample_count,
            fit_quality=round(fit_quality, 4),
        )
        self._last_graph = graph

        # 6. 写入 causal_edges 表
        self._save_edges(edges)

        # 7. 导出 JSON
        self._export_json(graph)

        logger.info("gcm_fitted", edges=len(edges), samples=sample_count,
                     fit_quality=round(fit_quality, 3))
        return graph

    async def update(self, new_trajectory_ids: list[str]) -> CausalGraph:
        """增量重拟合——追加新轨迹后重新 GCM fit。

        当前实现: 全量重拟合（GCM 不支持增量）。
        轨迹数 <5000 条时全量拟合 <2 秒，可接受。
        """
        return await self.fit()

    @property
    def gcm_model(self) -> object | None:
        return self._gcm

    @property
    def last_graph(self) -> CausalGraph | None:
        return self._last_graph

    # ── 内部 ──────────────────────────────────────────

    def _count_samples(self) -> int:
        try:
            row = self._db.execute(
                "SELECT count(*) FROM trajectories WHERE completed_at > 0"
            ).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def _extract_data(self):
        """从 TrajectoryCollector 的 trajectories + trajectory_steps 表提取特征矩阵。

        Returns:
            pandas DataFrame——每行一条轨迹，列为因果变量
        """
        import pandas as pd

        query = """
        SELECT
            t.agent_role,
            t.model_tier,
            t.total_turns,
            t.quality_score,
            CASE WHEN t.final_outcome = 'completed' THEN 1 ELSE 0 END as task_outcome,
            (t.completed_at - t.started_at) as latency,
            CAST((
                SELECT count(*) FROM trajectory_steps s
                WHERE s.trajectory_id = t.trajectory_id AND s.outcome = 'failed'
            ) AS REAL) / MAX(CAST(t.total_tool_calls AS REAL), 1.0) as tool_error_rate
        FROM trajectories t
        WHERE t.completed_at > 0 AND t.total_tool_calls > 0
        """
        try:
            df = pd.read_sql_query(query, self._db)

            # 处理缺失值：model_tier 为空 → "unknown"
            if "model_tier" in df.columns:
                df["model_tier"] = df["model_tier"].fillna("unknown")
                df.loc[df["model_tier"] == "", "model_tier"] = "unknown"

            # agent_role 编码为类别
            df["agent_role"] = df["agent_role"].astype("category")
            df["model_tier"] = df["model_tier"].astype("category")

            return df
        except Exception as e:
            logger.error("extract_data_failed", error=str(e))
            return None

    def _save_edges(self, edges: list[CausalEdge]) -> None:
        """写入 SQLite causal_edges 表。"""
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS causal_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_var TEXT NOT NULL,
                target_var TEXT NOT NULL,
                causal_strength REAL NOT NULL DEFAULT 0.0,
                confidence REAL NOT NULL DEFAULT 0.0,
                avg_causal_effect REAL,
                sample_count INTEGER NOT NULL,
                last_updated REAL NOT NULL,
                UNIQUE(source_var, target_var)
            )
        """)
        now = time.time()
        for e in edges:
            self._db.execute(
                """INSERT OR REPLACE INTO causal_edges
                   (source_var, target_var, causal_strength, confidence,
                    avg_causal_effect, sample_count, last_updated)
                   VALUES (?,?,?,?,?,?,?)""",
                (e.source_var, e.target_var, e.causal_strength, e.confidence,
                 e.avg_causal_effect, e.sample_count, now),
            )
        self._db.commit()

    def _export_json(self, graph: CausalGraph) -> None:
        """导出到 data/causal_graph.json——供驾驶舱 + git 追踪。"""
        try:
            os.makedirs("data", exist_ok=True)
            path = Path("data/causal_graph.json")
            data = graph.model_dump(mode="json")
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            logger.info("causal_graph_exported", path=str(path))
        except OSError as e:
            logger.warning("causal_graph_export_failed", error=str(e))
