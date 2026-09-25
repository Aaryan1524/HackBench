from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class EvidenceType(str, Enum):
    REPOSITORY = "repository"
    DEVPOST = "devpost"
    DEMO = "demo"
    EVENT_RULES = "event_rules"
    DEPLOYMENT = "deployment"
    GIT_HISTORY = "git_history"
    DERIVED_METRIC = "derived_metric"


class ProvenanceRecord(BaseModel):
    """
    Every extracted claim and measured fact must retain source provenance.
    """
    claim: str
    evidence_type: EvidenceType
    source: str
    location: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    details: Optional[dict] = None
