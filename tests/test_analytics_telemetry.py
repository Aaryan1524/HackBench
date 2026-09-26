"""The backend exposes only safe routing facts for product analytics."""
import pytest
from fastapi.testclient import TestClient

from hackbench.api import server


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key in ("CHATGPT_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "JEV_API_KEY"):
        monkeypatch.setenv(key, "")


@pytest.fixture
def client():
    server.rate_limiter.requests.clear()
    return TestClient(server.app, raise_server_exceptions=False)


IDEA = {"analysis_mode": "idea", "idea": {"description": "A tool for beekeepers that detects queenless colonies from hive audio."}}


class _Eval:
    def __init__(self, provider, label="moderate", fallback_reason=None):
        self.provider, self.label, self.fallback_reason = provider, label, fallback_reason


def test_telemetry_contains_only_booleans_and_one_enum(client):
    t = client.post("/api/analyze", json=IDEA).json()["telemetry"]
    assert set(t) == {"jev_used", "gemini_used", "fallback_used", "result_quality"}
    assert all(isinstance(t[k], bool) for k in ("jev_used", "gemini_used", "fallback_used"))
    assert t["result_quality"] in ("full", "partial")


def test_project_telemetry_is_present_too(client):
    r = client.post("/api/analyze", json={"analysis_mode": "project", "project": {"name": "X", "problem": "p", "target_user": "u", "what_it_does": "does a thing", "how_it_works": "python"}})
    assert set(r.json()["telemetry"]) == {"jev_used", "gemini_used", "fallback_used", "result_quality"}


def test_no_provider_means_fallback_and_partial(client):
    t = client.post("/api/analyze", json=IDEA).json()["telemetry"]
    assert t["fallback_used"] is True and t["gemini_used"] is False and t["jev_used"] is False
    assert t["result_quality"] == "partial"


def test_routing_flags_for_each_provider_combination():
    f = server._routing_telemetry
    # ChatGPT only (no Jev): live, not a fallback.
    t = f({"a": _Eval("chatgpt", fallback_reason="jev_key_not_configured")}, "gpt-x", [], True)
    assert (t["jev_used"], t["gemini_used"], t["fallback_used"], t["result_quality"]) == (False, True, False, "full")
    # Jev used and trusted.
    t = f({"a": _Eval("jev")}, "gpt-x", [], True)
    assert (t["jev_used"], t["fallback_used"]) == (True, False)
    # Jev low confidence handed to ChatGPT counts as fallback.
    t = f({"a": _Eval("chatgpt", fallback_reason="jev_confidence_below_threshold")}, "gpt-x", [], True)
    assert t["fallback_used"] is True
    # Live model failed and the local synthesis took over.
    t = f({"a": _Eval("chatgpt")}, "chatgpt-local-calibrated", [], True)
    assert t["fallback_used"] is True
    # Notes or missing evidence make a result partial.
    assert f({"a": _Eval("chatgpt")}, "gpt-x", ["note"], True)["result_quality"] == "partial"
    assert f({"a": _Eval("chatgpt", label="insufficient_evidence")}, "gpt-x", [], False)["result_quality"] == "partial"
    assert f({"a": _Eval("chatgpt", label="insufficient_evidence")}, "gpt-x", [], True)["result_quality"] == "full"


def test_telemetry_leaks_nothing_else(client):
    body = client.post("/api/analyze", json=IDEA).json()["telemetry"]
    assert "chatgpt" not in str(body).lower() and "key" not in str(body).lower()


def test_unexpected_errors_return_a_generic_body_and_stage_header(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("secret user text: quokka")

    monkeypatch.setattr(server, "_routing_telemetry", boom)
    r = client.post("/api/analyze", json=IDEA)
    assert r.status_code == 500
    assert r.headers["x-failure-stage"] == "unknown"
    assert "quokka" not in r.text


def test_busy_response_names_its_stage(client):
    slots = [server._clone_slots.acquire(blocking=False) for _ in range(server.MAX_CONCURRENT_CLONES)]
    try:
        r = client.post("/api/analyze", json={"analysis_mode": "project", "github_url": "https://github.com/octocat/Hello-World"})
        assert r.status_code == 503 and r.headers["x-failure-stage"] == "repo_analysis"
    finally:
        for got in slots:
            if got:
                server._clone_slots.release()
