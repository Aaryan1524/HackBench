import math
import logging
from typing import List, Dict, Tuple, Optional

from ..models import (
    BlindProjectEvaluation,
    ProjectOutcome,
    MismatchClassification,
    ProjectForensicRecord,
    StrongNonWinner,
)

logger = logging.getLogger("hackbench.analysis.mismatches")


class MismatchAnalyzer:
    """
    Analyzes degree of alignment between blind project quality evaluations and official judging outcomes.
    INVARIANT:
    Never manipulates or smooths analysis to justify an official result.
    Disagreements are explicitly captured and preserved as 'evidence_conflicts_with_outcome'.
    """

    def classify_project(
        self,
        project_id: str,
        slug: str,
        title: str,
        evaluation: BlindProjectEvaluation,
        outcome: ProjectOutcome,
        all_evaluations: Dict[str, BlindProjectEvaluation],
        all_outcomes: Dict[str, ProjectOutcome],
        strong_non_winners: List[StrongNonWinner],
    ) -> ProjectForensicRecord:
        score = evaluation.composite_quality_score
        comp = evaluation.aggregated_scores.get("completion", 0.0)
        tech = evaluation.aggregated_scores.get("technical_depth", 0.0)

        comparable_non_winners: List[str] = []
        unobserved_hypotheses: List[str] = []

        if not outcome.is_winner:
            # For non-winners
            if score >= 3.2 and comp >= 3.0 and tech >= 3.0:
                classification = MismatchClassification.EVIDENCE_CONFLICTS
                explanation = (
                    f"Strong non-winner: Evaluated at composite {score:.2f} (Completion: {comp:.1f}, "
                    f"Tech: {tech:.1f}) but received no official awards."
                )
                unobserved_hypotheses = [
                    "Live judging pitch may not have resonated or encountered technical questions.",
                    "Project category had unusually fierce competition during judging rounds.",
                    "Judges prioritized novel conceptual ideas over raw implementation completeness.",
                ]
            else:
                classification = MismatchClassification.EVIDENCE_STRONGLY_SUPPORTS
                explanation = f"Non-winner with composite score {score:.2f}; consistent with median non-winning cohort."
            
            return ProjectForensicRecord(
                project_id=project_id,
                slug=slug,
                title=title,
                blind_evaluation=evaluation,
                outcome=outcome,
                mismatch_classification=classification,
                mismatch_explanation=explanation,
                comparable_non_winners=[],
                unobserved_factor_hypotheses=unobserved_hypotheses,
            )

        # WINNER ANALYSIS:
        # Check if public evidence is insufficient
        if comp <= 1.5 and tech <= 1.5:
            classification = MismatchClassification.INSUFFICIENT_EVIDENCE
            explanation = (
                f"Winner with low observable public evidence (Composite: {score:.2f}, Completion: {comp:.1f}, Tech: {tech:.1f}). "
                "The public repository or demo lacks sufficient artifact depth to explain the win from public evidence alone."
            )
            unobserved_hypotheses = [
                "Exceptional live presentation, charisma, or stage demo during in-person expo judging.",
                "Working demo shown locally on judges' laptops/phones that was not committed to public GitHub.",
                "Compelling pitch and personal story aligned directly with sponsor representatives.",
                "Private technical components demonstrated directly to judges that remain closed-source.",
            ]
            return ProjectForensicRecord(
                project_id=project_id,
                slug=slug,
                title=title,
                blind_evaluation=evaluation,
                outcome=outcome,
                mismatch_classification=classification,
                mismatch_explanation=explanation,
                comparable_non_winners=comparable_non_winners,
                unobserved_factor_hypotheses=unobserved_hypotheses,
            )

        # Find comparable non-winners that scored higher than this winner
        for snw in strong_non_winners:
            if snw.composite_quality_score > score + 0.3:
                comparable_non_winners.append(f"{snw.title} (Score: {snw.composite_quality_score:.2f})")

        if len(comparable_non_winners) >= 3 and score < 3.0:
            classification = MismatchClassification.EVIDENCE_CONFLICTS
            explanation = (
                f"Evidence conflicts with outcome: Winner scored {score:.2f}, whereas multiple non-winning "
                f"projects ({', '.join(comparable_non_winners[:2])}) demonstrated significantly higher verified "
                "completion and technical depth."
            )
            unobserved_hypotheses = [
                "Unobserved live demonstration dynamics or high-charisma oral presentation.",
                "Sponsor relationship, specific sponsor rubric nuances, or off-repo criteria.",
                "Judges valued narrative pitch and market potential over software architecture completeness.",
                "Judging variance: different judging panels possessed different evaluation standards.",
            ]
        elif len(comparable_non_winners) >= 1:
            classification = MismatchClassification.EVIDENCE_DOES_NOT_CLEARLY_DISTINGUISH
            explanation = (
                f"Evidence does not clearly distinguish winner: Scored {score:.2f}. "
                f"Comparable non-winners ({', '.join(comparable_non_winners[:2])}) exhibited equal or slightly higher verified metrics."
            )
            unobserved_hypotheses = [
                "Live demo execution differentiated this project from comparable non-winners.",
                "Specific judge preference for this application domain or UI styling.",
            ]
        elif score >= 3.6:
            classification = MismatchClassification.EVIDENCE_STRONGLY_SUPPORTS
            explanation = (
                f"Evidence strongly supports outcome: Winner demonstrated robust verified execution "
                f"(Composite: {score:.2f}, Completion: {comp:.1f}, Tech: {tech:.1f}) with working repository and demo."
            )
            unobserved_hypotheses = []
        else:
            classification = MismatchClassification.EVIDENCE_MODERATELY_SUPPORTS
            explanation = (
                f"Evidence moderately supports outcome: Project achieved solid execution (Composite: {score:.2f}) "
                "with verified functionality."
            )
            unobserved_hypotheses = [
                "Sponsor challenge criteria directly targeted by this solution.",
            ]

        return ProjectForensicRecord(
            project_id=project_id,
            slug=slug,
            title=title,
            blind_evaluation=evaluation,
            outcome=outcome,
            mismatch_classification=classification,
            mismatch_explanation=explanation,
            comparable_non_winners=comparable_non_winners,
            unobserved_factor_hypotheses=unobserved_hypotheses,
        )
