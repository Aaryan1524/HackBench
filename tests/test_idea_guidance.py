"""Phase 3: concise pre-hackathon build guidance for Idea Mode."""
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hackbench.ai.chatgpt import ChatGPTClient, ParticipantReportSynthesis
from hackbench.ai.idea_extractor import ExtractedIdea, IdeaExtractor
from hackbench.ai.idea_guidance import (
    FORBIDDEN_FIRST_STEPS,
    build_idea_guidance,
    find_dont_build,
    historical_takeaway,
    is_valid_action,
    is_valid_build_first,
)
from hackbench.ai.prize_matcher import FORBIDDEN_WIN_TERMS, FitLevel, PrizeMatcher
from hackbench.api.server import app
from hackbench.models.event import PrizeCategory

TECHNICAL = (
    "We want to build an offline bluetooth mesh network for campus emergency alerts that broadcasts a "
    "distress signal to nearby phones, matches a safe-walk request, and shows the route on a real-time offline map.",
    ["Rust", "Flutter"],
)
VAGUE = ("An app that helps students study better.", [])
SPONSOR = (
    "We want to build a voice agent for clinics that calls patients after appointments, asks follow-up questions "
    "based on their answers, and turns conversations into operational insights for clinic managers.",
    ["ElevenLabs", "Twilio"],
)
ALL_IDEAS = {"technical": TECHNICAL, "vague": VAGUE, "sponsor": SPONSOR}

IMPLEMENTATION_WORDS = re.compile(
    r"\b(repo|repository|github|deploy(?:ed|ment)?|test coverage|lines of code|loc|ci|commits?)\b", re.IGNORECASE
)
HEDGING_WORDS = re.compile(r"\b(consider|potentially|prioriti[sz]ing|implementation of|leverage)\b", re.IGNORECASE)
SCORE_LANGUAGE = re.compile(r"\b(score optimi[sz]\w*|optimi[sz]e (?:the )?score|alignment score|boost your score)\b", re.IGNORECASE)
ENGINEERING_KEYS = {"approx_loc", "test_files_count", "api_routes_count", "has_ci", "live_deployment_reachable",
                    "deployment_verification", "todo_fixme_count", "primary_languages"}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Guidance must work (and be tested) without any live model call."""
    for key in ("CHATGPT_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "JEV_API_KEY"):
        monkeypatch.setenv(key, "")


def _guidance(name):
    description, techs = ALL_IDEAS[name]
    idea = IdeaExtractor().extract(description, techs)
    fits = PrizeMatcher().match_prizes(idea, techs).top_fits
    return idea, fits, build_idea_guidance(idea, description, fits)


def _all_text(obj) -> str:
    return json.dumps(obj if isinstance(obj, (dict, list)) else obj.model_dump())


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


@pytest.mark.parametrize("name", ALL_IDEAS)
def test_build_first_is_an_end_to_end_workflow(name):
    _, _, g = _guidance(name)
    steps = [s.strip() for s in g.build_first.split("→")]
    assert 3 <= len(steps) <= 5
    assert steps == g.build_first_steps
    assert not FORBIDDEN_FIRST_STEPS.search(steps[0])
    assert not any(FORBIDDEN_FIRST_STEPS.search(s) for s in steps)


def test_build_first_uses_the_ideas_own_workflow():
    _, _, g = _guidance("sponsor")
    joined = g.build_first.lower()
    assert "call patients after appointments" in joined
    assert "ask follow-up questions" in joined
    assert "operational insights" in joined


def test_build_first_for_undefined_workflow_does_not_invent_steps():
    idea, _, g = _guidance("vague")
    assert idea.core_workflow is None
    assert g.biggest_gap.kind == "workflow_undefined"
    assert "students" in g.build_first
    # It describes the shape of a loop but names no invented features or technologies.
    assert not re.search(r"\b(voice|blockchain|dashboard|database|api)\b", g.build_first, re.IGNORECASE)


@pytest.mark.parametrize("name", ALL_IDEAS)
def test_guidance_never_depends_on_implementation_evidence(name):
    _, _, g = _guidance(name)
    assert not IMPLEMENTATION_WORDS.search(_all_text(g))


def test_dont_build_yet_is_empty_without_evidence():
    idea, fits, g = _guidance("sponsor")
    assert g.dont_build_yet == []
    assert find_dont_build(idea, "A tool that turns receipts into recipes.", fits) == []


def test_dont_build_yet_only_quotes_things_the_idea_mentions():
    description = (
        "A campus alert app for students that broadcasts a distress signal to nearby phones and shows a route. "
        "Later it needs multi-campus admin dashboards and user accounts."
    )
    idea = IdeaExtractor().extract(description)
    items = find_dont_build(idea, description, [])
    assert 1 <= len(items) <= 3
    for item in items:
        quoted = re.search(r"“(.+?)”", item).group(1)
        assert quoted.lower() in description.lower()


def test_dont_build_yet_is_capped_at_three():
    description = (
        "A helper for students that suggests study plans and shows them. It has user accounts, dashboards, "
        "billing, settings, multi-tenant support, and Slack integrations."
    )
    idea = IdeaExtractor().extract(description)
    assert len(find_dont_build(idea, description, [])) == 3


def test_dont_build_yet_skips_what_the_core_loop_or_prize_requires():
    # "dashboard" is the core outcome here, so it is not something to postpone.
    description = "A tool for coaches that turns match footage into a dashboard of player stats."
    idea = ExtractedIdea(core_workflow="turns match footage into a dashboard of player stats",
                         user_outcome="turns match footage into a dashboard")
    assert find_dont_build(idea, description, []) == []

    # A documented prize requirement (Auth0 login) must not be listed as something to skip.
    matcher = PrizeMatcher()
    auth_prize = PrizeCategory(
        prize_id="auth0", title="Best Use of Auth0", prize_type="sponsor", sponsor_name="Auth0",
        description="Integrate Auth0 authentication such as social sign-in, MFA, or passwordless login.",
        technologies_required_or_encouraged=["Auth0"],
    )
    desc = "A study group app for students with login and shared notes."
    idea = IdeaExtractor().extract(desc, ["Auth0"])
    fit = matcher._evaluate_deterministic(idea, ["Auth0"], auth_prize)
    assert "Login" not in " ".join(find_dont_build(idea, desc, [fit]))


def test_demo_requirements_come_from_documented_prize_criteria():
    matcher = PrizeMatcher()
    prize = PrizeCategory(
        prize_id="prize_elevenlabs",
        title="ElevenLabs — Best Use of Conversational AI & Voice",
        prize_type="sponsor",
        sponsor_name="ElevenLabs",
        description="Build a voice-first application using ElevenLabs Conversational AI. Projects must demonstrate real-time adaptive voice interaction.",
        technologies_required_or_encouraged=["ElevenLabs"],
    )
    idea = IdeaExtractor().extract(*SPONSOR)
    fit = matcher._evaluate_deterministic(idea, ["ElevenLabs"], prize)
    assert fit.what_must_be_demonstrated
    joined = " ".join(fit.what_must_be_demonstrated).lower()
    assert "voice" in joined and "sponsor technology" in joined


def test_prize_without_documented_criteria_yields_no_invented_demo_requirements():
    matcher = PrizeMatcher()
    stub = PrizeCategory(prize_id="stub", title="State Farm", prize_type="track", description="State Farm Challenge:")
    idea = IdeaExtractor().extract(*SPONSOR)
    assert matcher._evaluate_deterministic(idea, [], stub).what_must_be_demonstrated == []

    no_tech = PrizeCategory(
        prize_id="misc", title="Best Hardware Hack", prize_type="track",
        description="Awarded to the most creative use of physical sensors and microcontrollers in a project.",
    )
    fit = matcher._evaluate_deterministic(idea, [], no_tech)
    # Anything listed must be quoted from the prize's own description, never a placeholder.
    for item in fit.what_must_be_demonstrated:
        assert item.rstrip("…").strip() in no_tech.description


@pytest.mark.parametrize("name", ALL_IDEAS)
def test_guidance_is_concise(name):
    _, _, g = _guidance(name)
    assert len(g.build_first_steps) <= 5
    assert len(g.dont_build_yet) <= 3
    assert len(g.before_hackathon) == 3
    assert len(g.headline.split("\n")) == 2
    for text in [g.strongest.detail, g.biggest_gap.detail, g.summary, g.historical_takeaway or ""]:
        assert len(text) <= 260
    for a in g.before_hackathon:
        assert len(a["action"]) <= 200 and len(a["reason"]) <= 200
    for item in g.dont_build_yet:
        assert len(item) <= 160


@pytest.mark.parametrize("name", ALL_IDEAS)
def test_language_is_direct_and_has_no_win_prediction_or_score_optimization(name):
    _, fits, g = _guidance(name)
    text = _all_text(g) + _all_text([f.model_dump() for f in fits])
    for pattern in FORBIDDEN_WIN_TERMS:
        assert not re.search(pattern, text, re.IGNORECASE), pattern
    assert not SCORE_LANGUAGE.search(text)
    for a in g.before_hackathon:
        assert not HEDGING_WORDS.search(a["action"])


def test_recommendations_differ_across_different_ideas():
    gs = {name: _guidance(name)[2] for name in ALL_IDEAS}
    assert len({g.build_first for g in gs.values()}) == 3
    assert len({g.biggest_gap.kind for g in gs.values()}) >= 2
    assert len({g.strongest.kind for g in gs.values()}) >= 2
    assert len({tuple(a["action"] for a in g.before_hackathon) for g in gs.values()}) == 3
    # Only the sponsor-specific idea is told to make the sponsor visible in the demo.
    assert any("ElevenLabs" in a["action"] for a in gs["sponsor"].before_hackathon)
    assert not any("ElevenLabs" in a["action"] for a in gs["vague"].before_hackathon)


def test_historical_takeaway_is_computed_from_the_baseline_and_omitted_when_unsupported():
    from hackbench.ai.baselines import load_history
    history, _ = load_history("shellhacks2025:2025")
    if history:
        text = historical_takeaway(history)
        assert text and "n=" in text and "ShellHacks 2025" in text
    assert historical_takeaway(None) is None
    assert historical_takeaway({"cohort_comparisons": {"winners_vs_nonwinners": [
        {"dimension_or_feature": "technical_depth", "interpretation": "Large effect size (higher in Winners)",
         "sample_a": 5, "sample_b": 9}]}}) is None


def test_model_output_is_validated_before_it_is_used():
    assert is_valid_build_first("A → B → C")
    assert not is_valid_build_first("Build a great app")
    assert not is_valid_build_first("Authentication and login → B → C")
    assert not is_valid_action("Consider potentially prioritizing the feedback workflow.")
    assert is_valid_action("Build the complete loop first.")

    _, _, g = _guidance("sponsor")
    llm = ParticipantReportSynthesis(
        summary="x", build_first="Set up billing → Add settings page → Ship",
        dont_build_yet=["Made-up filler item"],
    )
    merged = ChatGPTClient._merge_idea_synthesis(llm, g)
    assert merged.build_first == g.build_first
    assert merged.dont_build_yet == g.dont_build_yet == []


@pytest.fixture
def client():
    return TestClient(app)


def test_api_idea_mode_exposes_guidance_and_no_engineering_metrics(client):
    res = client.post("/api/analyze", json={
        "analysis_mode": "idea",
        "idea": {"description": SPONSOR[0], "technologies_of_interest": SPONSOR[1]},
    })
    assert res.status_code == 200
    data = res.json()
    assert "engineering" not in data
    assert not (set(_keys(data)) & ENGINEERING_KEYS)

    recs = data["recommendations"]
    assert recs["build_first"].count("→") >= 2
    assert recs["strengths"] and recs["gaps"]
    assert len(recs["next_actions"]) == 3
    assert "dont_build_yet" in recs and len(recs["dont_build_yet"]) <= 3
    assert "demo_requirements" not in recs
    assert data["prize_fits"]["top_fits"][0]["what_must_be_demonstrated"]

    text = json.dumps(recs) + json.dumps(data["prize_fits"])
    assert not IMPLEMENTATION_WORDS.search(json.dumps(recs))
    for pattern in FORBIDDEN_WIN_TERMS:
        assert not re.search(pattern, text, re.IGNORECASE)


def test_api_recommendations_differ_by_idea(client):
    outs = []
    for description, techs in ALL_IDEAS.values():
        res = client.post("/api/analyze", json={
            "analysis_mode": "idea", "idea": {"description": description, "technologies_of_interest": techs},
        })
        assert res.status_code == 200
        outs.append(res.json()["recommendations"])
    assert len({r["build_first"] for r in outs}) == 3
    assert len({r["gaps"][0]["title"] for r in outs}) >= 2


def test_weak_prize_fit_never_becomes_the_biggest_gap():
    idea, fits, _ = _guidance("sponsor")
    weak = [f.model_copy(update={"fit_level": FitLevel.WEAK, "prize_type": "sponsor"}) for f in fits]
    g = build_idea_guidance(idea, SPONSOR[0], weak)
    assert g.biggest_gap.kind != "prize_requirement"
