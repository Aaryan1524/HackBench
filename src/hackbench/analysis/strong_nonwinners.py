import logging
from typing import List, Dict
from ..models import (
    BlindProjectBundle,
    BlindProjectEvaluation,
    ProjectOutcome,
    StrongNonWinner,
)

logger = logging.getLogger("hackbench.analysis.strong_nonwinners")


class StrongNonWinnerDetector:
    """
    Identifies high-quality non-winning projects using purely blind evaluation scores.
    """

    def find_strong_non_winners(
        self,
        bundles: Dict[str, BlindProjectBundle],
        evaluations: Dict[str, BlindProjectEvaluation],
        outcomes: Dict[str, ProjectOutcome],
        min_composite_score: float = 2.8,
        min_completion: float = 2.5,
        min_tech_depth: float = 2.5,
    ) -> List[StrongNonWinner]:
        candidates: List[StrongNonWinner] = []

        for pid, evaln in evaluations.items():
            outcome = outcomes.get(pid)
            # Must be a non-winner
            if outcome and outcome.is_winner:
                continue

            comp = evaln.aggregated_scores.get("completion", 0.0)
            tech = evaln.aggregated_scores.get("technical_depth", 0.0)
            cohere = evaln.aggregated_scores.get("product_coherence", 0.0)
            composite = evaln.composite_quality_score

            if composite >= min_composite_score and comp >= min_completion and tech >= min_tech_depth:
                bundle = bundles.get(pid)
                repo_url = bundle.repository_metrics.repo_url if bundle and bundle.repository_metrics else None
                demo_url = bundle.demo_summary.video_url or bundle.demo_summary.deployment_url if bundle else None
                title = bundle.title if bundle else pid
                slug = bundle.slug if bundle else pid

                strengths = []
                for p in evaln.passes:
                    strengths.extend(p.strongest_aspects)
                strengths = list(dict.fromkeys(strengths))[:4]

                why = (
                    f"Demonstrated verified engineering depth (Tech: {tech:.1f}/5, Completion: {comp:.1f}/5) "
                    f"and cohesive product scope (Composite: {composite:.2f}) with working repository code."
                )

                candidates.append(
                    StrongNonWinner(
                        project_id=pid,
                        slug=slug,
                        title=title,
                        composite_quality_score=composite,
                        completion_score=comp,
                        technical_depth_score=tech,
                        product_coherence_score=cohere,
                        repo_url=repo_url,
                        demo_url=demo_url,
                        key_strengths=strengths,
                        why_it_stands_out=why,
                    )
                )

        # Sort descending by composite score
        candidates.sort(key=lambda x: x.composite_quality_score, reverse=True)
        logger.info(f"Discovered {len(candidates)} strong non-winning projects.")
        return candidates
