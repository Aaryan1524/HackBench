"""
Network safety helpers shared by the API and the collectors: public-URL validation and a hardened fetch.
Kept free of any other HackBench imports so both sides can use it without import cycles.
"""
import ipaddress
import logging
import socket
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("hackbench.netsafety")

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


_DNS_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="dns")
DNS_TIMEOUT_SECONDS = 3.0


def _resolve(hostname: str):
    """getaddrinfo with a deadline. Raises socket.gaierror on timeout so callers treat it as unresolvable."""
    future = _DNS_POOL.submit(socket.getaddrinfo, hostname, None)
    try:
        return future.result(timeout=DNS_TIMEOUT_SECONDS)
    except FutureTimeout:
        future.cancel()
        raise socket.gaierror("DNS lookup timed out")


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

    if parsed.username or parsed.password:
        return False, "URLs with embedded credentials are not allowed."

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False, "URL must contain a valid hostname."

    if hostname in BLOCKED_HOSTNAMES:
        return False, f"Access to '{hostname}' is forbidden."

    # Resolve IP address to detect private or loopback ranges
    try:
        # Resolve all IPs for hostname (with a deadline: a hostile DNS server must not be able to stall a worker)
        addr_info = _resolve(hostname)
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




class UnsafeFetch(Exception):
    """A fetch was refused (internal address, too many redirects, too large, too slow). Message is safe to log, not to show."""


def _ip_is_public(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    return not (ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def safe_fetch_text(
    url: str,
    timeout: float = 6.0,
    max_bytes: int = 200_000,
    max_redirects: int = 3,
    total_deadline: float = 10.0,
    headers: Optional[dict] = None,
    transport=None,
) -> Tuple[int, str, str]:
    """
    GET a user-supplied public URL without becoming a proxy into our own network.

    - Every hop, including each redirect target, is validated as a public http(s) URL.
    - The address actually connected to is checked too (defeats DNS rebinding between check and connect).
    - Bodies are cut off at max_bytes and the whole fetch has a wall-clock deadline.
    Returns (status_code, text, final_url). Raises UnsafeFetch; never leaks the server's error text.
    """
    import httpx
    from urllib.parse import urljoin

    started = time.monotonic()
    current = url
    for _hop in range(max_redirects + 1):
        ok, _msg = is_safe_public_url(current)
        if not ok:
            raise UnsafeFetch("blocked address")
        if time.monotonic() - started > total_deadline:
            raise UnsafeFetch("deadline")
        try:
            with httpx.Client(follow_redirects=False, timeout=timeout, headers=headers or {}, transport=transport) as client:
                with client.stream("GET", current) as resp:
                    stream = resp.extensions.get("network_stream")
                    server_addr = stream.get_extra_info("server_addr") if stream is not None else None
                    if server_addr and not _ip_is_public(str(server_addr[0])):
                        raise UnsafeFetch("connected to a non-public address")
                    if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                        current = urljoin(current, resp.headers["location"])
                        continue
                    chunks, size = [], 0
                    for chunk in resp.iter_bytes():
                        size += len(chunk)
                        chunks.append(chunk)
                        if size >= max_bytes or time.monotonic() - started > total_deadline:
                            break
                    body = b"".join(chunks)[:max_bytes]
                    return resp.status_code, body.decode(resp.encoding or "utf-8", errors="replace"), current
        except UnsafeFetch:
            raise
        except Exception as e:  # network errors: report the class only
            raise UnsafeFetch(f"request failed: {type(e).__name__}")
    raise UnsafeFetch("too many redirects")
