import json
import pytest
from fastapi.testclient import TestClient
from hackbench.api.server import app
from hackbench.ai.idea_extractor import IdeaExtractor, ExtractedIdea


@pytest.fixture
def client():
    return TestClient(app)


def test_idea_extractor_produces_structured_fields():
    """
    Test 7: Idea description extraction produces structured fields:
    - problem
    - target user
    - proposed product
    - core workflow
    - intended technologies
    """
    extractor = IdeaExtractor()
    text = (
        "We want to build a voice agent for clinics that calls patients after appointments, "
        "asks follow-up questions based on their answers, and turns conversations into "
        "operational insights for clinic managers."
    )
    technologies = ["Twilio", "FastAPI", "OpenAI"]
    
    extracted = extractor.extract(text, technologies_of_interest=technologies)
    assert isinstance(extracted, ExtractedIdea)
    
    # Verify structured fields
    assert extracted.proposed_product is not None
    assert "voice agent" in extracted.proposed_product.lower() or "clinic" in extracted.proposed_product.lower()
    
    assert extracted.target_user is not None
    assert any(term in extracted.target_user.lower() for term in ["clinic", "patient", "manager", "staff"])
    
    assert extracted.problem is not None or extracted.user_outcome is not None
    assert extracted.core_workflow is not None
    assert any(term in extracted.core_workflow.lower() for term in ["call", "patient", "appointments", "insight", "conversation"])
    
    assert extracted.intended_technologies is not None
    assert "Twilio" in extracted.intended_technologies or "FastAPI" in extracted.intended_technologies


def test_missing_extracted_fields_remain_unknown_instead_of_invented():
    """
    Test 8: Missing extracted fields remain unknown (None or empty) instead of invented.
    """
    extractor = IdeaExtractor()
    minimal_text = "A simple calculator for splitting restaurant bills evenly."
    extracted = extractor.extract(minimal_text)

    assert isinstance(extracted, ExtractedIdea)
    # Technologies were not mentioned, so must remain empty lists rather than invented tech stacks
    assert extracted.intended_technologies == []
    assert extracted.likely_sponsor_technologies == []


def test_idea_mode_does_not_require_repository_or_demo_fields(client):
    """
    Test 2: Idea mode does not require repository/demo fields.
    """
    payload = {
        "analysis_mode": "idea",
        "idea": {
            "description": "We want to build a voice agent for clinics that calls patients after appointments.",
            "technologies_of_interest": ["Twilio", "Python"],
        },
    }
    # No github_url, devpost_url, demo_url, or deployment_url provided
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["analysis_mode"] == "idea"
    assert "extracted_idea" in data
    assert "recommendations" in data


def test_completion_and_demo_are_not_evaluated_in_idea_mode(client):
    """
    Test 4 & 5: Completion and demo strength are NOT evaluated in idea mode
    (must be labeled 'not_evaluated', never treated as missing/zero/weak).
    """
    payload = {
        "analysis_mode": "idea",
        "idea": {
            "description": (
                "An automated triaging system for emergency rooms that categorizes incoming patients "
                "by symptom severity before human intake."
            ),
        },
    }
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 200
    data = res.json()

    # Judge surface metrics
    judge_surface = data["judge_surface"]
    assert "completion_appearance" in judge_surface
    assert "demo_strength" in judge_surface
    assert judge_surface["completion_appearance"]["label"] == "not_evaluated"
    assert judge_surface["demo_strength"]["label"] == "not_evaluated"

    # Historical comparison metrics
    hist_dims = data["historical_comparison"]["dimensions"]
    assert "completion_appearance" in hist_dims
    assert "demo_strength" in hist_dims
    assert "not evaluated" in hist_dims["completion_appearance"]["you"].lower()
    assert "not evaluated" in hist_dims["demo_strength"]["you"].lower()


def test_idea_analysis_does_not_mark_missing_implementation_as_weak(client):
    """
    Test 3: Idea analysis does not mark missing implementation as weak,
    and produces actionable 'build_first' guidance instead of penalizing absent code.
    """
    payload = {
        "analysis_mode": "idea",
        "idea": {
            "description": (
                "A voice agent for clinics that calls patients after appointments, asks follow-up questions, "
                "and turns conversations into operational insights for clinic managers."
            ),
        },
    }
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 200
    data = res.json()

    recs = data["recommendations"]
    # Invariant: biggest gap must NOT penalize missing deployment or repo
    assert recs["gaps"], "idea mode must name a conceptual gap"
    biggest_gap = (recs["gaps"][0]["title"] + " " + recs["gaps"][0]["evidence"]).lower()
    assert "no reachable live deployment" not in biggest_gap
    assert "repository" not in biggest_gap
    assert "deployment" not in biggest_gap

    # Invariant: must provide concrete 'build_first' priority
    assert "build_first" in recs
    assert recs["build_first"] is not None
    assert len(recs["build_first"].strip()) > 0


def test_existing_project_mode_still_works_with_repositories_and_deployments(client):
    """
    Test 6: Existing project mode still works with repositories and deployments.
    """
    payload = {
        "analysis_mode": "project",
        "input_mode": "manual",
        "project": {
            "name": "SafetyNet",
            "tagline": "AI hazard detector for pedestrians",
            "problem": "Pedestrian accidents at blind intersections cause 4,000 injuries annually.",
            "target_user": "Urban commuters and cyclists.",
            "what_it_does": "Alerts nearby pedestrians using Bluetooth audio beacons.",
            "how_it_works": "React frontend connected to OpenCV camera feed.",
            "tech_tags": ["React", "Python", "OpenCV"],
        },
    }
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["analysis_mode"] == "project"
    assert "engineering" in data
    assert "judge_surface" in data
    # In project mode, demo_strength is evaluated (insufficient_evidence when no demo URL provided)
    assert data["judge_surface"]["demo_strength"]["label"] in ["insufficient_evidence", "weak", "moderate", "strong"]


def test_default_mode_is_idea_when_unspecified(client):
    """
    Test 1: When no mode is specified, requests default to Review an Idea.
    """
    payload = {
        "idea": {
            "description": "Smart irrigation controller optimizing water delivery based on microclimate forecasts.",
        }
    }
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["analysis_mode"] == "idea"
    assert data["judge_surface"]["completion_appearance"]["label"] == "not_evaluated"
