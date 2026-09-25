import re
import ipaddress
import socket
import logging
from urllib.parse import urlparse
from typing import Tuple, Optional
import time
from collections import defaultdict

logger = logging.getLogger("hackbench.api.security")

# Cloud metadata addresses to explicitly block
BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "169.254.169.254",
    "metadata",
    "instance-data",
}

# Maximum allowed download size for external web fetches (5 MB)
MAX_FETCH_BYTES = 5 * 1024 * 1024


def is_safe_public_url(url: str) -> Tuple[bool, str]:
    """
    Validates that a URL is a safe public HTTP/HTTPS URL, preventing SSRF attacks
    targeting internal networks, localhost, private IP ranges (RFC1918),
    cloud metadata endpoints, and non-HTTP protocols.
    """
    if not url or not isinstance(url, str):
        return False, "URL must be a non-empty string."

    url = url.strip()

    # Block dangerous schemes
    if url.startswith("file://") or url.startswith("gopher://") or url.startswith("ftp://"):
        return False, "Unsupported protocol: only http and https are permitted."

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Malformed URL: {e}"

    if parsed.scheme.lower() not in ("http", "https"):
        return False, "URL scheme must be http or https."

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False, "URL must contain a valid hostname."

    if hostname in BLOCKED_HOSTNAMES:
        return False, f"Access to '{hostname}' is forbidden."

    # Resolve IP address to detect private or loopback ranges
    try:
        # Resolve all IPs for hostname
        addr_info = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)

            if ip.is_loopback:
                return False, f"Loopback address '{ip_str}' is forbidden."
            if ip.is_private:
                return False, f"Private network address '{ip_str}' is forbidden."
            if ip.is_link_local:
                return False, f"Link-local address '{ip_str}' is forbidden."
            if ip.is_multicast:
                return False, f"Multicast address '{ip_str}' is forbidden."
            if ip.is_reserved:
                return False, f"Reserved address '{ip_str}' is forbidden."
            if str(ip) == "169.254.169.254":
                return False, "Cloud metadata endpoint is strictly forbidden."
    except socket.gaierror:
        # Hostname could not be resolved
        return False, f"Could not resolve hostname '{hostname}'."
    except Exception as e:
        return False, f"DNS validation error: {e}"

    return True, "URL is safe."


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
    neutralized = neutralized.replace("```system", "```escaped_system")

    return neutralized


class InMemoryRateLimiter:
    """
    Token-bucket rate limiter tracking requests per IP address.
    """

    def __init__(self, requests_per_minute: int = 20):
        self.rate = requests_per_minute
        self.window_seconds = 60.0
        self.requests = defaultdict(list)

    def is_allowed(self, client_ip: str) -> bool:
        now = time.time()
        client_history = self.requests[client_ip]

        # Evict timestamps older than 60 seconds
        self.requests[client_ip] = [t for t in client_history if now - t < self.window_seconds]

        if len(self.requests[client_ip]) >= self.rate:
            return False

        self.requests[client_ip].append(now)
        return True
