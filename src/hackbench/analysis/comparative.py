import math
import logging
from typing import List, Dict, Any, Optional, Tuple
from ..models import (
    BlindProjectBundle,
    BlindProjectEvaluation,
    ProjectOutcome,
    CohortMetricComparison,
)

logger = logging.getLogger("hackbench.analysis.comparative")


def calculate_cohens_d(group_a: List[float], group_b: List[float]) -> Optional[float]:
    if len(group_a) < 2 or len(group_b) < 2:
        return None
    mean_a = sum(group_a) / len(group_a)
    mean_b = sum(group_b) / len(group_b)
    var_a = sum((x - mean_a) ** 2 for x in group_a) / (len(group_a) - 1)
    var_b = sum((x - mean_b) ** 2 for x in group_b) / (len(group_b) - 1)
    pooled_sd = math.sqrt(((len(group_a) - 1) * var_a + (len(group_b) - 1) * var_b) / (len(group_a) + len(group_b) - 2))
    if pooled_sd == 0:
        return 0.0
    return round((mean_a - mean_b) / pooled_sd, 2)


def calculate_odds_ratio(
    a_success: int, a_total: int, b_success: int, b_total: int
) -> Optional[float]:
    a_fail = a_total - a_success
    b_fail = b_total - b_success
    if b_success == 0 or a_fail == 0:
        return None  # division by zero or infinite
    return round((a_success * b_fail) / (a_fail * b_success), 2)


class ComparativeAnalyzer:
    """
    Executes statistical cohort comparisons across winners and non-winners.
    Uses descriptive statistics, effect sizes (Cohen's d), and odds ratios.
    Never asserts causal relationships.
    """

    def compare_cohorts(
        self,
        cohort_a_name: str,
        cohort_a_ids: List[str],
        cohort_b_name: str,
        cohort_b_ids: List[str],
        evaluations: Dict[str, BlindProjectEvaluation],
        bundles: Dict[str, BlindProjectBundle],
    ) -> List[CohortMetricComparison]:
        comparisons: List[CohortMetricComparison] = []
        n_a = len(cohort_a_ids)
        n_b = len(cohort_b_ids)

        if n_a == 0 or n_b == 0:
            return comparisons

        # Numeric dimensions to compare
        dimensions = [
            "composite_quality_score",
            "completion",
            "technical_depth",
            "product_coherence",
            "originality",
            "demo_strength",
            "design_ux",
            "problem_clarity",
            "ai_necessity",
            "sponsor_alignment",
        ]

        for dim in dimensions:
            vals_a: List[float] = []
            vals_b: List[float] = []

            for pid in cohort_a_ids:
                if pid in evaluations:
                    ev = evaluations[pid]
                    val = ev.composite_quality_score if dim == "composite_quality_score" else ev.aggregated_scores.get(dim, 0.0)
                    vals_a.append(val)

            for pid in cohort_b_ids:
                if pid in evaluations:
                    ev = evaluations[pid]
                    val = ev.composite_quality_score if dim == "composite_quality_score" else ev.aggregated_scores.get(dim, 0.0)
                    vals_b.append(val)

            if not vals_a or not vals_b:
                continue

            mean_a = round(sum(vals_a) / len(vals_a), 2)
            mean_b = round(sum(vals_b) / len(vals_b), 2)
            diff = round(mean_a - mean_b, 2)
            d = calculate_cohens_d(vals_a, vals_b)

            interp = "Negligible difference"
            if d is not None:
                if abs(d) >= 0.8:
                    interp = f"Large effect size ({'higher' if d > 0 else 'lower'} in {cohort_a_name})"
                elif abs(d) >= 0.5:
                    interp = f"Moderate effect size ({'higher' if d > 0 else 'lower'} in {cohort_a_name})"
                elif abs(d) >= 0.2:
                    interp = f"Small effect size ({'higher' if d > 0 else 'lower'} in {cohort_a_name})"

            comparisons.append(
                CohortMetricComparison(
                    dimension_or_feature=dim,
                    group_a_name=cohort_a_name,
                    group_b_name=cohort_b_name,
                    mean_a=mean_a,
                    mean_b=mean_b,
                    diff=diff,
                    cohens_d=d,
                    sample_a=len(vals_a),
                    sample_b=len(vals_b),
                    interpretation=interp,
                )
            )

        # Binary feature odds ratios
        binary_features = [
            ("has_video_demo", lambda b: b.demo_summary.has_video_demo),
            ("has_live_deployment", lambda b: b.demo_summary.has_live_deployment),
            ("has_public_repo", lambda b: b.repository_metrics and b.repository_metrics.status == "accessible"),
            ("has_tests", lambda b: b.repository_metrics and b.repository_metrics.test_files_count > 0),
            ("has_ci", lambda b: b.repository_metrics and b.repository_metrics.has_ci),
            ("ai_present", lambda b: any("ai" in t or "gpt" in t or "gemini" in t for t in [x.lower() for x in b.tech_tags])),
        ]

        for feat_name, pred in binary_features:
            succ_a = sum(1 for pid in cohort_a_ids if pid in bundles and pred(bundles[pid]))
            succ_b = sum(1 for pid in cohort_b_ids if pid in bundles and pred(bundles[pid]))

            prop_a = round(succ_a / n_a, 2) if n_a else 0.0
            prop_b = round(succ_b / n_b, 2) if n_b else 0.0
            diff = round(prop_a - prop_b, 2)
            or_val = calculate_odds_ratio(succ_a, n_a, succ_b, n_b)

            comparisons.append(
                CohortMetricComparison(
                    dimension_or_feature=feat_name,
                    group_a_name=cohort_a_name,
                    group_b_name=cohort_b_name,
                    mean_a=prop_a,
                    mean_b=prop_b,
                    diff=diff,
                    odds_ratio=or_val,
                    sample_a=n_a,
                    sample_b=n_b,
                    interpretation=f"{cohort_a_name}: {int(prop_a*100)}% vs {cohort_b_name}: {int(prop_b*100)}%",
                )
            )

        return comparisons
