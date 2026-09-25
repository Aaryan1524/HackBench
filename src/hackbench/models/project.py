from datetime import datetime, timezone
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from .provenance import ProvenanceRecord


class ProjectLink(BaseModel):
    url: str
    link_type: str  # github, gitlab, youtube, figma, deployment, devpost, doc, other
    title: str = ""


class ProjectTeamMember(BaseModel):
    name: str
    devpost_username: str = ""
    profile_url: str = ""
    role: str = ""


class DescriptionSections(BaseModel):
    problem_statement: str = ""
    inspiration: str = ""
    what_it_does: str = ""
    how_it_was_built: str = ""
    challenges: str = ""
    accomplishments: str = ""
    lessons_learned: str = ""
    future_plans: str = ""
    raw_full_text: str = ""


class RawProject(BaseModel):
    project_id: str
    slug: str
    title: str
    devpost_url: str
    gallery_url: str = ""
    tagline: str = ""
    description_sections: DescriptionSections = Field(default_factory=DescriptionSections)
    tech_tags: List[str] = Field(default_factory=list)
    links: List[ProjectLink] = Field(default_factory=list)
    github_urls: List[str] = Field(default_factory=list)
    demo_urls: List[str] = Field(default_factory=list)
    deployment_urls: List[str] = Field(default_factory=list)
    team_members: List[ProjectTeamMember] = Field(default_factory=list)
    team_size: int = 1
    screenshots: List[str] = Field(default_factory=list)
    thumbnail_url: str = ""
    sponsor_technologies_mentioned: List[str] = Field(default_factory=list)
    submission_timestamp: Optional[str] = None
    gallery_winner_badge: bool = False
    raw_winner_awards_text: List[str] = Field(default_factory=list)
    provenance: List[ProvenanceRecord] = Field(default_factory=list)
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
