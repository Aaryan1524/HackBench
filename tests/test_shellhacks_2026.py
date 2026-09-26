"""ShellHacks 2026: this year's sponsor challenges, used as a prize source (there are no results to compare against yet)."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hackbench.ai.baselines import (
    ALL_YEARS_ID, CURRENT_EVENT_ID, KNOWN_BASELINE_IDS, KNOWN_PRIZE_EVENT_IDS, combined_prizes, label_for,
    load_history, load_prizes, prize_has_criteria,
)
from hackbench.ai.idea_extractor import ExtractedIdea, IdeaExtractor
from hackbench.ai.prize_matcher import PrizeMatcher
from hackbench.api import server

EVENT_DIR = Path("data/raw/shellhacks2026/2026/event")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key in ("CHATGPT_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "JEV_API_KEY"):
        monkeypatch.setenv(key, "")


@pytest.fixture
def client():
    server.rate_limiter.requests.clear()
    return TestClient(server.app)


def prizes():
    return load_prizes(CURRENT_EVENT_ID)[0]


def fits_for(description, techs=None):
    idea = IdeaExtractor().extract(description, techs or [])
    result = PrizeMatcher().match_prizes(idea, techs or [], event_id=CURRENT_EVENT_ID)
    return {f.award_title: f for f in result.top_fits}, idea


def fit_of(description, title_part, techs=None):
    idea = IdeaExtractor().extract(description, techs or [])
    prize = next(p for p in prizes() if title_part in p.title)
    return PrizeMatcher()._evaluate_deterministic(idea, techs or [], prize)


def strong(description, techs=None):
    fits, _ = fits_for(description, techs)
    return {t.split("—")[-1].strip() for t, f in fits.items() if f.fit_level.value in ("strong", "very_strong")}


# ---------- the data ----------

def test_2026_is_a_prize_source_not_a_history_baseline():
    assert CURRENT_EVENT_ID in KNOWN_PRIZE_EVENT_IDS
    assert CURRENT_EVENT_ID not in KNOWN_BASELINE_IDS
    history, exact = load_history(CURRENT_EVENT_ID)
    assert exact is False  # no results exist, so nothing pretends to be 2026 history
    assert label_for(CURRENT_EVENT_ID) == "ShellHacks 2026"


def test_all_provided_challenges_are_loaded():
    titles = [p.title for p in prizes()]
    assert len(titles) == 17
    for expected in ["Best Overall", "Best First-Time Hacker", "Sperry Tech — The GridLock Challenge",
                     "Assurant — Take Control of AI", "Waymo — The Waymo Mobility Challenge", "Microsoft — What's Missing?",
                     "Blackstone — Reimagining the Investor Experience", "State Farm — Auto Insurance Challenge",
                     "INIT National — Building Together", "MLH × ElevenLabs — Best Use of ElevenLabs",
                     "MLH × Google Cloud — Best Use of Gemini API", "MLH × Solana — Best Use of Solana",
                     "MLH × Tiger Data — Best Use of Tiger Data", "MLH × DigitalOcean — Best Use of DigitalOcean",
                     "MLH × Snowflake — Best Use of Snowflake API", "MLH × MongoDB — Best Use of MongoDB Atlas",
                     "MLH × GoDaddy Registry — Best Domain Name from GoDaddy Registry"]:
        assert expected in titles, expected
    assert len([p for p in prizes() if p.prize_type == "sponsor"]) == 15


def test_nothing_is_invented_and_prize_items_are_not_criteria():
    data = json.loads((EVENT_DIR / "event_metadata.json").read_text())
    assert data["event_url"] == "" and data["devpost_url"] == ""  # none were provided
    text = " ".join(p["description"] for p in data["prize_categories"])
    for swag in ["MacBook", "iPad", "gift card", "Ledger", "Stream Deck", "Raspberry", "backpack", "Earbuds"]:
        assert swag.lower() not in text.lower(), swag
    # ...but the raw record keeps them for reference.
    assert "MacBook" in json.dumps(data["sponsor_challenges"])


def test_requirements_are_kept_in_the_description():
    ms = next(p for p in prizes() if "What's Missing" in p.title)
    assert "cannot be a chatbot" in ms.description and "real task" in ms.description
    gemini = next(p for p in prizes() if "Gemini" in p.title)
    assert "Use the Gemini API" in gemini.description and gemini.technologies_required_or_encouraged == ["Gemini API"]


def test_criteria_flags():
    by_title = {p.title: prize_has_criteria(p) for p in prizes()}
    assert by_title["Best Overall"] is True  # judged on the general dimensions
    assert by_title["Best First-Time Hacker"] is False  # eligibility, not criteria
    assert all(v for t, v in by_title.items() if "—" in t)


def test_source_yaml_is_kept_next_to_the_json():
    assert (EVENT_DIR / "sponsor_challenges.yaml").exists()
    assert Path("scripts/import_event_yaml.py").exists()


def test_combined_prizes_stay_the_past_years_only():
    assert not any("GridLock" in p.title or "Take Control of AI" in p.title for p in combined_prizes())


def test_idea_source_text_never_leaves_the_process():
    idea = IdeaExtractor().extract("A trail app for hikers that plots routes. Secret note: ZEBRA-9931 must stay private.")
    assert idea.source_text and "ZEBRA-9931" in idea.source_text
    assert "source_text" not in idea.model_dump() and "ZEBRA-9931" not in idea.model_dump_json()
    assert "source_text" not in ExtractedIdea.model_validate(idea.model_dump()).model_dump()


# ---------- matching ----------

@pytest.mark.parametrize("description, techs, expected", [
    ("We want to build a voice agent for clinics that calls patients after appointments, asks follow-up questions, and turns conversations into insights for clinic managers.", ["ElevenLabs"], "Best Use of ElevenLabs"),
    ("A tool that compares two power utilities' public construction plans and flags nearby or overlapping projects so they can share crews and equipment.", [], "The GridLock Challenge"),
    ("A dashboard for retail investors that analyzes their portfolio, visualizes risk and summarizes trends from public economic data.", [], "Reimagining the Investor Experience"),
    ("An app that helps college students understand auto insurance and gamifies safe parking to reduce car theft near campus.", [], "Auto Insurance Challenge"),
    ("A platform where student builders find teammates, get mentorship, and share knowledge to keep building projects together over months.", [], "Building Together"),
    ("An app that helps students carpool to campus using Google Maps directions and elevation data.", [], "The Waymo Mobility Challenge"),
    ("A payments app on Solana that lets students split bills instantly, storing profiles in MongoDB Atlas.", ["Solana", "MongoDB Atlas"], "Best Use of MongoDB Atlas"),
])
def test_each_challenge_matches_the_idea_it_describes(description, techs, expected):
    assert expected in strong(description, techs)


def test_an_idea_with_no_sponsor_subject_matches_only_the_general_award():
    fits, _ = fits_for("A tool for beekeepers that listens to hive audio, detects queenless colonies, and sends a notification.")
    sponsor_hits = [t for t, f in fits.items() if f.prize_type == "sponsor" and f.fit_level.value in ("strong", "very_strong", "moderate")]
    assert sponsor_hits == []


def test_a_required_technology_must_actually_be_planned():
    named = fit_of("An app that summarizes research papers using the Gemini API for students.", "Gemini")
    assert named.fit_level.value == "strong" and named.sponsor_tech_role.value == "central"
    listed_only = fit_of("An app that summarizes research papers for students.", "Gemini", ["Gemini"])
    assert listed_only.fit_level.value == "moderate" and listed_only.sponsor_tech_role.value == "decorative"
    absent = fit_of("An app that helps hikers plan trail routes.", "Gemini")
    assert absent.fit_level.value in ("weak", "very_weak") and "Gemini API" in absent.why_it_may_not_fit
    assert "Use Gemini API" in absent.biggest_missing_requirement


def test_microsoft_rule_a_chatbot_cannot_be_the_core_experience():
    chatbot = fit_of("A chatbot that helps students study by answering questions in a chat window, using AI.", "What's Missing")
    assert chatbot.fit_level.value in ("weak", "very_weak")
    assert "cannot be a chatbot" in chatbot.why_it_may_not_fit
    assert "cannot be a chatbot" in chatbot.biggest_missing_requirement
    real = fit_of("An app that turns a photo of a crumpled paper form into an accessible digital form for people with low vision, using AI to read and fix the layout.", "What's Missing")
    assert real.fit_level.value in ("moderate", "strong") and "cannot be" not in real.why_it_may_not_fit


def test_demo_requirements_come_from_the_challenge_text():
    f = fit_of("An app that turns a photo of a paper form into an accessible digital form using AI.", "What's Missing")
    joined = " ".join(f.documented_requirements + f.what_must_be_demonstrated).lower()
    assert "chatbot" in joined or "real task" in joined


def test_elevenlabs_challenge_uses_the_voice_rule():
    f = fit_of("A voice agent that talks to patients and adapts its replies.", "ElevenLabs", ["ElevenLabs"])
    assert f.fit_level.value == "very_strong" and f.sponsor_name == "ElevenLabs"


# ---------- API ----------

IDEA = "A tool that compares two power utilities' public construction plans and flags nearby or overlapping projects so they can share crews."


def test_prizes_endpoint_lists_2026(client):
    body = client.get(f"/api/events/{CURRENT_EVENT_ID}/prizes").json()
    assert len(body["prizes"]) == 17
    flags = {p["title"]: p["has_sufficient_criteria"] for p in body["prizes"]}
    assert flags["Best Overall"] and not flags["Best First-Time Hacker"]


def test_2026_prizes_with_past_results_from_2025(client):
    r = client.post("/api/analyze", json={"analysis_mode": "idea", "event_id": "shellhacks2025:2025",
                                          "prize_event_id": CURRENT_EVENT_ID, "idea": {"description": IDEA}}).json()
    assert r["prize_event_id"] == CURRENT_EVENT_ID
    assert r["historical_comparison"]["baseline_label"] == "ShellHacks 2025"
    assert r["notes"] == [] or all("no data" not in n.lower() and "no prizes" not in n.lower() for n in r["notes"])
    top = r["prize_fits"]["top_fits"][0]
    assert "GridLock" in top["award_title"] and top["fit_level"] in ("strong", "very_strong")
    assert r["prize_fits"]["top_fits"][0]["what_must_be_demonstrated"]


def test_prizes_default_to_the_comparison_year_when_not_specified(client):
    r = client.post("/api/analyze", json={"analysis_mode": "idea", "event_id": "shellhacks2024:2024", "idea": {"description": IDEA}}).json()
    assert r["prize_event_id"] == "shellhacks2024:2024"
    assert not any("GridLock" in f["award_title"] for f in r["prize_fits"]["top_fits"])


def test_unknown_prize_source_falls_back_and_says_so(client):
    r = client.post("/api/analyze", json={"analysis_mode": "idea", "event_id": "shellhacks2025:2025",
                                          "prize_event_id": "shellhacks2031:2031", "idea": {"description": IDEA}}).json()
    assert any("no prizes" in n.lower() for n in r["notes"])


def test_specific_2026_prize_can_be_chosen(client):
    prize_id = next(p.prize_id for p in prizes() if "GridLock" in p.title)
    r = client.post("/api/analyze", json={"analysis_mode": "idea", "event_id": "shellhacks2025:2025", "prize_event_id": CURRENT_EVENT_ID,
                                          "prize_targeting_mode": "specific", "award_id": prize_id, "idea": {"description": IDEA}}).json()
    assert len(r["prize_fits"]["top_fits"]) == 1 and "GridLock" in r["prize_fits"]["top_fits"][0]["award_title"]
