import json
import pytest
from fastapi.testclient import TestClient
from hackbench.api.server import app
from hackbench.ai.idea_extractor import ExtractedIdea
from hackbench.ai.prize_matcher import (
    PrizeMatcher,
    FitLevel,
    SponsorTechRole,
    FORBIDDEN_WIN_TERMS,
    sanitize_fit_language,
)
from hackbench.models.event import PrizeCategory


@pytest.fixture
def client():
    return TestClient(app)


def test_prize_fit_uses_documented_criteria():
    """
    Test 1: Prize fit uses documented criteria and does not invent missing rules.
    """
    matcher = PrizeMatcher()
    prize = PrizeCategory(
        prize_id="prize_elevenlabs",
        title="ElevenLabs — Best Use of Conversational AI & Voice",
        prize_type="sponsor",
        sponsor_name="ElevenLabs",
        description="Build an engaging voice-first application using ElevenLabs Conversational AI or Voice APIs. Projects must demonstrate real-time adaptive voice interaction and practical conversational utility.",
        technologies_required_or_encouraged=["ElevenLabs"],
    )

    idea = ExtractedIdea(
        proposed_product="Voice Agent for Clinics",
        core_workflow="Calls patients after appointments and conducts voice conversation.",
        problem="Clinics get low post-appointments feedback completion.",
        intended_technologies=["ElevenLabs", "Twilio"],
    )

    fit = matcher._evaluate_deterministic(idea, ["ElevenLabs"], prize)
    assert fit.prize_id == "prize_elevenlabs"
    assert fit.insufficient_criteria is False
    # Verified documented requirements match the description
    assert any("voice" in req.lower() or "conversational" in req.lower() for req in fit.documented_requirements)
    assert len(fit.what_must_be_demonstrated) > 0


def test_missing_criteria_does_not_get_invented():
    """
    Test 2: Missing criteria does not get invented; stubs are marked insufficient_criteria.
    """
    matcher = PrizeMatcher()
    # Stub prize with no real criteria
    stub_prize = PrizeCategory(
        prize_id="prize_stub_sponsor",
        title="State Farm",
        prize_type="track",
        description="State Farm Challenge:",
        technologies_required_or_encouraged=[],
    )

    idea = ExtractedIdea(
        proposed_product="Auto Insurance Claim Assistant",
        core_workflow="Uploads damage photos and estimates claim payouts.",
    )

    fit = matcher._evaluate_deterministic(idea, [], stub_prize)
    assert fit.insufficient_criteria is True
    assert fit.fit_level == FitLevel.INSUFFICIENT_CRITERIA
    assert fit.fit_label == "Insufficient criteria"
    assert "insufficient" in fit.why_it_may_not_fit.lower() or "not published" in fit.biggest_missing_requirement.lower()


def test_sponsor_technology_must_be_relevant_to_core_workflow_for_very_strong_fit():
    """
    Test 3: Sponsor technology must be relevant and central to the core workflow for very strong fit.
    """
    matcher = PrizeMatcher()
    prize = PrizeCategory(
        prize_id="prize_elevenlabs",
        title="ElevenLabs Voice Challenge",
        prize_type="sponsor",
        sponsor_name="ElevenLabs",
        description="Build a voice-first application demonstrating real-time conversational voice interaction.",
        technologies_required_or_encouraged=["ElevenLabs"],
    )

    # Core workflow fundamentally depends on voice
    idea = ExtractedIdea(
        proposed_product="Voice Agent for Clinics",
        core_workflow="Calls patients after appointments and handles voice inquiries dynamically.",
        intended_technologies=["ElevenLabs", "FastAPI"],
    )

    fit = matcher._evaluate_deterministic(idea, ["ElevenLabs"], prize)
    assert fit.sponsor_tech_role == SponsorTechRole.CENTRAL
    assert fit.fit_level in (FitLevel.VERY_STRONG, FitLevel.STRONG)
    assert "central" in fit.why_it_fits.lower() or "voice" in fit.why_it_fits.lower()


def test_decorative_sponsor_mention_does_not_receive_very_strong_alignment():
    """
    Test 4: Decorative sponsor mention does not receive very strong alignment.
    """
    matcher = PrizeMatcher()
    prize = PrizeCategory(
        prize_id="prize_elevenlabs",
        title="ElevenLabs Voice Challenge",
        prize_type="sponsor",
        sponsor_name="ElevenLabs",
        description="Build a voice-first application demonstrating real-time conversational voice interaction.",
        technologies_required_or_encouraged=["ElevenLabs"],
    )

    # Core product is a calculator; ElevenLabs is only mentioned in technologies list
    idea = ExtractedIdea(
        proposed_product="Restaurant Bill Splitter",
        core_workflow="Input bill amount and calculate split mathematically.",
        intended_technologies=[],
    )

    # User adds ElevenLabs as an afterthought technology
    fit = matcher._evaluate_deterministic(idea, ["ElevenLabs"], prize)
    assert fit.sponsor_tech_role == SponsorTechRole.DECORATIVE
    # Critical invariant: must NOT be very strong
    assert fit.fit_level != FitLevel.VERY_STRONG
    assert fit.fit_level in (FitLevel.MODERATE, FitLevel.WEAK)
    assert "auxiliary" in fit.why_it_may_not_fit.lower() or "not" in fit.why_it_may_not_fit.lower()


def test_fit_language_never_becomes_win_probability_language():
    """
    Test 5: Fit language never becomes win-probability language anywhere in the output.
    """
    matcher = PrizeMatcher()
    idea = ExtractedIdea(
        proposed_product="A voice agent for clinics",
        core_workflow="Calls patients after appointments and turns conversations into operational insights.",
        problem="Post-appointments satisfaction surveys have low response rates.",
        intended_technologies=["ElevenLabs", "Twilio"],
    )

    result = matcher.match_prizes(idea, ["ElevenLabs"], event_id="shellhacks2025:2025")
    serialized = json.dumps(result.model_dump()).lower()

    # Assert none of the forbidden phrases exist
    for pattern in FORBIDDEN_WIN_TERMS:
        import re
        assert not re.search(pattern, serialized), f"Forbidden win probability term matched: {pattern}"

    assert "chance to win" not in serialized
    assert "most likely to win" not in serialized
    assert "easiest prize" not in serialized
    assert "best chance" not in serialized
    assert "win probability" not in serialized


def test_automatic_mode_can_analyze_multiple_awards(client):
    """
    Test 6: Automatic mode analyzes multiple awards and returns ranked fits.
    """
    payload = {
        "analysis_mode": "idea",
        "prize_targeting_mode": "auto",
        "idea": {
            "description": "A voice agent for clinics that calls patients after appointments and collects feedback.",
            "technologies_of_interest": ["ElevenLabs", "Twilio"],
        },
        "event_id": "shellhacks2025:2025",
    }
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert "prize_fits" in data
    pf = data["prize_fits"]
    assert pf["targeting_mode"] == "auto"
    assert pf["evaluated_count"] > 1
    assert len(pf["top_fits"]) > 0

    # Best-fitting prize should be voice or overall
    top_fit = pf["top_fits"][0]
    assert top_fit["fit_level"] in ["very_strong", "strong", "moderate"]
    assert "why_it_fits" in top_fit
    assert "what_must_be_demonstrated" in top_fit


def test_specific_prize_mode_still_works(client):
    """
    Test 7: Specific-prize mode still works when a user selects a prize.
    """
    payload = {
        "analysis_mode": "idea",
        "prize_targeting_mode": "specific",
        "award_id": "prize_elevenlabs",
        "idea": {
            "description": "A voice agent for clinics that calls patients after appointments.",
            "technologies_of_interest": ["ElevenLabs"],
        },
        "event_id": "shellhacks2025:2025",
    }
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert "prize_fits" in data
    pf = data["prize_fits"]
    assert pf["targeting_mode"] == "specific"
    assert len(pf["top_fits"]) == 1
    assert pf["top_fits"][0]["prize_id"] == "prize_elevenlabs"
    assert "ElevenLabs" in data["criteria_alignment"]["target_award"]


def test_results_are_limited_to_meaningful_top_matches(client):
    """
    Test 8: Results are limited to at most 3 meaningful top matches.
    """
    payload = {
        "analysis_mode": "idea",
        "prize_targeting_mode": "auto",
        "idea": {
            "description": "Smart inventory logistics optimization using RFID sensors and linear programming.",
            "technologies_of_interest": ["Python", "FastAPI"],
        },
        "event_id": "shellhacks2025:2025",
    }
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 200
    data = res.json()

    pf = data["prize_fits"]
    assert len(pf["top_fits"]) <= 3
    for match in pf["top_fits"]:
        # Invariant: insufficient criteria prizes are never shown as top matches
        assert match["insufficient_criteria"] is False
        assert match["fit_level"] != "insufficient_criteria"
