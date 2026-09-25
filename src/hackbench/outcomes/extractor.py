import re
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from ..models import (
    ProjectOutcome,
    ProjectAward,
    AwardType,
    RawProject,
    HackathonEvent,
)

logger = logging.getLogger("hackbench.outcomes")


class OutcomeExtractor:
    """
    Extracts official award results from raw project submissions and event prizes.
    STRICT INVARIANT:
    Outcomes extracted here are quarantined in a sealed file and NEVER exposed
    to the blind evaluation pipeline.
    """

    def extract_and_seal_outcomes(
        self,
        event: HackathonEvent,
        projects: List[RawProject],
        sealed_output_path: Path,
    ) -> Dict[str, ProjectOutcome]:
        outcomes: Dict[str, ProjectOutcome] = {}

        for p in projects:
            awards: List[ProjectAward] = []

            # Examine raw winner awards text extracted during project scraping
            for raw_award in p.raw_winner_awards_text:
                award = self._classify_award(raw_award, event, p.devpost_url)
                if award:
                    awards.append(award)

            # If project had a winner badge in the gallery but no specific award was found on page
            if p.gallery_winner_badge and not awards:
                awards.append(
                    ProjectAward(
                        name="Hackathon Winner Badge",
                        award_type=AwardType.OTHER,
                        official_source=p.devpost_url,
                        raw_badge_text="Winner (Devpost Gallery Ribbon)",
                    )
                )

            is_win = len(awards) > 0
            is_overall = any(a.award_type == AwardType.OVERALL for a in awards)
            is_sponsor = any(a.award_type == AwardType.SPONSOR for a in awards)
            is_track = any(a.award_type == AwardType.TRACK for a in awards)
            is_beginner = any(a.award_type == AwardType.BEGINNER for a in awards)

            outcome = ProjectOutcome(
                project_id=p.project_id,
                is_winner=is_win,
                is_overall_winner=is_overall,
                is_sponsor_winner=is_sponsor,
                is_track_winner=is_track,
                is_beginner_winner=is_beginner,
                awards=awards,
                unsealed_at=None,  # Sealed!
            )
            outcomes[p.project_id] = outcome

        # Write to sealed path
        sealed_output_path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {pid: o.model_dump(mode="json") for pid, o in outcomes.items()}
        sealed_output_path.write_text(json.dumps(serializable, indent=2))
        logger.info(f"Sealed {len(outcomes)} project outcomes to {sealed_output_path}")

        return outcomes

    def _classify_award(
        self, raw_text: str, event: HackathonEvent, source_url: str
    ) -> Optional[ProjectAward]:
        text_clean = raw_text.strip()
        lower = text_clean.lower()

        placement = None
        if "1st" in lower or "first" in lower:
            placement = "1st"
        elif "2nd" in lower or "second" in lower:
            placement = "2nd"
        elif "3rd" in lower or "third" in lower:
            placement = "3rd"

        # Check for Overall
        if any(w in lower for w in ["best overall", "overall"]):
            return ProjectAward(
                name=text_clean,
                award_type=AwardType.OVERALL,
                placement=placement,
                official_source=source_url,
                raw_badge_text=raw_text,
            )

        # Check for Beginner
        if any(w in lower for w in ["first-time", "first time", "beginner", "freshman"]):
            return ProjectAward(
                name=text_clean,
                award_type=AwardType.BEGINNER,
                placement=placement,
                official_source=source_url,
                raw_badge_text=raw_text,
            )

        # Check for People's Choice
        if any(w in lower for w in ["people's choice", "community", "popular"]):
            return ProjectAward(
                name=text_clean,
                award_type=AwardType.PEOPLES_CHOICE,
                placement=placement,
                official_source=source_url,
                raw_badge_text=raw_text,
            )

        # Check against known event prizes
        sponsor_match = None
        if event and event.prize_categories:
            for prize in event.prize_categories:
                if prize.title.lower() in lower or (prize.sponsor_name and prize.sponsor_name.lower() in lower):
                    sponsor_match = prize.sponsor_name
                    break

        # Check common sponsor keywords
        if sponsor_match or any(w in lower for w in ["wix", "base44", "microsoft", "aws", "google", "cloud", "sponsor"]):
            return ProjectAward(
                name=text_clean,
                award_type=AwardType.SPONSOR,
                sponsor=sponsor_match,
                placement=placement,
                official_source=source_url,
                raw_badge_text=raw_text,
            )

        # Default to Track
        return ProjectAward(
            name=text_clean,
            award_type=AwardType.TRACK,
            placement=placement,
            official_source=source_url,
            raw_badge_text=raw_text,
        )
