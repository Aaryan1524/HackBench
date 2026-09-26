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
from .chatgpt import ChatGPTClient, GeminiClient, ParticipantReportSynthesis
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

IDEA_ANALYSIS_DIMENSIONS = [
    "problem_clarity",
    "user_clarity",
    "product_clarity",
    "originality",
    "practicality",
    "scope_clarity",
    "story_clarity",
    "potential_demo_clarity",
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
    jev_confidence: Optional[float] = None
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
        analysis_mode: str = "project",
        has_repository: bool = False,
        text_from_readme: bool = False,
    ) -> Dict[str, DimensionEvaluationResult]:
        """
        Evaluates the judge-facing presentation surface.
        In 'project' mode: evaluates all 9 canonical post-implementation dimensions.
        In 'idea' mode: evaluates idea-stage dimensions and explicitly marks implementation/completion
        as 'not_evaluated' (never 'weak').
        """
        is_idea_mode = (analysis_mode == "idea")

        # 1. Construct compact, unified project state
        if is_idea_mode:
            state_parts = [
                f"STAGE: Pre-pitch Idea (Unbuilt Concept)",
                f"IDEA TITLE: {project_name}",
                f"CONCEPT PITCH: {tagline or 'N/A'}",
                f"\nPROBLEM STATEMENT:\n{problem or 'Not explicitly articulated'}",
                f"\nTARGET USER:\n{target_user or 'Not specified'}",
                f"\nPROPOSED PRODUCT & WORKFLOW:\n{what_it_does or 'N/A'}\n{how_it_works or 'N/A'}",
                f"\nSTAGE INVARIANT: Neither repository, working code, deployment, nor video demo exist yet.",
            ]
        else:
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

        if not is_idea_mode and not has_video_demo and not has_live_deployment:
            state_parts.append("\nEVIDENCE LIMITATIONS: Neither interactive deployment nor video demo available.")

        shared_state = "\n".join(state_parts)

        # 2. Build Jev questions for active dimensions
        active_dimensions = IDEA_ANALYSIS_DIMENSIONS if is_idea_mode else BOUNDED_JEV_DIMENSIONS
        questions: List[JevQuestion] = []
        for dim in active_dimensions:
            rubric = RUBRIC_DEFINITIONS.get(dim, {})
            instructions = f"Evaluate the candidate's '{dim.replace('_', ' ')}' against the explicit rubric anchors."
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
            dimension_or_type=f"judge_surface_batch_{analysis_mode}",
            model_version=f"{self.jev.model}_{self.gemini.model}_jev{int(self.jev.is_configured)}_gpt{int(self.gemini.is_configured)}",
            rubric_version=RUBRIC_VERSION,
        )
        cached_result = self.cache.get(cache_key)
        if cached_result:
            cached = {k: DimensionEvaluationResult.model_validate(v) for k, v in cached_result.items()}
            return self._gate_on_evidence(
                cached, is_idea_mode, problem, target_user, what_it_does, how_it_works, tagline,
                has_video_demo, has_live_deployment, has_repository, text_from_readme,
            )

        # 4. Evaluation Routing: Jev (Layer 2) if configured, else ChatGPT batch classification
        results: Dict[str, DimensionEvaluationResult] = {}

        # Critical Invariant: In Idea Mode, completion and demo MUST be marked not_evaluated (not weak)
        if is_idea_mode:
            results["completion_appearance"] = DimensionEvaluationResult(
                dimension="completion_appearance",
                label="not_evaluated",
                score=0.0,
                confidence=1.0,
                provider="deterministic_rule",
                is_insufficient_evidence=False,
            )
            results["demo_strength"] = DimensionEvaluationResult(
                dimension="demo_strength",
                label="not_evaluated",
                score=0.0,
                confidence=1.0,
                provider="deterministic_rule",
                is_insufficient_evidence=False,
            )

        if self.jev.is_configured:
            # Jev Layer 2 with confidence gating to ChatGPT
            jev_resp = self.jev.evaluate(shared_state, questions)
            for q in questions:
                dim = q.id
                q_res = jev_resp.results.get(dim)

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

                if q_res and q_res.confidence >= self.confidence_threshold:
                    best_label = str(q_res.value)
                    if isinstance(q_res.value, (int, float)):
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
                        jev_confidence=q_res.confidence,
                    )
                else:
                    reason = "jev_confidence_below_threshold" if q_res else "jev_dimension_missing"
                    rubric = RUBRIC_DEFINITIONS.get(dim, {})
                    chatgpt_fallback = self.gemini.classify_ambiguous(
                        dimension=dim,
                        untrusted_evidence=shared_state,
                        rubric_anchors=rubric,
                        fallback_reason=reason,
                    )
                    label = chatgpt_fallback.get("label", "moderate").lower()
                    results[dim] = DimensionEvaluationResult(
                        dimension=dim,
                        label=label,
                        score=SCORE_LEVEL_VALUES.get(label, 3.0),
                        confidence=float(chatgpt_fallback.get("confidence", 0.80)),
                        provider="chatgpt",
                        fallback_used=True,
                        fallback_reason=reason,
                        jev_confidence=q_res.confidence if q_res else None,
                    )
        elif self.gemini.is_configured:
            # JEV_API_KEY not yet configured: Route directly through ChatGPT
            logger.info("JEV_API_KEY not configured. Evaluating rubric dimensions via ChatGPT batch classification.")
            batch_evals = self.gemini.classify_batch(
                untrusted_evidence=shared_state,
                dimensions=active_dimensions,
                rubrics=RUBRIC_DEFINITIONS,
            )
            for q in questions:
                dim = q.id

                if dim in results:
                    # Pre-populated invariant (e.g. not_evaluated in idea mode)
                    continue

                if dim == "demo_strength" and not is_idea_mode and not has_video_demo and not has_live_deployment:
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

                dim_eval = batch_evals.get(dim, {})
                label = str(dim_eval.get("label", "moderate")).lower()
                conf = float(dim_eval.get("confidence", 0.85))
                score_val = SCORE_LEVEL_VALUES.get(label, 3.0)

                results[dim] = DimensionEvaluationResult(
                    dimension=dim,
                    label=label,
                    score=score_val,
                    confidence=conf,
                    provider="chatgpt",
                    fallback_used=True,
                    fallback_reason="jev_key_not_configured",
                    jev_confidence=None,
                )
        else:
            # Neither API key configured: Fall back to local calibrated heuristics
            jev_resp = self.jev.evaluate(shared_state, questions)
            for q in questions:
                dim = q.id
                if dim in results:
                    continue
                q_res = jev_resp.results.get(dim)
                best_label = str(q_res.value) if q_res else "moderate"
                if q_res and isinstance(q_res.value, (int, float)):
                    best_label = self._score_to_label(float(q_res.value))
                score_val = SCORE_LEVEL_VALUES.get(best_label.lower(), 3.0)
                results[dim] = DimensionEvaluationResult(
                    dimension=dim,
                    label=best_label.lower(),
                    score=score_val,
                    confidence=q_res.confidence if q_res else 0.80,
                    provider="offline_calibrated",
                    fallback_used=True,
                    fallback_reason="no_api_keys_configured",
                )

        # Cross-map originality and memorability for shared schemas
        if "originality" in results and "memorability" not in results:
            results["memorability"] = results["originality"]
        elif "memorability" in results and "originality" not in results:
            results["originality"] = results["memorability"]

        # Log router provider telemetry for auditability
        for dim, res in results.items():
            logger.info(
                f"[Router Telemetry] {dim}: provider={res.provider}, fallback={res.fallback_used} "
                f"(reason={res.fallback_reason}), conf={res.confidence:.2f}, jev_conf={res.jev_confidence}"
            )

        # Cache final results
        # Never cache offline fallback ratings: they would be served later even once an AI provider is available.
        if not any(v.provider == "offline_calibrated" for v in results.values()):
            self.cache.set(cache_key, {k: v.model_dump() for k, v in results.items()})
        return self._gate_on_evidence(
            results, is_idea_mode, problem, target_user, what_it_does, how_it_works, tagline,
            has_video_demo, has_live_deployment, has_repository, text_from_readme,
        )

    @staticmethod
    def _gate_on_evidence(
        results: Dict[str, "DimensionEvaluationResult"],
        is_idea_mode: bool,
        problem: Optional[str],
        target_user: Optional[str],
        what_it_does: Optional[str],
        how_it_works: Optional[str],
        tagline: Optional[str],
        has_video_demo: bool,
        has_live_deployment: bool,
        has_repository: bool,
        text_from_readme: bool = False,
    ) -> Dict[str, "DimensionEvaluationResult"]:
        """
        Whatever provider produced the labels, a dimension with no submitted evidence is
        'insufficient_evidence', never 'weak'. Idea mode is handled separately (not_evaluated).
        """
        if is_idea_mode:
            return results

        text = {
            "problem": (problem or "").strip(),
            "user": (target_user or "").strip(),
            "what": (what_it_does or "").strip(),
            "how": (how_it_works or "").strip(),
            "tagline": (tagline or "").strip(),
        }
        no_description = not any(text.values())
        no_product_text = not (text["what"] or text["how"] or text["tagline"])
        no_build_evidence = not (has_repository or has_live_deployment or has_video_demo)

        missing = set()
        # A README is one block of prose, not separate problem/user fields: let the reviewer judge those from it.
        if not text["problem"] and not text_from_readme:
            missing.add("problem_clarity")
        if not text["user"] and not text_from_readme:
            missing.add("user_clarity")
        if no_product_text:
            missing.add("product_clarity")
        if not (has_video_demo or has_live_deployment):
            missing.add("demo_strength")
        if no_build_evidence:
            missing.add("completion_appearance")
        if no_description:
            missing.update({
                "story_clarity", "memorability", "originality", "practicality", "award_alignment",
                "completion_appearance", "demo_strength",
            })

        gated = dict(results)
        for dim in missing:
            if dim in gated:
                gated[dim] = DimensionEvaluationResult(
                    dimension=dim,
                    label="insufficient_evidence",
                    score=0.0,
                    confidence=1.0,
                    provider="deterministic_rule",
                    is_insufficient_evidence=True,
                )
        return gated

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
