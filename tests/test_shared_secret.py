"""When BACKEND_SHARED_SECRET is set, only callers that know it (our frontend) may use /api."""
import pytest
from fastapi.testclient import TestClient

from hackbench.api import server

SECRET = "s3cret-value-for-tests"
BODY = {"analysis_mode": "idea", "idea": {"description": "A tool for beekeepers that detects queenless colonies from hive audio."}}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key in ("CHATGPT_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "JEV_API_KEY"):
        monkeypatch.setenv(key, "")
    server.rate_limiter.requests.clear()


@pytest.fixture
def secured(monkeypatch):
    monkeypatch.setattr(server, "BACKEND_SHARED_SECRET", SECRET)
    return TestClient(server.app)


def test_no_secret_no_access(secured):
    r = secured.post("/api/analyze", json=BODY)
    assert r.status_code == 401 and r.json() == {"detail": "Unauthorized"}


def test_wrong_secret_no_access(secured):
    for bad in ["", "wrong", SECRET + "x", SECRET[:-1], SECRET.upper()]:
        assert secured.post("/api/analyze", json=BODY, headers={"x-backend-secret": bad}).status_code == 401


def test_prizes_and_every_other_api_path_are_protected_too(secured):
    assert secured.get("/api/events/shellhacks2025:2025/prizes").status_code == 401
    assert secured.get("/api/anything").status_code == 401


def test_correct_secret_works(secured):
    r = secured.post("/api/analyze", json=BODY, headers={"x-backend-secret": SECRET})
    assert r.status_code == 200 and r.json()["analysis_mode"] == "idea"
    assert secured.get("/api/events/shellhacks2025:2025/prizes", headers={"x-backend-secret": SECRET}).status_code == 200


def test_health_stays_open_for_platform_checks_and_leaks_nothing(secured):
    r = secured.get("/health")
    assert r.status_code == 200 and SECRET not in r.text


def test_rate_limit_is_per_visitor_address_from_a_trusted_caller(secured):
    headers = lambda ip: {"x-backend-secret": SECRET, "x-client-ip": ip}
    for _ in range(server.rate_limiter.rate):
        assert secured.post("/api/analyze", json=BODY, headers=headers("203.0.113.5")).status_code == 200
    assert secured.post("/api/analyze", json=BODY, headers=headers("203.0.113.5")).status_code == 429
    # A different visitor is unaffected by the first one's usage.
    assert secured.post("/api/analyze", json=BODY, headers=headers("203.0.113.6")).status_code == 200


def test_client_ip_header_is_ignored_without_the_secret_and_when_malformed(secured):
    r = secured.post("/api/analyze", json=BODY, headers={"x-client-ip": "203.0.113.5"})
    assert r.status_code == 401
    r = secured.post("/api/analyze", json=BODY, headers={"x-backend-secret": SECRET, "x-client-ip": "not-an-ip; DROP"})
    assert r.status_code == 200  # falls back to the peer address instead of trusting junk


def test_without_a_secret_configured_local_development_still_works(monkeypatch):
    monkeypatch.setattr(server, "BACKEND_SHARED_SECRET", "")
    assert TestClient(server.app).post("/api/analyze", json=BODY).status_code == 200
