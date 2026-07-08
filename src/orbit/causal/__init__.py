"""因果推理引擎 (V14.2+Theory 方向 1).

DoWhy GCM (MIT) —— 从轨迹数据中构建因果图，
用 gcm.attribute_anomalies() 定位失败根因，
用 LLM 生成人类可读解释（P1）。

用法:
    from orbit.causal import CausalModelManager, RootCauseAnalyzer, CausalRecommender
    mgr = CausalModelManager(db=trajectory_collector._db)
    await mgr.fit()
    analyzer = RootCauseAnalyzer(mgr, trajectory_collector)
    root_cause = await analyzer.analyze("task-123")
"""

from orbit.causal.graph import CausalModelManager
from orbit.causal.models import CausalEdge, CausalGraph, CauseCandidate, RootCause
from orbit.causal.recommend import CausalRecommender
from orbit.causal.root_cause import RootCauseAnalyzer

__all__ = [
    "CausalEdge",
    "CausalGraph",
    "CausalModelManager",
    "CauseCandidate",
    "CausalRecommender",
    "RootCause",
    "RootCauseAnalyzer",
]
