from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from .provenance import ProvenanceRecord


class TechStackDetection(BaseModel):
    frontend_frameworks: List[str] = Field(default_factory=list)
    backend_frameworks: List[str] = Field(default_factory=list)
    databases: List[str] = Field(default_factory=list)
    ai_ml_libraries: List[str] = Field(default_factory=list)
    model_providers: List[str] = Field(default_factory=list)
    cloud_devops: List[str] = Field(default_factory=list)
    third_party_apis: List[str] = Field(default_factory=list)
    hardware_components: List[str] = Field(default_factory=list)
    package_dependencies: List[str] = Field(default_factory=list)


class GitCommitTimeline(BaseModel):
    total_commits: int = 0
    commits_in_window: int = 0
    first_commit_time: Optional[datetime] = None
    last_commit_time: Optional[datetime] = None
    commit_timestamps: List[datetime] = Field(default_factory=list)
    late_rewrites_detected: bool = False
    deadline_crunch_ratio: float = 0.0  # ratio of commits in final 25% of hackathon
    final_stage_focus: str = "unknown"  # "features", "integration", "debugging", "polish", "docs", "squashed"
    history_is_squashed_or_minimal: bool = False
    contributor_count: int = 0
    contributors: List[str] = Field(default_factory=list)


class DeploymentCheck(BaseModel):
    url: str
    is_reachable: bool = False
    status_code: Optional[int] = None
    response_time_ms: Optional[float] = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RepositoryMetrics(BaseModel):
    repo_url: str
    status: str = "accessible"  # accessible, private, not_found, empty, failed_clone
    default_branch: str = "main"
    file_count: int = 0
    approx_loc: int = 0
    loc_by_language: Dict[str, int] = Field(default_factory=dict)
    primary_languages: List[str] = Field(default_factory=list)
    tech_stack: TechStackDetection = Field(default_factory=TechStackDetection)
    git_timeline: GitCommitTimeline = Field(default_factory=GitCommitTimeline)
    test_files_count: int = 0
    test_frameworks: List[str] = Field(default_factory=list)
    has_ci: bool = False
    ci_configs: List[str] = Field(default_factory=list)
    has_docker: bool = False
    has_env_template: bool = False
    readme_size_bytes: int = 0
    has_architecture_docs: bool = False
    api_routes_count: int = 0
    db_migrations_or_schema_count: int = 0
    mock_data_detected: bool = False
    mock_data_indicators: List[str] = Field(default_factory=list)
    todo_fixme_count: int = 0
    boilerplate_detected: bool = False
    boilerplate_indicators: List[str] = Field(default_factory=list)
    deployment_check: Optional[DeploymentCheck] = None
    consistency_with_claims: str = "unverifiable"  # consistent, partial, inconsistent, unverifiable
    consistency_explanation: str = ""
    actual_integrations_found: List[str] = Field(default_factory=list)
    readme_claims_unsupported_by_code: List[str] = Field(default_factory=list)
    provenance: List[ProvenanceRecord] = Field(default_factory=list)
