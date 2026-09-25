import os
import json
import logging
import time
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from .jev import (
    JevClient,
    JevQuestion,
    QuestionType,
    RUBRIC_DEFINITIONS,
    SCORE_LEVEL_VALUES,
)
from .gemini import GeminiClient, ParticipantReportSynthesis
from .cache import AICache, RUBRIC_VERSION
from .usage import AnalysisUsageStats

logger = logging.getLogger("hackbench.ai.router")

DEFAULT_CONFIDENCE_THRESHOLD = 0.80

BOUNDED_JEV_DIMENSIONS = [
    "problem_clarity",
    "user_clarity",
    "product_clarity",
    "demo_strength",
    "completion_appearance",
    "practicality",
    "story_clarity",
    "memorability",
    "award_alignment",
]


class DimensionEvaluationResult(BaseModel):
    dimension: str
    label: str
    score: float
    confidence: float
    provider: str
    probabilities: Dict[str, float] = Field(default_factory=dict)
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    is_insufficient_evidence: bool = False


class RouterEvaluationOutput(BaseModel):
    evaluations: Dict[str, DimensionEvaluationResult]
    composite_presentation_score: float
    usage: AnalysisUsageStats
    synthesis: Optional[ParticipantReportSynthesis] = None


class EvaluationRouter:
    """
    3-Layer Hybrid Evaluation Router:
    Layer 1: Deterministic software facts.
    Layer 2: Jev bounded rubric classifications with shared-state batching.
    Layer 3: Confidence gating + Gemini fallback & final synthesis.
    """

    def __init__(
        self,
        jev_client: Optional[JevClient] = None,
        gemini_client: Optional[GeminiClient] = None,
        cache: Optional[AICache] = None,
        confidence_threshold: Optional[float] = None,
    ):
        self.jev = jev_client or JevClient()
        self.gemini = gemini_client or GeminiClient()
        self.cache = cache or AICache()
        env_thresh = os.getenv("JEV_CONFIDENCE_THRESHOLD")
        self.confidence_threshold = (
            float(env_thresh) if env_thresh else (confidence_threshold or DEFAULT_CONFIDENCE_THRESHOLD)
        )

    def evaluate_judge_surface(
        self,
        project_name: str,
        tagline: str,
        problem: str,
        target_user: str,
        what_it_does: str,
        how_it_works: str,
        demo_evidence: str,
        award_criteria_text: Optional[str] = None,
        has_video_demo: bool = False,
        has_live_deployment: bool = False,
    ) -> Dict[str, DimensionEvaluationResult]:
        """
        Evaluates the judge-facing presentation surface across all 9 canonical dimensions
        using shared-state Jev batching and Gemini fallback gating.
        """
        # 1. Construct compact, unified project state
        state_parts = [
            f"PROJECT: {project_name}",
            f"TAGLINE: {tagline or 'N/A'}",
            f"\nPROBLEM STATEMENT:\n{problem or 'N/A'}",
            f"\nTARGET USER:\n{target_user or 'Inferred from description'}",
            f"\nPRODUCT & WORKFLOW:\n{what_it_does or 'N/A'}\n{how_it_works or 'N/A'}",
            f"\nDEMO EVIDENCE:\n{demo_evidence or ('Video demo present' if has_video_demo else 'No demo provided')}",
        ]
        if award_criteria_text:
            state_parts.append(f"\nDOCUMENTED AWARD CRITERIA:\n{award_criteria_text}")
        else:
            state_parts.append("\nDOCUMENTED AWARD CRITERIA: None provided / general category.")

        if not has_video_demo and not has_live_deployment:
            state_parts.append("\nEVIDENCE LIMITATIONS: Neither interactive deployment nor video demo available.")

        shared_state = "\n".join(state_parts)

        # 2. Build Jev questions for bounded dimensions
        questions: List[JevQuestion] = []
        for dim in BOUNDED_JEV_DIMENSIONS:
            rubric = RUBRIC_DEFINITIONS.get(dim, {})
            instructions = f"Evaluate the project's '{dim.replace('_', ' ')}' against the explicit rubric anchors."
            questions.append(
                JevQuestion(
                    id=dim,
                    type=QuestionType.SCORE,
                    instructions=instructions,
                    options=rubric,
                    scale_min=1.0,
                    scale_max=5.0,
                )
            )

        # 3. Check cache
        cache_key = self.cache.compute_cache_key(
            evidence=shared_state,
            dimension_or_type="judge_surface_batch",
            model_version=f"{self.jev.model}_{self.gemini.model}",
            rubric_version=RUBRIC_VERSION,
        )
        cached_result = self.cache.get(cache_key)
        if cached_result:
            return {
                k: DimensionEvaluationResult.model_validate(v)
                for k, v in cached_result.items()
            }

        # 4. Execute Jev shared-state evaluation
        jev_resp = self.jev.evaluate(shared_state, questions)

        # 5. Confidence Gating & Gemini Fallback
        results: Dict[str, DimensionEvaluationResult] = {}
        for q in questions:
            dim = q.id
            q_res = jev_resp.results.get(dim)

            # Special case: missing demo or criteria -> explicit insufficient_evidence
            if dim == "demo_strength" and not has_video_demo and not has_live_deployment:
                results[dim] = DimensionEvaluationResult(
                    dimension=dim,
                    label="insufficient_evidence",
                    score=0.0,
                    confidence=1.0,
                    provider="deterministic_rule",
                    is_insufficient_evidence=True,
                )
                continue

            if dim == "award_alignment" and not award_criteria_text:
                results[dim] = DimensionEvaluationResult(
                    dimension=dim,
                    label="insufficient_evidence",
                    score=0.0,
                    confidence=1.0,
                    provider="deterministic_rule",
                    is_insufficient_evidence=True,
                )
                continue

            # Check if Jev response exists and meets confidence threshold
            if q_res and q_res.confidence >= self.confidence_threshold:
                # High Confidence -> Accept Jev classification
                best_label = str(q_res.value)
                if isinstance(q_res.value, (int, float)):
                    # map numeric score back to closest label
                    best_label = self._score_to_label(float(q_res.value))
                score_val = SCORE_LEVEL_VALUES.get(best_label.lower(), 3.0)

                results[dim] = DimensionEvaluationResult(
                    dimension=dim,
                    label=best_label.lower(),
                    score=score_val,
                    confidence=q_res.confidence,
                    provider="jev",
                    probabilities=q_res.probabilities,
                    fallback_used=False,
                )
            else:
                # Low Confidence or Jev Failure -> Fallback to Gemini
                reason = "jev_confidence_below_threshold" if q_res else "jev_dimension_missing"
                rubric = RUBRIC_DEFINITIONS.get(dim, {})
                gemini_fallback = self.gemini.classify_ambiguous(
                    dimension=dim,
                    untrusted_evidence=shared_state,
                    rubric_anchors=rubric,
                    fallback_reason=reason,
                )
                label = gemini_fallback.get("label", "moderate").lower()
                results[dim] = DimensionEvaluationResult(
                    dimension=dim,
                    label=label,
                    score=SCORE_LEVEL_VALUES.get(label, 3.0),
                    confidence=float(gemini_fallback.get("confidence", 0.80)),
                    provider="gemini",
                    fallback_used=True,
                    fallback_reason=reason,
                )

        # Cache final results
        self.cache.set(cache_key, {k: v.model_dump() for k, v in results.items()})
        return results

    def _score_to_label(self, score: float) -> str:
        if score >= 4.5:
            return "very_strong"
        elif score >= 3.5:
            return "strong"
        elif score >= 2.5:
            return "moderate"
        elif score >= 1.5:
            return "weak"
        return "very_weak"
