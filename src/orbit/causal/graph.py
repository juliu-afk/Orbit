"""DoWhy GCM 封装——因果图全生命周期管理 (V14.2+Theory)."""
from __future__ import annotations
import json, os, sqlite3, time
from pathlib import Path
import structlog
from orbit.causal.models import CausalEdge, CausalGraph
logger = structlog.get_logger("orbit.causal.graph")

VARIABLE_MAP = {"agent_role":"trajectories.agent_role","model_tier":"trajectories.model_tier","task_outcome":"trajectories.final_outcome","latency":"trajectories.completed_at-trajectories.started_at","tool_error_rate":"COUNT(steps WHERE outcome='failed')/COUNT(steps)","total_turns":"trajectories.total_turns","quality_score":"trajectories.quality_score"}
DOMAIN_DAG = [("agent_role","task_outcome"),("agent_role","tool_error_rate"),("model_tier","latency"),("model_tier","task_outcome"),("tool_error_rate","task_outcome"),("total_turns","latency"),("total_turns","task_outcome")]

class CausalModelManager:
    MIN_SAMPLES = 50
    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db; self._dag = None; self._gcm = None; self._last_graph = None
    def build_dag(self) -> object:
        import networkx as nx
        dag = nx.DiGraph(); dag.add_nodes_from(VARIABLE_MAP.keys()); dag.add_edges_from(DOMAIN_DAG)
        if not nx.is_directed_acyclic_graph(dag):
            logger.warning("dag_has_cycle"); 
            try:
                for u,v in list(nx.find_cycle(dag)): dag.remove_edge(u,v)
            except nx.NetworkXNoCycle: pass
            except Exception: logger.error("dag_cycle_removal_failed",exc_info=True)
        self._dag = dag; return dag
    async def fit(self, min_samples=None):
        min_samples = min_samples or self.MIN_SAMPLES
        n = self._count_samples()
        if n < min_samples: return CausalGraph(sample_size=n)
        df = self._extract_data()
        if df is None or len(df) < min_samples: return CausalGraph(sample_size=len(df) if df is not None else 0)
        dag = self.build_dag()
        try:
            from dowhy import gcm
            m = gcm.InvertibleStructuralCausalModel(dag); gcm.auto.assign_causal_mechanisms(m, df); gcm.fit(m, df)
            self._gcm = m
        except Exception as e: logger.error("gcm_fit_failed",error=str(e)); return CausalGraph(sample_size=n)
        edges = []; scores = []
        for u,v in dag.edges():
            try:
                s = float(gcm.arrow_strength(m, target=v))
                edges.append(CausalEdge(source_var=u,target_var=v,causal_strength=min(s,1.0),confidence=min(n/500.0,1.0),sample_count=n))
                scores.append(min(s, 1.0))
            except Exception:
                edges.append(CausalEdge(source_var=u,target_var=v,sample_count=n))
        fit_q = sum(scores)/len(scores) if scores else 0.0
        g = CausalGraph(variables=list(dag.nodes()),edges=edges,learned_at=time.time(),sample_size=n,fit_quality=round(fit_q,4))
        self._last_graph = g; self._save_edges(edges); self._export_json(g)
        return g
    async def update(self, ids): return await self.fit()
    @property
    def gcm_model(self): return self._gcm
    @property
    def last_graph(self): return self._last_graph
    def _count_samples(self):
        try:
            r = self._db.execute("SELECT count(*) FROM trajectories WHERE completed_at > 0").fetchone()
            return int(r[0]) if r else 0
        except Exception: return 0
    def _extract_data(self):
        import pandas as pd
        q = """SELECT t.agent_role, t.model_tier, t.total_turns, t.quality_score, CASE WHEN t.final_outcome='completed' THEN 1 ELSE 0 END as task_outcome, (t.completed_at-t.started_at) as latency, CAST((SELECT count(*) FROM trajectory_steps s WHERE s.trajectory_id=t.trajectory_id AND s.outcome='failed') AS REAL)/MAX(CAST(t.total_tool_calls AS REAL),1.0) as tool_error_rate FROM trajectories t WHERE t.completed_at>0 AND t.total_tool_calls>0"""
        try:
            df = pd.read_sql_query(q, self._db)
            for col in ["model_tier","agent_role"]:
                if col in df.columns: df[col]=df[col].fillna("unknown").astype("category"); df.loc[df[col]=="",col]="unknown"
            return df
        except Exception as e: logger.error("extract_data_failed",error=str(e)); return None
    def _save_edges(self, edges):
        self._db.execute("""CREATE TABLE IF NOT EXISTS causal_edges (id INTEGER PRIMARY KEY AUTOINCREMENT, source_var TEXT NOT NULL, target_var TEXT NOT NULL, causal_strength REAL NOT NULL DEFAULT 0.0, confidence REAL NOT NULL DEFAULT 0.0, avg_causal_effect REAL, sample_count INTEGER NOT NULL, last_updated REAL NOT NULL, UNIQUE(source_var, target_var))""")
        now = time.time()
        for e in edges: self._db.execute("INSERT OR REPLACE INTO causal_edges VALUES (NULL,?,?,?,?,?,?,?)",(e.source_var,e.target_var,e.causal_strength,e.confidence,e.avg_causal_effect,e.sample_count,now))
        self._db.commit()
    def _export_json(self, g):
        try:
            os.makedirs("data",exist_ok=True)
            Path("data/causal_graph.json").write_text(json.dumps(g.model_dump(mode="json"),ensure_ascii=False,indent=2),encoding="utf-8")
        except OSError as e: logger.warning("export_failed",error=str(e))
