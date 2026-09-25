from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class AwardType(str, Enum):
    OVERALL = "overall"          # 1st, 2nd, 3rd Best Overall
    SPONSOR = "sponsor"          # Sponsor-specific challenges (e.g. Wix/Base44, Microsoft, etc.)
    TRACK = "track"              # Track awards (e.g. Best FinTech, Best Health)
    BEGINNER = "beginner"        # Best First-Time Hacker
    PEOPLES_CHOICE = "peoples_choice"
    OTHER = "other"


class ProjectAward(BaseModel):
    name: str
    award_type: AwardType
    sponsor: Optional[str] = None
    placement: Optional[str] = None  # e.g., "1st", "2nd", "3rd", "Winner"
    official_source: str = ""
    raw_badge_text: str = ""


class ProjectOutcome(BaseModel):
    project_id: str
    is_winner: bool = False
    is_overall_winner: bool = False
    is_sponsor_winner: bool = False
    is_track_winner: bool = False
    is_beginner_winner: bool = False
    awards: List[ProjectAward] = Field(default_factory=list)
    unsealed_at: Optional[datetime] = None
