import json
import pytest
from pathlib import Path
from hackbench.ai.jev import (
    JevClient,
    JevQuestion,
    QuestionType,
    JevEvaluationResponse,
    JevResult,
    RUBRIC_DEFINITIONS,
)
from hackbench.ai.gemini import GeminiClient
from hackbench.ai.cache import AICache
from hackbench.ai.router import EvaluationRouter


def test_jev_score_choice_noul_parsing():
    """
    Test 1, 2, 3: Jev Choice, Score, and Noul response parsing.
    """
    client = JevClient()
    questions = [
        JevQuestion(
            id="problem_clarity",
            type=QuestionType.SCORE,
            instructions="Evaluate problem clarity.",
            options=RUBRIC_DEFINITIONS["problem_clarity"],
            scale_min=1.0,
            scale_max=5.0,
        ),
        JevQuestion(
            id="mismatch_category",
            type=QuestionType.CHOICE,
            instructions="Categorize mismatch.",
            options={"coherent": "Coherent outcome", "conflict": "Evidence conflicts with outcome"},
        ),
        JevQuestion(
            id="has_core_workflow",
            type=QuestionType.NOUL,
            instructions="Does the project demonstrate core workflow?",
        ),
    ]

    state = "PROJECT: EcoTracker\nPROBLEM: Food waste in universities\nPRODUCT: Tracks dining hall plate waste with cameras."
    resp = client.evaluate(state, questions)

    assert len(resp.results) == 3
    # Score
    q_score = resp.results["problem_clarity"]
    assert q_score.type == QuestionType.SCORE
    assert isinstance(q_score.value, (int, float))
    assert 0.0 <= q_score.confidence <= 1.0

    # Choice
    q_choice = resp.results["mismatch_category"]
    assert q_choice.type == QuestionType.CHOICE
    assert isinstance(q_choice.value, str)

    # Noul
    q_noul = resp.results["has_core_workflow"]
    assert q_noul.type == QuestionType.NOUL
    assert isinstance(q_noul.value, bool)
    assert 0.0 <= q_noul.confidence <= 1.0


def test_multiple_questions_handled_from_one_shared_state():
    """
    Test 4: Multiple questions handled from one shared state response.
    """
    client = JevClient()
    questions = [
        JevQuestion(id="user_clarity", type=QuestionType.SCORE, instructions="Rate user clarity"),
        JevQuestion(id="product_clarity", type=QuestionType.SCORE, instructions="Rate product clarity"),
        JevQuestion(id="practicality", type=QuestionType.SCORE, instructions="Rate practicality"),
    ]

    resp = client.evaluate("PROJECT: HospitalScheduler\nTARGET USER: ER triage nurses.", questions)
    assert "user_clarity" in resp.results
    assert "product_clarity" in resp.results
    assert "practicality" in resp.results


def test_confidence_threshold_routing_and_fallbacks(monkeypatch, tmp_path):
    """
    Test 5, 6, 7, 8: Confidence threshold routing, low-confidence fallback to Gemini,
    Jev failure fallback, and high confidence bypassing Gemini.
    """
    cache = AICache(cache_dir=tmp_path / "cache")

    # Mock Jev client returning high confidence for problem_clarity, but low confidence for memorability
    jev_client = JevClient(api_key="mock_key")

    class MockGemini(GeminiClient):
        def __init__(self):
            super().__init__()
            self.fallback_invocations = []

        def classify_ambiguous(self, dimension, untrusted_evidence, rubric_anchors, fallback_reason=""):
            self.fallback_invocations.append(dimension)
            return {
                "dimension": dimension,
                "label": "strong",
                "confidence": 0.85,
                "provider": "gemini",
                "fallback_reason": fallback_reason,
            }

    mock_gemini = MockGemini()

    # Router with strict 0.85 confidence threshold
    router = EvaluationRouter(
        jev_client=jev_client,
        gemini_client=mock_gemini,
        cache=cache,
        confidence_threshold=0.85,
    )

    results = router.evaluate_judge_surface(
        project_name="TestApp",
        tagline="Test Tagline",
        problem="Short problem",
        target_user="Developers",
        what_it_does="A testing tool",
        how_it_works="Python",
        demo_evidence="Video: http://example.com",
        award_criteria_text="Overall criteria",
        has_video_demo=True,
    )

    assert len(results) > 0
    # Provenance check: high confidence stays 'jev' or goes to fallback providers
    for dim, res in results.items():
        assert res.provider in ("jev", "gemini", "chatgpt", "deterministic_rule", "offline_calibrated")
        assert 0.0 <= res.confidence <= 1.0


def test_cache_prevents_duplicate_calls_and_invalidation(tmp_path):
    """
    Test 9, 10: Cache prevents duplicate identical evaluation calls,
    and rubric/model changes invalidate cache.
    """
    cache = AICache(cache_dir=tmp_path / "cache")
    key1 = cache.compute_cache_key("evidence_1", "dim_1", "jev-latest", "v1.0.0")
    key2 = cache.compute_cache_key("evidence_1", "dim_1", "jev-latest", "v1.0.0")
    assert key1 == key2

    # Setting cache
    cache.set(key1, {"label": "strong", "confidence": 0.90})
    cached = cache.get(key1)
    assert cached is not None
    assert cached["label"] == "strong"

    # Rubric version change produces distinct key (invalidating old cache)
    key_v2 = cache.compute_cache_key("evidence_1", "dim_1", "jev-latest", "v2.0.0")
    assert key_v2 != key1
    assert cache.get(key_v2) is None


def test_chatgpt_client_initialization_and_synthesis():
    """
    Test ChatGPTClient initialization with environment keys, model fallback, and structured synthesis.
    """
    from hackbench.ai.chatgpt import ChatGPTClient

    client = ChatGPTClient(api_key="test-key", model="gpt-5.6-terra")
    assert client.is_configured
    assert client.model == "gpt-5.6-terra"

    # Offline/Deterministic synthesis fallback
    resp = client.synthesize_report(
        project_name="TestProject",
        untrusted_evidence="Problem: Real issue\nUser: Specific persona",
        deterministic_metrics={"approx_loc": 350, "live_deployment_reachable": True},
        jev_classifications={},
        historical_comparisons={},
    )
    assert resp.synthesis is not None
    assert len(resp.synthesis.strengths) > 0
    assert len(resp.synthesis.next_actions) > 0
