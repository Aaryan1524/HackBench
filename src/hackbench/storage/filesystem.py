import os
from pathlib import Path
from typing import Optional


class StorageManager:
    """
    Manages structured file storage according to the non-overwrite invariant:
    data/
      raw/<event_slug>/<year>/
        event/
        projects/
        repos/
        outcomes_sealed/
      processed/<event_slug>/<year>/
        blind_bundles/
        blind_evaluations/
        outcomes/
        analysis/
    """

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            self.base_dir = Path(os.getcwd()) / "data"
        else:
            self.base_dir = Path(base_dir)

    def get_raw_dir(self, event_slug: str, year: int) -> Path:
        p = self.base_dir / "raw" / event_slug / str(year)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_raw_projects_dir(self, event_slug: str, year: int) -> Path:
        p = self.get_raw_dir(event_slug, year) / "projects"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_raw_repos_dir(self, event_slug: str, year: int) -> Path:
        p = self.get_raw_dir(event_slug, year) / "repos"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_raw_event_dir(self, event_slug: str, year: int) -> Path:
        p = self.get_raw_dir(event_slug, year) / "event"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_sealed_outcomes_dir(self, event_slug: str, year: int) -> Path:
        p = self.get_raw_dir(event_slug, year) / "outcomes_sealed"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_processed_dir(self, event_slug: str, year: int) -> Path:
        p = self.base_dir / "processed" / event_slug / str(year)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_blind_bundles_dir(self, event_slug: str, year: int) -> Path:
        p = self.get_processed_dir(event_slug, year) / "blind_bundles"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_blind_evaluations_dir(self, event_slug: str, year: int) -> Path:
        p = self.get_processed_dir(event_slug, year) / "blind_evaluations"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_analysis_dir(self, event_slug: str, year: int) -> Path:
        p = self.get_processed_dir(event_slug, year) / "analysis"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_reports_dir(self, event_slug: str, year: int) -> Path:
        p = Path(os.getcwd()) / "reports" / f"{event_slug}_{year}"
        p.mkdir(parents=True, exist_ok=True)
        return p
