"""V1 verification: realistic messy input and graceful degradation."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hackbench.ai.idea_extractor import IdeaExtractor
from hackbench.ai.idea_guidance import parse_workflow_steps
from hackbench.ai.prize_matcher import FORBIDDEN_WIN_TERMS, PrizeMatcher
from hackbench.api.server import app


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key in ("CHATGPT_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "JEV_API_KEY"):
        monkeypatch.setenv(key, "")


@pytest.fixture
def client():
    from hackbench.api import server
    server.rate_limiter.requests.clear()  # the limiter is process-wide; isolate each test
    return TestClient(app)


def idea(client, description, techs=None, **extra):
    return client.post("/api/analyze", json={
        "analysis_mode": "idea", "idea": {"description": description, "technologies_of_interest": techs or []}, **extra,
    })


def project(client, **payload):
    return client.post("/api/analyze", json={"analysis_mode": "project", **payload})


# ---------- idea extraction on messy input ----------

def test_user_with_hyphenated_word_is_not_truncated():
    idea_ = IdeaExtractor().extract("An agent that flags fraud for corner-store owners who can't afford a fraud team.")
    assert idea_.target_user == "corner-store owners"


def test_workflow_is_found_when_sentence_has_apostrophes_and_slashes():
    text = ("We're building an agent that watches a small business's Stripe transactions, flags likely fraud, "
            "and texts the owner a one-tap approve/decline.")
    steps = parse_workflow_steps(IdeaExtractor().extract(text).core_workflow)
    assert len(steps) == 3


def test_arrow_workflow_and_singular_verbs():
    steps = parse_workflow_steps("Voice dictation -> goes into the EHR thing")
    assert steps == ["Voice dictation", "Go into the EHR thing"]


def test_single_clause_description_is_not_treated_as_a_workflow():
    assert IdeaExtractor().extract("An app that helps students study better.").core_workflow is None


def test_topic_word_is_not_a_target_user():
    assert IdeaExtractor().extract("something with AI for education").target_user is None


# ---------- prize fit on messy input ----------

def _top_fits(description, techs=None):
    idea_ = IdeaExtractor().extract(description, techs or [])
    return PrizeMatcher().match_prizes(idea_, techs or []).top_fits


def test_one_word_idea_has_no_strong_sponsor_fit():
    fits = _top_fits("game")
    assert not any(f.fit_level.value in ("strong", "very_strong") and f.prize_type != "overall" for f in fits)


def test_hive_audio_is_not_conversational_voice():
    fits = _top_fits("A tool for beekeepers that listens to hive audio, detects queenless colonies, and sends an alert.")
    assert not any("ElevenLabs" in f.award_title and f.fit_level.value in ("strong", "very_strong") for f in fits)


def test_agent_idea_without_google_stack_is_not_a_strong_google_fit():
    fits = _top_fits("An agent that watches transactions, flags fraud, and texts the owner.", ["Stripe"])
    google = [f for f in fits if f.sponsor_name == "Google Cloud"]
    assert all(f.fit_level.value not in ("strong", "very_strong") for f in google)


# ---------- idea-mode API failure cases ----------

@pytest.mark.parametrize("description", ["game", "something with AI for education", "x" * 3])
def test_vague_idea_still_gets_actionable_guidance(client, description):
    r = idea(client, description)
    assert r.status_code == 200
    recs = r.json()["recommendations"]
    assert recs["build_first"].count("→") >= 2
    assert recs["dont_build_yet"] == []


def test_blank_idea_is_a_clear_400(client):
    r = idea(client, "   ")
    assert r.status_code == 400 and "idea" in r.json()["detail"].lower()


def test_unknown_hackathon_falls_back_and_says_so(client):
    r = idea(client, "A tool for beekeepers that listens to hive audio, detects queenless colonies, and sends an alert.",
             event_id="nohackathon:1999")
    assert r.status_code == 200
    assert any("nohackathon:1999" in n for n in r.json()["notes"])


def test_unknown_specific_prize_does_not_crash(client):
    r = idea(client, "A tool for beekeepers that detects queenless colonies from hive audio.",
             prize_targeting_mode="specific", award_id="does_not_exist")
    assert r.status_code == 200


def test_without_ai_provider_idea_says_comparison_is_hidden(client):
    r = idea(client, "A tool for beekeepers that detects queenless colonies from hive audio.")
    assert any("AI reviewer is unavailable" in n for n in r.json()["notes"])


# ---------- project-mode failure cases ----------

def test_empty_project_is_a_clear_400(client):
    r = project(client, input_mode="manual", project={})
    assert r.status_code == 400 and "link" in r.json()["detail"].lower()


def test_private_addresses_are_still_rejected(client):
    r = project(client, github_url="http://127.0.0.1:8000/x")
    assert r.status_code == 400


def test_dead_link_is_skipped_with_a_note_not_rejected(client):
    r = project(client, deployment_url="https://this-domain-should-not-exist-hackbench.example",
                project={"name": "X", "problem": "p", "target_user": "u", "what_it_does": "does a thing for users"})
    assert r.status_code == 200
    assert any("couldn't reach" in n for n in r.json()["notes"])


def test_project_with_no_repository_marks_missing_evidence_as_unavailable(client):
    r = project(client, input_mode="manual", project={
        "name": "FridgeChef", "problem": "College students waste food.", "target_user": "Broke students",
        "what_it_does": "Photographs a fridge and suggests recipes.", "how_it_works": "React and Flask with a vision model.",
    })
    assert r.status_code == 200
    js = r.json()["judge_surface"]
    assert js["demo_strength"]["label"] == "insufficient_evidence"
    assert js["completion_appearance"]["label"] == "insufficient_evidence"


def test_link_only_submission_does_not_rate_everything_weak(client, monkeypatch):
    from hackbench.api import server

    class Repo:
        status = "accessible"; approx_loc = 900; primary_languages = []; test_files_count = 0
        api_routes_count = 0; has_ci = False; todo_fixme_count = 0; deployment_check = None
        readme_excerpt = ""

        class tech_stack:
            frontend_frameworks = backend_frameworks = databases = model_providers = []

    monkeypatch.setattr(server.RepositoryAnalyzer, "analyze_repository", lambda self, **kw: Repo())
    r = project(client, github_url="https://github.com/octocat/Hello-World")
    assert r.status_code == 200
    data = r.json()
    labels = {k: v["label"] for k, v in data["judge_surface"].items()}
    assert set(labels.values()) == {"insufficient_evidence"}
    assert any("no README" in n for n in data["notes"])


def test_unreadable_repository_is_reported(client, monkeypatch):
    from hackbench.api import server

    def boom(self, **kw):
        raise RuntimeError("clone failed")

    monkeypatch.setattr(server.RepositoryAnalyzer, "analyze_repository", boom)
    r = project(client, github_url="https://github.com/octocat/Hello-World")
    assert r.status_code == 200
    assert any("couldn't read the GitHub repository" in n for n in r.json()["notes"])


def test_project_advice_has_no_invented_statistics_or_predictions(client):
    r = project(client, input_mode="manual", project={"name": "X", "problem": "short", "target_user": "u",
                                                        "what_it_does": "does a thing", "how_it_works": "python"})
    body = r.json()
    body.pop("disclaimer")  # the disclaimer says outcomes are NOT predicted
    text = str(body)
    assert "72%" not in text and "400-800" not in text and "predictor" not in text
    for pattern in FORBIDDEN_WIN_TERMS:
        assert not re.search(pattern, text, re.IGNORECASE)


def test_partial_historical_data_degrades(client, monkeypatch):
    from hackbench.ai import idea_guidance
    assert idea_guidance.historical_takeaway({}) is None
    assert idea_guidance.historical_takeaway({"label": "X", "cohort_comparisons": {}}) is None
    assert idea_guidance.load_history_summary(Path("does/not/exist.json")) is None


# ---------- copy audit ----------

def test_user_facing_copy_has_no_internal_jargon():
    src = Path("web/app/page.tsx").read_text() + Path("web/app/layout.tsx").read_text()
    # Rendered text only: JSX text nodes and string literals, minus snake_case code identifiers.
    literals = [a or b for a, b in re.findall(r'>([^<>{}]{3,})<|"([^"\n]{12,})"', src)]
    strings = " ".join(l for l in literals if not re.fullmatch(r"[a-z_]+", l.strip())).lower()
    strings = re.sub(r"\b[a-z]+_[a-z_]+\b", "", strings)
    for bad in ("empirical", "forensic", "invariant", "multi-layer", "deterministic", "model routing",
                "provider confidence", "canonical", "telemetry"):
        assert bad not in strings, bad


def test_offline_ratings_are_never_cached(client):
    """An offline run must not be replayed later when an AI provider becomes available."""
    from hackbench.ai.router import EvaluationRouter
    router = EvaluationRouter()
    kwargs = dict(project_name="CacheProbe", tagline="t", problem="p " * 20, target_user="students",
                  what_it_does="does a thing for students", how_it_works="python", demo_evidence="")
    first = router.evaluate_judge_surface(**kwargs)
    assert any(v.provider == "offline_calibrated" for v in first.values())
    key = router.cache.compute_cache_key(
        evidence="x", dimension_or_type="judge_surface_batch_project",
        model_version=f"{router.jev.model}_{router.gemini.model}_jev0_gpt0", rubric_version="x",
    )
    assert router.cache.get(key) is None


# ---------- pre-ship fixes: filler advice and link-only projects ----------

def _fake_repo(readme):
    class Repo:
        status = "accessible"; approx_loc = 900; primary_languages = []; test_files_count = 0
        api_routes_count = 0; has_ci = False; todo_fixme_count = 0; deployment_check = None
        readme_excerpt = readme

        class tech_stack:
            frontend_frameworks = backend_frameworks = databases = model_providers = []

    return Repo()


def test_no_generic_backup_recording_advice_without_a_live_demo(client):
    r = project(client, input_mode="manual", project={"name": "X", "problem": "short", "target_user": "u",
                                                        "what_it_does": "does a thing", "how_it_works": "python"})
    actions = " ".join(a["action"] for a in r.json()["recommendations"]["next_actions"]).lower()
    assert "backup" not in actions and "wi-fi" not in actions and "60 seconds" not in actions


def test_generic_actions_are_dropped_from_model_output():
    from hackbench.ai.chatgpt import ChatGPTClient, SynthesizedNextAction
    acts = [SynthesizedNextAction(priority=1, action="Fix the fridge photo parsing.", reason="r"),
            SynthesizedNextAction(priority=2, action="Prepare a backup screen recording in case venue Wi-Fi fails.", reason="r")]
    kept = ChatGPTClient._drop_generic_actions(acts, deployment_reachable=False)
    assert [a.action for a in kept] == ["Fix the fridge photo parsing."]
    assert len(ChatGPTClient._drop_generic_actions(acts, deployment_reachable=True)) == 2


def test_link_only_project_uses_readme_as_description(client, monkeypatch):
    from hackbench.api import server
    readme = "# FridgeChef\n" + "FridgeChef photographs your fridge, identifies the ingredients, and suggests dinner recipes for students. " * 3
    monkeypatch.setattr(server.RepositoryAnalyzer, "analyze_repository", lambda self, **kw: _fake_repo(readme))
    r = project(client, github_url="https://github.com/octocat/Hello-World")
    data = r.json()
    labels = {k: v["label"] for k, v in data["judge_surface"].items()}
    assert labels["product_clarity"] != "insufficient_evidence"
    assert labels["problem_clarity"] != "insufficient_evidence"
    assert any("README" in n for n in data["notes"])
    assert data["project"]["tagline"] == "FridgeChef"


def test_link_only_project_without_readme_asks_for_one_sentence(client, monkeypatch):
    from hackbench.api import server
    monkeypatch.setattr(server.RepositoryAnalyzer, "analyze_repository", lambda self, **kw: _fake_repo(""))
    data = project(client, github_url="https://github.com/octocat/Hello-World").json()
    assert any("Add one sentence" in n for n in data["notes"])


def test_one_line_description_lifts_a_link_only_review(client, monkeypatch):
    from hackbench.api import server
    monkeypatch.setattr(server.RepositoryAnalyzer, "analyze_repository", lambda self, **kw: _fake_repo(""))
    data = project(client, github_url="https://github.com/octocat/Hello-World",
                   project={"what_it_does": "Photographs a fridge and suggests dinner recipes for students."}).json()
    assert data["judge_surface"]["product_clarity"]["label"] != "insufficient_evidence"


def test_readme_excerpt_strips_badges_html_and_code():
    from hackbench.collectors.git_repo import RepositoryAnalyzer
    text = "# App\n![badge](x.svg)\n<img src='a'>\n```\nnpm i\n```\n[Docs](http://d)\nDoes a real thing for users.\n---\n"
    out = RepositoryAnalyzer._readme_excerpt(text)
    assert "badge" not in out and "npm i" not in out and "<img" not in out
    assert "Docs" in out and "Does a real thing" in out
