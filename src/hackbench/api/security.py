import re
import logging
import time
from urllib.parse import urlparse
from typing import Tuple, Optional
from collections import defaultdict

# Re-exported: the URL validation and safe fetch live in hackbench.netsafety (no import cycles).
from ..netsafety import (  # noqa: F401
    BLOCKED_HOSTNAMES, MAX_FETCH_BYTES, UnsafeFetch, is_safe_public_url, safe_fetch_text,
)

logger = logging.getLogger("hackbench.api.security")


def sanitize_untrusted_text(text: str, max_chars: int = 25000) -> str:
    """
    Sanitizes untrusted project evidence (README, Devpost descriptions, comments)
    to neutralize prompt injection attempts and enforce bounded payload sizes.
    """
    if not text:
        return ""

    truncated = text[:max_chars]

    # Neutralize closing delimiter attempts
    neutralized = truncated.replace("</PROJECT_EVIDENCE>", "<\\/PROJECT_EVIDENCE>")
    neutralized = neutralized.replace("</IDEA_DESCRIPTION>", "<\\/IDEA_DESCRIPTION>")
    neutralized = neutralized.replace("```system", "```escaped_system")

    return neutralized


class InMemoryRateLimiter:
    """
    Token-bucket rate limiter tracking requests per IP address.
    """

    MAX_TRACKED_IPS = 10_000

    def __init__(self, requests_per_minute: int = 20):
        self.rate = requests_per_minute
        self.window_seconds = 60.0
        self.requests = defaultdict(list)

    def is_allowed(self, client_ip: str) -> bool:
        now = time.time()
        if len(self.requests) > self.MAX_TRACKED_IPS:
            # Bound memory: forget clients with no activity inside the window.
            self.requests = defaultdict(
                list, {ip: ts for ip, ts in self.requests.items() if ts and now - ts[-1] < self.window_seconds}
            )
        client_history = self.requests[client_ip]

        # Evict timestamps older than 60 seconds
        self.requests[client_ip] = [t for t in client_history if now - t < self.window_seconds]

        if len(self.requests[client_ip]) >= self.rate:
            return False

        self.requests[client_ip].append(now)
        return True



# Repositories may only be cloned from well-known public hosts.
ALLOWED_REPO_HOSTS = {"github.com", "www.github.com", "gitlab.com", "www.gitlab.com", "bitbucket.org", "www.bitbucket.org"}


def is_allowed_repo_url(url: str) -> bool:
    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return False
    return parsed.scheme == "https" and (parsed.hostname or "").lower() in ALLOWED_REPO_HOSTS


def client_ip_for(request, trust_proxy_headers: bool) -> str:
    """
    Real client address for rate limiting. Behind the frontend proxy every request arrives from the
    proxy itself. Only enable trust when the platform in front OVERWRITES or appends to X-Forwarded-For
    (then the rightmost entry is the one it added and cannot be forged). Never enable it behind a proxy
    that passes the header through untouched, such as the Next.js rewrite proxy.
    """
    peer = request.client.host if request.client else "127.0.0.1"
    if trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return peer


class BodySizeLimitMiddleware:
    """Pure ASGI middleware: reject request bodies over max_bytes (declared or streamed) with 413."""

    def __init__(self, app, max_bytes: int = 64 * 1024):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared and declared.isdigit() and int(declared) > self.max_bytes:
            return await self._reject(send)

        received = 0
        too_big = False

        async def limited_receive():
            nonlocal received, too_big
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    too_big = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        started = False

        async def guarded_send(message):
            nonlocal started
            if too_big and not started:
                started = True
                return await self._reject(send)
            if not too_big:
                await send(message)

        return await self.app(scope, limited_receive, guarded_send)

    async def _reject(self, send):
        body = b'{"detail":"Request too large."}'
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
