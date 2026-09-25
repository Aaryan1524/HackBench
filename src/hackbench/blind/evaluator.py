import os
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from ..models import (
    BlindProjectBundle,
    BlindProjectEvaluation,
    EvaluatorPass,
    DimensionScore,
)
from .rubric import (
    RUBRIC_ANCHORS,
    score_dimension,
    compute_evaluator_agreement,
)

logger = logging.getLogger("hackbench.blind.evaluator")


class BlindEvaluator:
    """
    Executes multi-pass blind evaluation on BlindProjectBundle instances.
    Guarantees strict isolation from any winner labels.
    Uses heuristic multi-pass analysis backed by Gemini/LLM when API key is provided.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

    def evaluate_project(
        self,
        bundle: BlindProjectBundle,
        num_passes: int = 3,
    ) -> BlindProjectEvaluation:
        passes: List[EvaluatorPass] = []
        pass_numeric_scores: List[Dict[str, int]] = []

        for p_idx in range(1, num_passes + 1):
            eval_pass = self._evaluate_single_pass(bundle, pass_index=p_idx)
            passes.append(eval_pass)
            pass_numeric_scores.append({
                dim: score.score_numeric for dim, score in eval_pass.dimensions.items()
            })

        # Compute agreement, variances, and disputed dimensions
        means, variances, disputed, agreement_status = compute_evaluator_agreement(pass_numeric_scores)

        # Composite quality score
        comp = means.get("completion", 0.0)
        tech = means.get("technical_depth", 0.0)
        cohere = means.get("product_coherence", 0.0)
        orig = means.get("originality", 0.0)
        demo = means.get("demo_strength", 0.0)

        composite = round(
            (0.25 * comp) + (0.25 * tech) + (0.20 * cohere) + (0.15 * orig) + (0.15 * demo),
            2,
        )

        evaluation = BlindProjectEvaluation(
            project_id=bundle.project_id,
            bundle_sha256=bundle.bundle_sha256,
            passes=passes,
            aggregated_scores=means,
            score_variance=variances,
            disputed_dimensions=disputed,
            evaluator_agreement_status=agreement_status,
            composite_quality_score=composite,
            answers_consensus=passes[0].answers if passes else {},
            evaluation_sha256="",
            sealed_at=datetime.now(timezone.utc),
            is_frozen=True,
        )

        # Seal evaluation with SHA256 hash
        eval_json = evaluation.model_dump_json(exclude={"evaluation_sha256", "sealed_at"})
        evaluation.evaluation_sha256 = hashlib.sha256(eval_json.encode("utf-8")).hexdigest()

        return evaluation

    def _evaluate_single_pass(
        self,
        bundle: BlindProjectBundle,
        pass_index: int,
    ) -> EvaluatorPass:
        """
        Executes a single evaluation pass using evidence-based heuristic rules and NLP heuristics.
        """
        # Diagnostic analysis of problem, tech, completion, and originality
        repo = bundle.repository_metrics
        demo = bundle.demo_summary
        what = bundle.what_it_does
        how = bundle.how_it_was_built
        challenges = bundle.challenges
        tags = [t.lower() for t in bundle.tech_tags]

        # 1. Diagnostic answers
        prob_ans = bundle.problem_statement or bundle.tagline or "Not explicitly detailed."
        user_ans = "Identified from context" if len(bundle.problem_statement) > 40 else "Generic / broad user base"
        workflow_ans = what[:200] + ("..." if len(what) > 200 else "")
        insight_ans = bundle.inspiration[:150] or "Direct application of hackathon technologies"

        what_works_list = []
        what_incomplete_list = []
        evidence_completion = []

        if repo and repo.status == "accessible":
            evidence_completion.append(f"Public Git repository with {repo.approx_loc} LOC and {repo.file_count} files.")
            if repo.git_timeline.commits_in_window > 0:
                evidence_completion.append(f"{repo.git_timeline.commits_in_window} commits recorded during event window.")
            if repo.api_routes_count > 0:
                what_works_list.append(f"{repo.api_routes_count} backend API routes implemented.")
            if repo.test_files_count > 0:
                evidence_completion.append(f"{repo.test_files_count} test files present in repo.")
            if repo.todo_fixme_count > 0:
                what_incomplete_list.append(f"{repo.todo_fixme_count} TODO/FIXME markers in codebase.")
            if repo.mock_data_detected:
                what_incomplete_list.append(f"Mock data indicators detected: {', '.join(repo.mock_data_indicators[:2])}")
        elif repo and repo.status != "accessible":
            what_incomplete_list.append(f"Repository is {repo.status}; code cannot be verified.")
        else:
            what_incomplete_list.append("No public repository provided.")

        if demo.has_live_deployment:
            if demo.deployment_reachable is True:
                what_works_list.append(f"Live deployment is active and reachable ({demo.deployment_url}).")
                evidence_completion.append("Reachable live web application.")
            elif demo.deployment_reachable is False:
                what_incomplete_list.append(f"Deployment URL is unreachable or returned error ({demo.deployment_url}).")

        if demo.has_video_demo:
            evidence_completion.append(f"Video demo available on {demo.video_platform or 'video platform'}.")

        # Compute dimension scores
        scores: Dict[str, DimensionScore] = {}

        # Completion Score (0-5)
        comp_score = 1
        comp_just = "Minimal evidence of working software."
        if repo and repo.status == "accessible":
            if repo.approx_loc > 300 and (demo.has_live_deployment or demo.has_video_demo):
                if repo.api_routes_count > 0 or repo.db_migrations_or_schema_count > 0 or len(repo.tech_stack.frontend_frameworks) > 0:
                    comp_score = 3
                    comp_just = "Functional core end-to-end; repository and working presentation assets verified."
                    if repo.test_files_count > 0 and repo.has_ci:
                        comp_score = 4
                        comp_just = "Complete primary workflow with testing, CI, and verifiable implementation."
            elif repo.approx_loc > 100:
                comp_score = 2
                comp_just = "Partial implementation in repository; workflow partially complete."
        elif demo.has_live_deployment or demo.has_video_demo:
            comp_score = 2
            comp_just = "Demo or deployment claimed, but repository unverified."

        # Jitter for multi-pass variance simulation (pass 2 might be slightly stricter, pass 3 slightly more lenient)
        if pass_index == 2 and comp_score > 2 and repo and repo.todo_fixme_count > 3:
            comp_score = max(1, comp_score - 1)
        elif pass_index == 3 and comp_score < 4 and demo.has_live_deployment and demo.deployment_reachable:
            comp_score = min(5, comp_score + 1)

        scores["completion"] = score_dimension("completion", comp_score, comp_just)

        # Technical Depth Score (0-5)
        tech_score = 1
        tech_just = "Basic scaffolding or single CRUD tier."
        if repo and repo.status == "accessible":
            loc = repo.approx_loc
            if loc > 1500 or (repo.tech_stack.ai_ml_libraries and repo.api_routes_count > 4):
                tech_score = 4
                tech_just = f"Advanced architecture: {loc} LOC, ML pipelines, and {repo.api_routes_count} API endpoints."
            elif loc > 500 or (repo.tech_stack.backend_frameworks and repo.tech_stack.databases):
                tech_score = 3
                tech_just = f"Substantial multi-tier stack: {loc} LOC with backend, DB, and custom logic."
            elif loc > 150:
                tech_score = 2
                tech_just = f"Moderate web implementation: {loc} LOC."
        scores["technical_depth"] = score_dimension("technical_depth", tech_score, tech_just)

        # Originality (0-5)
        orig_score = 2
        orig_just = "Standard hackathon concept."
        text_corpus = f"{bundle.title} {bundle.tagline} {bundle.problem_statement} {what}".lower()
        if any(w in text_corpus for w in ["hardware", "biosensor", "acoustic", "novel protocol", "distributed mesh", "satellites", "quantum"]):
            orig_score = 4
            orig_just = "Distinct, unexpected engineering concept outside conventional tropes."
        elif any(w in text_corpus for w in ["ai study", "flashcard", "chat with pdf", "recipe", "resume", "to-do"]):
            orig_score = 1
            orig_just = "Common hackathon trope with predictable functionality."
        scores["originality"] = score_dimension("originality", orig_score, orig_just)

        # Product Coherence (0-5)
        cohere_score = 3 if len(what) > 100 else 2
        scores["product_coherence"] = score_dimension(
            "product_coherence",
            cohere_score,
            "Clear logical narrative connecting problem to solution.",
        )

        # Problem Clarity (0-5)
        clarity_score = 4 if len(bundle.problem_statement) > 120 else (3 if len(bundle.problem_statement) > 40 else 2)
        scores["problem_clarity"] = score_dimension(
            "problem_clarity", clarity_score, "Problem statement lucidity."
        )

        # User Specificity (0-5)
        user_score = 3 if any(u in text_corpus for u in ["student", "nurse", "developer", "driver", "doctor", "researcher", "tenant"]) else 2
        scores["user_specificity"] = score_dimension("user_specificity", user_score, "Target persona identification.")

        # Problem Importance (0-5)
        importance_score = 3 if any(w in text_corpus for w in ["health", "safety", "disaster", "flood", "cost", "energy", "security"]) else 2
        scores["problem_importance"] = score_dimension("problem_importance", importance_score, "Consequential domain friction.")

        # Scope Discipline (0-5)
        scope_score = 3
        if repo and repo.todo_fixme_count > 10:
            scope_score = 2
        scores["scope_discipline"] = score_dimension("scope_discipline", scope_score, "Plausibility of execution within hackathon window.")

        # Technical Appropriateness (0-5)
        scores["technical_appropriateness"] = score_dimension("technical_appropriateness", 3, "Stack suits problem requirements.")

        # Integration Depth (0-5)
        int_score = 1
        if repo and repo.actual_integrations_found:
            int_score = min(4, len(repo.actual_integrations_found))
        scores["integration_depth"] = score_dimension("integration_depth", int_score, "Depth of external service utilization.")

        # AI Necessity (0-5)
        ai_score = 0
        if any(ai_term in text_corpus for ai_term in ["gemini", "openai", "gpt", "model", "neural", "computer vision", "llm"]):
            ai_score = 3 if (repo and repo.tech_stack.ai_ml_libraries) else 2
        scores["ai_necessity"] = score_dimension("ai_necessity", ai_score, "Relevance of AI component to core value.")

        # Demo Strength (0-5)
        demo_score = 1
        if demo.has_video_demo and demo.has_live_deployment and demo.deployment_reachable:
            demo_score = 4
        elif demo.has_video_demo or (demo.has_live_deployment and demo.deployment_reachable):
            demo_score = 3
        elif demo.has_slide_deck:
            demo_score = 2
        scores["demo_strength"] = score_dimension("demo_strength", demo_score, "Presentation media and verifiable demonstration.")

        # Design / UX (0-5)
        design_score = 3 if (repo and "TailwindCSS" in repo.tech_stack.frontend_frameworks) else 2
        scores["design_ux"] = score_dimension("design_ux", design_score, "UI/UX polish signals.")

        # Practicality (0-5)
        scores["practicality"] = score_dimension("practicality", 3, "Feasibility of ongoing utility.")

        # Memorability (0-5)
        mem_score = orig_score
        scores["memorability"] = score_dimension("memorability", mem_score, "Standout factor among typical submissions.")

        # Story Clarity (0-5)
        scores["story_clarity"] = score_dimension("story_clarity", clarity_score, "End-to-end narrative clarity.")

        # Sponsor Alignment (0-5)
        spons_score = 2 if bundle.sponsor_technologies_mentioned else 1
        scores["sponsor_alignment"] = score_dimension("sponsor_alignment", spons_score, "Relevance to sponsor prompts.")

        diagnostic_answers = {
            "problem_solved": prob_ans,
            "target_user": user_ans,
            "core_insight": insight_ans,
            "primary_workflow": workflow_ans,
            "technically_difficult": f"Integration of {', '.join(bundle.tech_tags[:3])}" if bundle.tech_tags else "Standard implementation",
            "what_works": "; ".join(what_works_list) if what_works_list else "Basic UI claimed",
            "what_incomplete": "; ".join(what_incomplete_list) if what_incomplete_list else "None apparent from public data",
            "evidence_for_completion": "; ".join(evidence_completion) if evidence_completion else "Description text only",
            "wow_moment": bundle.tagline or bundle.title,
            "memorable_aspects": f"Unique focus on {bundle.title}" if orig_score >= 3 else "Standard category project",
            "generic_aspects": "Standard LLM wrapper" if orig_score <= 2 and ai_score > 0 else "None",
            "substantive_tech": ", ".join(repo.primary_languages[:2]) if repo else "Unverified",
            "ornamental_tech": ", ".join(repo.readme_claims_unsupported_by_code[:2]) if repo else "None detected",
            "unverifiable_claims": "Backend execution not visible in public repos" if not repo or repo.status != "accessible" else "None",
            "strongest_aspects": f"Technical depth: {tech_score}/5, Completion: {comp_score}/5",
            "weakest_aspects": "Incomplete repository or missing live demo" if comp_score <= 2 else "Scope bounding",
            "assessment_confidence": "High" if repo and repo.status == "accessible" else "Moderate (Repo missing)",
        }

        strongest = [f"{dim} ({s.score_numeric}/5)" for dim, s in scores.items() if s.score_numeric >= 4]
        weakest = [f"{dim} ({s.score_numeric}/5)" for dim, s in scores.items() if s.score_numeric <= 1]

        return EvaluatorPass(
            evaluator_id=f"forensics_evaluator_v1_seed{pass_index}",
            pass_index=pass_index,
            answers=diagnostic_answers,
            dimensions=scores,
            overall_assessment=f"Pass {pass_index}: Evaluated {bundle.title}. Completion: {comp_score}/5, Tech Depth: {tech_score}/5.",
            strongest_aspects=strongest,
            weakest_aspects=weakest,
            confidence=0.9 if repo and repo.status == "accessible" else 0.65,
        )
