from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from .blind import BlindProjectEvaluation
from .outcome import ProjectOutcome


class MismatchClassification(str, Enum):
    EVIDENCE_STRONGLY_SUPPORTS = "evidence_strongly_supports_outcome"
    EVIDENCE_MODERATELY_SUPPORTS = "evidence_moderately_supports_outcome"
    EVIDENCE_DOES_NOT_CLEARLY_DISTINGUISH = "evidence_does_not_clearly_distinguish_winner"
    EVIDENCE_CONFLICTS = "evidence_conflicts_with_outcome"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class StrongNonWinner(BaseModel):
    project_id: str
    slug: str
    title: str
    composite_quality_score: float
    completion_score: float
    technical_depth_score: float
    product_coherence_score: float
    repo_url: Optional[str] = None
    demo_url: Optional[str] = None
    key_strengths: List[str] = Field(default_factory=list)
    why_it_stands_out: str = ""


class ProjectForensicRecord(BaseModel):
    project_id: str
    slug: str
    title: str
    blind_evaluation: BlindProjectEvaluation
    outcome: ProjectOutcome
    mismatch_classification: MismatchClassification
    mismatch_explanation: str
    comparable_non_winners: List[str] = Field(default_factory=list)
    unobserved_factor_hypotheses: List[str] = Field(default_factory=list)  # explicitly labeled as possibilities!


class CohortMetricComparison(BaseModel):
    dimension_or_feature: str
    group_a_name: str
    group_b_name: str
    mean_a: float
    mean_b: float
    diff: float
    cohens_d: Optional[float] = None
    odds_ratio: Optional[float] = None
    sample_a: int
    sample_b: int
    interpretation: str = ""


class EventForensicAnalysis(BaseModel):
    event_slug: str
    total_projects: int
    total_winners: int
    total_overall_winners: int
    total_sponsor_winners: int
    total_non_winners: int
    strong_non_winners: List[StrongNonWinner] = Field(default_factory=list)
    mismatch_breakdown: Dict[MismatchClassification, int] = Field(default_factory=dict)
    project_records: List[ProjectForensicRecord] = Field(default_factory=list)
    cohort_comparisons: Dict[str, List[CohortMetricComparison]] = Field(default_factory=dict)
    counterfactual_audits: List[Dict[str, Any]] = Field(default_factory=list)
    summary_findings: List[str] = Field(default_factory=list)
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
