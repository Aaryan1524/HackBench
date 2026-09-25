from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from .provenance import ProvenanceRecord
from .repository import RepositoryMetrics


class BlindDemoSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    has_video_demo: bool = False
    video_platform: str = ""  # youtube, vimeo, loom, devpost, none
    video_url: str = ""
    duration_seconds: Optional[int] = None
    has_live_deployment: bool = False
    deployment_url: str = ""
    deployment_reachable: Optional[bool] = None
    has_slide_deck: bool = False
    observations: List[str] = Field(default_factory=list)


class BlindProjectBundle(BaseModel):
    """
    STRICT INVARIANT:
    This model MUST NEVER contain award names, winner status, badges, or placement.
    extra='forbid' prevents accidental contamination.
    """
    model_config = ConfigDict(extra="forbid")

    project_id: str
    slug: str
    title: str
    tagline: str
    problem_statement: str
    inspiration: str
    what_it_does: str
    how_it_was_built: str
    challenges: str
    accomplishments: str
    lessons_learned: str
    future_plans: str
    tech_tags: List[str] = Field(default_factory=list)
    team_size: int = 1
    repository_metrics: Optional[RepositoryMetrics] = None
    demo_summary: BlindDemoSummary = Field(default_factory=BlindDemoSummary)
    sponsor_technologies_mentioned: List[str] = Field(default_factory=list)
    bundle_sha256: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DimensionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str
    score_numeric: int = Field(ge=0, le=5)  # 0 to 5 rubric anchor
    score_ordinal: str  # very_weak, weak, moderate, strong, very_strong
    rubric_anchor: str
    justification: str
    evidence_citations: List[ProvenanceRecord] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class EvaluatorPass(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluator_id: str
    pass_index: int
    answers: Dict[str, str] = Field(default_factory=dict)
    # 17 standardized questions:
    # problem_solved, target_user, core_insight, primary_workflow, technically_difficult,
    # what_works, what_incomplete, evidence_for_completion, wow_moment, memorable_vs_generic,
    # substantive_vs_ornamental_tech, unverifiable_claims, strongest_aspects, weakest_aspects
    dimensions: Dict[str, DimensionScore] = Field(default_factory=dict)
    overall_assessment: str = ""
    strongest_aspects: List[str] = Field(default_factory=list)
    weakest_aspects: List[str] = Field(default_factory=list)
    confidence: float = 1.0


class BlindProjectEvaluation(BaseModel):
    """
    Sealed, immutable record of blind evaluation.
    """
    model_config = ConfigDict(extra="forbid")

    project_id: str
    bundle_sha256: str
    passes: List[EvaluatorPass] = Field(default_factory=list)
    aggregated_scores: Dict[str, float] = Field(default_factory=dict)  # dimension -> mean
    score_variance: Dict[str, float] = Field(default_factory=dict)     # dimension -> variance
    disputed_dimensions: List[str] = Field(default_factory=list)
    evaluator_agreement_status: str = "high_agreement"  # high_agreement, moderate_agreement, low_agreement_unstable
    composite_quality_score: float = 0.0  # weighted composite based on completion, depth, coherence, originality
    answers_consensus: Dict[str, str] = Field(default_factory=dict)
    evaluation_sha256: str = ""
    sealed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_frozen: bool = True
