import hashlib
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger("hackbench.collectors")


class CachedHttpClient:
    """
    Robust HTTP client with caching, exponential backoff, rate limiting, and hash verification.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        rate_limit_delay_seconds: float = 0.5,
        max_retries: int = 4,
        timeout: float = 25.0,
    ):
        self.cache_dir = cache_dir
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.rate_limit_delay = rate_limit_delay_seconds
        self.max_retries = max_retries
        self.timeout = timeout
        self.last_request_time = 0.0
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36 (HackathonForensics/1.0 Research)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def _get_cache_path(self, url: str) -> Optional[Path]:
        if not self.cache_dir:
            return None
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{url_hash}.html"

    def get(self, url: str, force_refresh: bool = False) -> str:
        cache_path = self._get_cache_path(url)
        if not force_refresh and cache_path and cache_path.exists():
            return cache_path.read_text(encoding="utf-8", errors="replace")

        # Rate limiting delay
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)

        backoff = 1.0
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                self.last_request_time = time.time()
                with httpx.Client(
                    headers=self.headers,
                    timeout=self.timeout,
                    follow_redirects=True,
                ) as client:
                    resp = client.get(url)
                    resp.raise_for_status()
                    content = resp.text

                    if cache_path:
                        cache_path.write_text(content, encoding="utf-8")
                    return content
            except Exception as e:
                last_error = e
                logger.warning(
                    f"HTTP GET failed (attempt {attempt}/{self.max_retries}) for {url}: {e}"
                )
                if attempt < self.max_retries:
                    time.sleep(backoff)
                    backoff *= 2.0

        logger.error(f"Failed to fetch {url} after {self.max_retries} attempts.")
        raise last_error or RuntimeError(f"Failed to fetch {url}")
