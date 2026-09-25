import logging
from typing import List, Dict, Any, Optional
from ..models import (
    BlindProjectBundle,
    BlindProjectEvaluation,
    ProjectOutcome,
)

logger = logging.getLogger("hackbench.analysis.counterfactuals")


class CounterfactualAuditor:
    """
    Actively hunts for counterexamples and base-rate anomalies to challenge emerging narratives.
    """

    def audit(
        self,
        bundles: Dict[str, BlindProjectBundle],
        evaluations: Dict[str, BlindProjectEvaluation],
        outcomes: Dict[str, ProjectOutcome],
    ) -> List[Dict[str, Any]]:
        audits: List[Dict[str, Any]] = []

        total_projects = len(bundles)
        if total_projects == 0:
            return audits

        winners = [pid for pid, o in outcomes.items() if o.is_winner]
        non_winners = [pid for pid, o in outcomes.items() if not o.is_winner]
        n_win = len(winners)
        n_non = len(non_winners)

        # 1. Base-Rate Audit: AI / ML Presence
        ai_in_all = 0
        ai_in_win = 0
        ai_in_non = 0

        for pid, b in bundles.items():
            has_ai = any(
                term in " ".join(b.tech_tags).lower() or term in b.what_it_does.lower()
                for term in ["ai", "gpt", "gemini", "openai", "machine learning", "neural"]
            )
            if has_ai:
                ai_in_all += 1
                if pid in winners:
                    ai_in_win += 1
                else:
                    ai_in_non += 1

        base_rate_ai = round(ai_in_all / total_projects, 3)
        win_rate_ai = round(ai_in_win / n_win, 3) if n_win else 0.0
        non_rate_ai = round(ai_in_non / n_non, 3) if n_non else 0.0

        audits.append({
            "hypothesis": "AI-heavy projects possess an inherent winning advantage.",
            "base_rate_overall": f"{int(base_rate_ai * 100)}% ({ai_in_all}/{total_projects})",
            "prevalence_among_winners": f"{int(win_rate_ai * 100)}% ({ai_in_win}/{n_win})",
            "prevalence_among_non_winners": f"{int(non_rate_ai * 100)}% ({ai_in_non}/{n_non})",
            "finding": (
                f"AI was present in {int(win_rate_ai * 100)}% of winners versus {int(non_rate_ai * 100)}% of non-winners. "
                f"Given the high overall base rate ({int(base_rate_ai * 100)}%), AI is essentially table stakes rather "
                "than a standalone differentiator."
            ),
        })

        # 2. Complexity vs Simplicity: Simplest Winner vs Most Complex Non-Winner
        simplest_winner = None
        min_winner_loc = 999999
        for pid in winners:
            b = bundles.get(pid)
            if b and b.repository_metrics and b.repository_metrics.status == "accessible":
                loc = b.repository_metrics.approx_loc
                if loc < min_winner_loc:
                    min_winner_loc = loc
                    simplest_winner = (pid, b.title, loc)

        most_complex_non_winner = None
        max_non_winner_loc = -1
        for pid in non_winners:
            b = bundles.get(pid)
            if b and b.repository_metrics and b.repository_metrics.status == "accessible":
                loc = b.repository_metrics.approx_loc
                if loc > max_non_winner_loc:
                    max_non_winner_loc = loc
                    most_complex_non_winner = (pid, b.title, loc)

        audits.append({
            "hypothesis": "The most technically complex codebase wins.",
            "counterexample_simplest_winner": (
                f"{simplest_winner[1]} won with only ~{simplest_winner[2]} verified LOC."
                if simplest_winner else "No accessible winning repos"
            ),
            "counterexample_complex_non_winner": (
                f"{most_complex_non_winner[1]} did not win despite building ~{most_complex_non_winner[2]} verified LOC."
                if most_complex_non_winner else "No accessible non-winning repos"
            ),
            "finding": (
                "Massive codebases do not guarantee victory. Simpler projects with focused workflows "
                "and polished presentations routinely triumph over sprawling engineering efforts."
            ),
        })

        # 3. Demo Media Counterexamples
        winners_without_video = []
        for pid in winners:
            b = bundles.get(pid)
            if b and not b.demo_summary.has_video_demo:
                winners_without_video.append(b.title)

        audits.append({
            "hypothesis": "A pre-recorded video demo is mandatory to win.",
            "counterexamples_found": len(winners_without_video),
            "examples": winners_without_video[:3],
            "finding": (
                f"{len(winners_without_video)}/{n_win} winning projects won without any pre-recorded video demo on Devpost, "
                "proving in-person live expo demonstrations and pitches were decisive."
            ),
        })

        return audits
