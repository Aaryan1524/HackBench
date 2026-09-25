import hashlib
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger("hackbench.ai.cache")

RUBRIC_VERSION = "v1.0.0"


class AICache:
    """
    Caches AI evaluation and synthesis results based on SHA256 of:
    normalized project evidence + rubric version + model configuration.
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path("data/cache/ai")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def compute_cache_key(
        self,
        evidence: str,
        dimension_or_type: str,
        model_version: str,
        rubric_version: str = RUBRIC_VERSION,
    ) -> str:
        raw_key = f"{rubric_version}:{model_version}:{dimension_or_type}:{evidence}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        path = self.cache_dir / f"{cache_key}.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Failed to read cache file {path}: {e}")
        return None

    def set(self, cache_key: str, data: Dict[str, Any]) -> None:
        path = self.cache_dir / f"{cache_key}.json"
        try:
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to write cache file {path}: {e}")
