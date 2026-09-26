"""Project reviews are judged against the challenge the user chose, using that challenge's own description."""
import pytest
from fastapi.testclient import TestClient

from hackbench.ai.baselines import CURRENT_EVENT_ID, load_prizes
from hackbench.ai.chatgpt import ChatGPTClient
from hackbench.api import server

REPO = "https://github.com/someone/Claude-Sentinel"
SENTINEL_README = (
    "# Claude Sentinel\nA small Python and shell utility that watches for the moment your Claude usage limit resets "
    "and sends you a desktop notification, so you know when you can start working with Claude again. "
    "Install with a shell script and run it in the background. It polls the reset time and notifies you once."
)
GRID_README = (
    "# GridSync\nCompares the public future construction plans of two power utilities in neighboring states and flags "
    "where their planned work overlaps, either because projects are physically close or scheduled around the same time, "
    "so utilities can coordinate and share crews and equipment."
)


def prize_id(part):
    return next(p.prize_id for p in load_prizes(CURRENT_EVENT_ID)[0] if part in p.title)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key in ("CHATGPT_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "JEV_API_KEY"):
        monkeypatch.setenv(key, "")
    server.rate_limiter.requests.clear()


@pytest.fixture
def client():
    return TestClient(server.app)


def fake_repo(readme):
    class Repo:
        status = "accessible"; approx_loc = 730; primary_languages = ["Python", "Shell"]; test_files_count = 0
        api_routes_count = 0; has_ci = False; todo_fixme_count = 0; deployment_check = None
        readme_excerpt = readme

        class tech_stack:
            frontend_frameworks = backend_frameworks = databases = model_providers = []

    return Repo()


def review(client, monkeypatch, readme, award="GridLock", **extra):
    monkeypatch.setattr(server.RepositoryAnalyzer, "analyze_repository", lambda self, **kw: fake_repo(readme))
    body = {"analysis_mode": "project", "github_url": REPO, "event_id": "shellhacks2025:2025",
            "prize_event_id": CURRENT_EVENT_ID, "award_id": prize_id(award), **extra}
    r = client.post("/api/analyze", json=body)
    assert r.status_code == 200
    return r.json()


def test_a_project_unrelated_to_the_challenge_is_reported_as_a_poor_match(client, monkeypatch):
    r = review(client, monkeypatch, SENTINEL_README)
    fit = r["prize_fits"]["top_fits"][0]
    assert "GridLock" in fit["award_title"] and fit["fit_level"] in ("weak", "very_weak")
    assert r["criteria_alignment"]["alignment_level"] in ("weak", "very_weak")


def test_the_heading_and_criteria_are_the_real_challenge_not_a_prettified_id(client, monkeypatch):
    r = review(client, monkeypatch, SENTINEL_README)
    ca = r["criteria_alignment"]
    assert ca["target_award"] == "Sperry Tech — The GridLock Challenge"
    assert "utilities" in ca["criteria_summary"].lower()
    assert "Overall excellence" not in ca["criteria_summary"]
    assert ca["sponsor_requirements"] == "Sperry Tech"
    assert "shellhacks2026" not in ca["target_award"].lower()


def test_a_poor_match_points_to_closer_documented_fits_that_are_actually_better(client, monkeypatch):
    r = review(client, monkeypatch, SENTINEL_README)
    fits = r["prize_fits"]["top_fits"]
    order = {"very_strong": 5, "strong": 4, "moderate": 3, "weak": 2, "very_weak": 1}
    assert len(fits) <= 3
    for alt in fits[1:]:
        assert order[alt["fit_level"]] >= 3 and order[alt["fit_level"]] > order[fits[0]["fit_level"]]
        assert "GridLock" not in alt["award_title"]
    if len(fits) > 1:
        assert "Closer documented fits" in r["prize_fits"]["summary"]


def test_a_project_that_matches_the_challenge_scores_well(client, monkeypatch):
    r = review(client, monkeypatch, GRID_README)
    fit = r["prize_fits"]["top_fits"][0]
    assert fit["fit_level"] in ("strong", "very_strong", "moderate")
    assert len(r["prize_fits"]["top_fits"]) == 1  # nothing closer to suggest


def test_the_reviewer_is_given_the_real_challenge_and_the_computed_fit(client, monkeypatch):
    seen = {}
    real = ChatGPTClient.synthesize_report

    def spy(self, **kw):
        seen.update(kw)
        return real(self, **kw)

    monkeypatch.setattr(ChatGPTClient, "synthesize_report", spy)
    review(client, monkeypatch, SENTINEL_README)
    ca = seen["criteria_alignment"]
    assert ca["award_title"] == "Sperry Tech — The GridLock Challenge"
    assert "utilities" in ca["criteria"].lower()
    assert ca["prize_fit"]["fit_level"] in ("weak", "very_weak")
    assert ca["prize_fit"]["why_it_may_not_fit"]
    assert "Target Award: Sperry Tech — The GridLock Challenge" in seen["untrusted_evidence"]


def test_readme_only_submissions_tell_the_reviewer_blank_fields_are_not_gaps(client, monkeypatch):
    seen = {}
    real = ChatGPTClient.synthesize_report
    monkeypatch.setattr(ChatGPTClient, "synthesize_report", lambda self, **kw: (seen.update(kw), real(self, **kw))[1])
    review(client, monkeypatch, SENTINEL_README)
    assert "Blank Problem, User and Tagline fields are not gaps" in seen["untrusted_evidence"]


def test_the_prompt_forbids_manufacturing_a_connection_to_a_challenge():
    from pathlib import Path
    src = Path("src/hackbench/ai/chatgpt.py").read_text()
    assert "NEVER advise adding text, docs or features merely to manufacture a connection" in src
    assert "closer_fits" in src


def test_the_project_is_named_after_its_repository(client, monkeypatch):
    r = review(client, monkeypatch, SENTINEL_README)
    assert r["project"]["name"] == "Claude Sentinel"


def test_an_explicit_name_is_kept(client, monkeypatch):
    r = review(client, monkeypatch, SENTINEL_README, project={"name": "My Own Name"})
    assert r["project"]["name"] == "My Own Name"


@pytest.mark.parametrize("url, expected", [
    ("https://github.com/owner/Claude-Sentinel", "Claude Sentinel"),
    ("https://github.com/owner/my_cool.app/tree/main/src", "my cool.app"),
    ("https://github.com/owner/repo.git", "repo"),
    ("https://github.com/owner", "owner"),
])
def test_repo_name_extraction(url, expected):
    assert server._project_name_from_repo_url(url) == expected


def test_unknown_or_missing_prize_does_not_break_a_review(client, monkeypatch):
    monkeypatch.setattr(server.RepositoryAnalyzer, "analyze_repository", lambda self, **kw: fake_repo(SENTINEL_README))
    for award in ["does_not_exist", "best_overall", "../../x"[:0] or "x"]:
        server.rate_limiter.requests.clear()
        r = client.post("/api/analyze", json={"analysis_mode": "project", "github_url": REPO, "award_id": award})
        assert r.status_code == 200, award
        assert r.json()["criteria_alignment"]["target_award"]


def test_default_award_still_uses_the_generic_overall_criteria_text_only_when_nothing_better_exists(client, monkeypatch):
    monkeypatch.setattr(server.RepositoryAnalyzer, "analyze_repository", lambda self, **kw: fake_repo(SENTINEL_README))
    r = client.post("/api/analyze", json={"analysis_mode": "project", "github_url": REPO,
                                          "prize_event_id": CURRENT_EVENT_ID, "award_id": "best_overall"}).json()
    assert r["criteria_alignment"]["target_award"] == "Best Overall"


def test_user_entered_requirements_are_added_to_the_challenge_not_a_replacement(client, monkeypatch):
    seen = {}
    real = ChatGPTClient.synthesize_report
    monkeypatch.setattr(ChatGPTClient, "synthesize_report", lambda self, **kw: (seen.update(kw), real(self, **kw))[1])
    review(client, monkeypatch, GRID_README, sponsor_requirements="Must use public GIS data")
    crit = seen["criteria_alignment"]["criteria"]
    assert "utilities" in crit.lower() and "Must use public GIS data" in crit
