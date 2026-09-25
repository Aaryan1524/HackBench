import re
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from ..models import (
    RawProject,
    RepositoryMetrics,
    BlindProjectBundle,
    BlindDemoSummary,
)

logger = logging.getLogger("hackbench.blind.bundler")

# Regex to scrub any winner / award mentions that hackers may have added post-event
WINNER_SCRUB_PATTERNS = [
    r"\bwinner\s+of\b[^\.\n]*",
    r"\bwon\s+(?:1st|2nd|3rd|first|second|third|best)[^\.\n]*",
    r"\b(?:1st|2nd|3rd)\s+place\s+winner[^\.\n]*",
    r"\bawarded\s+[^\.\n]*",
    r"\bprize\s+winner[^\.\n]*",
    r"\bfinalist\s+at[^\.\n]*",
    r"\bmlh\s+winner[^\.\n]*",
]


class BlindBundleCreator:
    """
    Creates sanitized, sealed BlindProjectBundle instances.
    STRICT INVARIANT:
    All winner information, badges, placement, and award names are purged.
    """

    def sanitize_text(self, text: str) -> str:
        if not text:
            return ""
        sanitized = text
        for pattern in WINNER_SCRUB_PATTERNS:
            sanitized = re.sub(pattern, "[OUTCOME_SCRUBBED]", sanitized, flags=re.IGNORECASE)
        return sanitized.strip()

    def create_bundle(
        self,
        project: RawProject,
        repo_metrics: Optional[RepositoryMetrics] = None,
    ) -> BlindProjectBundle:
        # Sanitize descriptions
        sec = project.description_sections
        clean_problem = self.sanitize_text(sec.problem_statement)
        clean_inspiration = self.sanitize_text(sec.inspiration)
        clean_what = self.sanitize_text(sec.what_it_does)
        clean_how = self.sanitize_text(sec.how_it_was_built)
        clean_challenges = self.sanitize_text(sec.challenges)
        clean_accomplishments = self.sanitize_text(sec.accomplishments)
        clean_lessons = self.sanitize_text(sec.lessons_learned)
        clean_future = self.sanitize_text(sec.future_plans)
        clean_tagline = self.sanitize_text(project.tagline)

        # Parse demo summary
        demo_summary = BlindDemoSummary()
        video_links = [u for u in project.demo_urls if any(p in u for p in ["youtube", "youtu.be", "vimeo", "loom"])]
        if video_links:
            demo_summary.has_video_demo = True
            demo_summary.video_url = video_links[0]
            if "youtube" in video_links[0] or "youtu.be" in video_links[0]:
                demo_summary.video_platform = "youtube"
            elif "vimeo" in video_links[0]:
                demo_summary.video_platform = "vimeo"
            elif "loom" in video_links[0]:
                demo_summary.video_platform = "loom"

        deploy_links = project.deployment_urls or [
            link.url for link in project.links if link.link_type == "deployment"
        ]
        if deploy_links:
            demo_summary.has_live_deployment = True
            demo_summary.deployment_url = deploy_links[0]
            if repo_metrics and repo_metrics.deployment_check:
                demo_summary.deployment_reachable = repo_metrics.deployment_check.is_reachable

        if any("figma" in u for u in project.demo_urls) or any("slide" in u.lower() for u in project.demo_urls):
            demo_summary.has_slide_deck = True

        # Construct bundle
        bundle = BlindProjectBundle(
            project_id=project.project_id,
            slug=project.slug,
            title=project.title,
            tagline=clean_tagline,
            problem_statement=clean_problem,
            inspiration=clean_inspiration,
            what_it_does=clean_what,
            how_it_was_built=clean_how,
            challenges=clean_challenges,
            accomplishments=clean_accomplishments,
            lessons_learned=clean_lessons,
            future_plans=clean_future,
            tech_tags=project.tech_tags,
            team_size=project.team_size,
            repository_metrics=repo_metrics,
            demo_summary=demo_summary,
            sponsor_technologies_mentioned=project.sponsor_technologies_mentioned,
            bundle_sha256="",
            created_at=datetime.now(timezone.utc),
        )

        # Compute deterministic SHA256 of the bundle content
        bundle_content = bundle.model_dump_json(exclude={"bundle_sha256", "created_at"})
        bundle.bundle_sha256 = hashlib.sha256(bundle_content.encode("utf-8")).hexdigest()

        return bundle

    def save_bundle(self, bundle: BlindProjectBundle, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        bundle_file = output_dir / f"{bundle.project_id}.json"
        bundle_file.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
        return bundle_file
