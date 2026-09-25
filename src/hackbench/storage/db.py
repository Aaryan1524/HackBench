import json
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from ..models import (
    HackathonEvent,
    RawProject,
    RepositoryMetrics,
    BlindProjectBundle,
    BlindProjectEvaluation,
    ProjectOutcome,
    EventForensicAnalysis,
)


class DatabaseManager:
    """
    DuckDB / SQLite database manager for structured analytical queries.
    Stores events, raw projects, repositories, blind evaluations, sealed outcomes, and forensics.
    """

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            self.db_path = Path("data") / "forensics.db"
        else:
            self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Events
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    slug TEXT,
                    year INTEGER,
                    name TEXT,
                    event_url TEXT,
                    devpost_url TEXT,
                    data_json TEXT,
                    ingested_at TIMESTAMP,
                    PRIMARY KEY (slug, year)
                )
            """)
            # Projects
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT,
                    event_slug TEXT,
                    year INTEGER,
                    slug TEXT,
                    title TEXT,
                    devpost_url TEXT,
                    has_repo BOOLEAN,
                    has_demo BOOLEAN,
                    team_size INTEGER,
                    tech_tags TEXT,
                    data_json TEXT,
                    PRIMARY KEY (project_id, event_slug, year)
                )
            """)
            # Repositories
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS repositories (
                    project_id TEXT,
                    event_slug TEXT,
                    year INTEGER,
                    repo_url TEXT,
                    status TEXT,
                    approx_loc INTEGER,
                    file_count INTEGER,
                    total_commits INTEGER,
                    commits_in_window INTEGER,
                    test_files_count INTEGER,
                    has_ci BOOLEAN,
                    has_docker BOOLEAN,
                    data_json TEXT,
                    PRIMARY KEY (project_id, event_slug, year)
                )
            """)
            # Blind Bundles
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS blind_bundles (
                    project_id TEXT,
                    event_slug TEXT,
                    year INTEGER,
                    bundle_sha256 TEXT,
                    bundle_json TEXT,
                    created_at TIMESTAMP,
                    PRIMARY KEY (project_id, event_slug, year)
                )
            """)
            # Blind Evaluations (IMMUTABLE)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS blind_evaluations (
                    project_id TEXT,
                    event_slug TEXT,
                    year INTEGER,
                    bundle_sha256 TEXT,
                    composite_quality_score REAL,
                    completion_score REAL,
                    technical_depth_score REAL,
                    originality_score REAL,
                    product_coherence_score REAL,
                    evaluator_agreement TEXT,
                    disputed_dimensions TEXT,
                    evaluation_sha256 TEXT,
                    evaluation_json TEXT,
                    sealed_at TIMESTAMP,
                    is_frozen BOOLEAN,
                    PRIMARY KEY (project_id, event_slug, year)
                )
            """)
            # Outcomes (Sealed until Stage B reveal)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS outcomes (
                    project_id TEXT,
                    event_slug TEXT,
                    year INTEGER,
                    is_winner BOOLEAN,
                    is_overall_winner BOOLEAN,
                    is_sponsor_winner BOOLEAN,
                    is_track_winner BOOLEAN,
                    awards_json TEXT,
                    unsealed_at TIMESTAMP,
                    PRIMARY KEY (project_id, event_slug, year)
                )
            """)
            # Forensic Project Records (Stage B comparison)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS forensic_records (
                    project_id TEXT,
                    event_slug TEXT,
                    year INTEGER,
                    is_winner BOOLEAN,
                    mismatch_classification TEXT,
                    composite_score REAL,
                    mismatch_explanation TEXT,
                    record_json TEXT,
                    PRIMARY KEY (project_id, event_slug, year)
                )
            """)
            conn.commit()

    def save_event(self, event: HackathonEvent):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO events (slug, year, name, event_url, devpost_url, data_json, ingested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.slug,
                    event.year,
                    event.name,
                    event.event_url,
                    event.devpost_url,
                    event.model_dump_json(),
                    event.ingested_at.isoformat(),
                ),
            )
            conn.commit()

    def save_project(self, event_slug: str, year: int, project: RawProject):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO projects (
                    project_id, event_slug, year, slug, title, devpost_url,
                    has_repo, has_demo, team_size, tech_tags, data_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project.project_id,
                    event_slug,
                    year,
                    project.slug,
                    project.title,
                    project.devpost_url,
                    bool(project.github_urls),
                    bool(project.demo_urls),
                    project.team_size,
                    json.dumps(project.tech_tags),
                    project.model_dump_json(),
                ),
            )
            conn.commit()

    def save_repository_metrics(self, event_slug: str, year: int, project_id: str, repo: RepositoryMetrics):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO repositories (
                    project_id, event_slug, year, repo_url, status, approx_loc,
                    file_count, total_commits, commits_in_window, test_files_count,
                    has_ci, has_docker, data_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    event_slug,
                    year,
                    repo.repo_url,
                    repo.status,
                    repo.approx_loc,
                    repo.file_count,
                    repo.git_timeline.total_commits,
                    repo.git_timeline.commits_in_window,
                    repo.test_files_count,
                    repo.has_ci,
                    repo.has_docker,
                    repo.model_dump_json(),
                ),
            )
            conn.commit()

    def save_blind_bundle(self, event_slug: str, year: int, bundle: BlindProjectBundle):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO blind_bundles (
                    project_id, event_slug, year, bundle_sha256, bundle_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    bundle.project_id,
                    event_slug,
                    year,
                    bundle.bundle_sha256,
                    bundle.model_dump_json(),
                    bundle.created_at.isoformat(),
                ),
            )
            conn.commit()

    def save_blind_evaluation(self, event_slug: str, year: int, evaluation: BlindProjectEvaluation):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO blind_evaluations (
                    project_id, event_slug, year, bundle_sha256, composite_quality_score,
                    completion_score, technical_depth_score, originality_score,
                    product_coherence_score, evaluator_agreement, disputed_dimensions,
                    evaluation_sha256, evaluation_json, sealed_at, is_frozen
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation.project_id,
                    event_slug,
                    year,
                    evaluation.bundle_sha256,
                    evaluation.composite_quality_score,
                    evaluation.aggregated_scores.get("completion", 0.0),
                    evaluation.aggregated_scores.get("technical_depth", 0.0),
                    evaluation.aggregated_scores.get("originality", 0.0),
                    evaluation.aggregated_scores.get("product_coherence", 0.0),
                    evaluation.evaluator_agreement_status,
                    json.dumps(evaluation.disputed_dimensions),
                    evaluation.evaluation_sha256,
                    evaluation.model_dump_json(),
                    evaluation.sealed_at.isoformat(),
                    evaluation.is_frozen,
                ),
            )
            conn.commit()

    def save_outcome(self, event_slug: str, year: int, outcome: ProjectOutcome):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO outcomes (
                    project_id, event_slug, year, is_winner, is_overall_winner,
                    is_sponsor_winner, is_track_winner, awards_json, unsealed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    outcome.project_id,
                    event_slug,
                    year,
                    outcome.is_winner,
                    outcome.is_overall_winner,
                    outcome.is_sponsor_winner,
                    outcome.is_track_winner,
                    json.dumps([a.model_dump() for a in outcome.awards]),
                    outcome.unsealed_at.isoformat() if outcome.unsealed_at else None,
                ),
            )
            conn.commit()
