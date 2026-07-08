"""因果推理引擎数据模型——Pydantic v2."""
from __future__ import annotations
from pydantic import BaseModel, Field

class CausalEdge(BaseModel):
    source_var: str; target_var: str
    causal_strength: float = Field(0.0, ge=0.0, le=1.0)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    avg_causal_effect: float | None = None
    sample_count: int = 0

class CausalGraph(BaseModel):
    variables: list[str] = Field(default_factory=list)
    edges: list[CausalEdge] = Field(default_factory=list)
    learned_at: float = 0.0; sample_size: int = 0
    fit_quality: float = Field(0.0, ge=0.0, le=1.0)

class CauseCandidate(BaseModel):
    variable: str; anomaly_score: float = Field(0.0, ge=0.0)
    causal_effect: float | None = None
    explanation: str = ""; counterfactual: str = ""

class RootCause(BaseModel):
    task_id: str
    causes: list[CauseCandidate] = Field(default_factory=list)
    top_cause: CauseCandidate | None = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    explanation_failed: bool = False
    missing_variables: list[str] = Field(default_factory=list)
    stale: bool = False
