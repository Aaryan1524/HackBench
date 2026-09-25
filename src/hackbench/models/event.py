from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from .provenance import ProvenanceRecord


class JudgingCriterion(BaseModel):
    name: str
    description: str = ""
    weight_percentage: Optional[float] = None
    source_url: str = ""


class PrizeCategory(BaseModel):
    prize_id: str
    title: str
    prize_type: str = "general"  # overall, sponsor, track, beginner, community, other
    sponsor_name: Optional[str] = None
    description: str = ""
    value_usd: Optional[float] = None
    number_of_winners: int = 1
    technologies_required_or_encouraged: List[str] = Field(default_factory=list)
    source_url: str = ""


class HackathonEvent(BaseModel):
    name: str
    slug: str
    year: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    organizer: str = ""
    event_url: str
    devpost_url: str
    gallery_url: str
    judging_criteria: List[JudgingCriterion] = Field(default_factory=list)
    eligibility_rules: List[str] = Field(default_factory=list)
    submission_requirements: List[str] = Field(default_factory=list)
    prize_categories: List[PrizeCategory] = Field(default_factory=list)
    sponsor_challenges: List[Dict[str, Any]] = Field(default_factory=list)
    special_tracks: List[str] = Field(default_factory=list)
    judging_process: str = ""
    judging_weights_published: bool = False
    number_of_projects: Optional[int] = None
    number_of_participants: Optional[int] = None
    technologies_encouraged: List[str] = Field(default_factory=list)
    official_winner_announcements: List[str] = Field(default_factory=list)
    sources: List[ProvenanceRecord] = Field(default_factory=list)
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
