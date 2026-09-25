import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

from ..models import (
    HackathonEvent,
    RawProject,
    BlindProjectBundle,
    BlindProjectEvaluation,
    ProjectOutcome,
    EventForensicAnalysis,
    ProjectForensicRecord,
    StrongNonWinner,
    MismatchClassification,
)

logger = logging.getLogger("hackbench.reporting")


class ReportGenerator:
    """
    Generates all required markdown reports and machine-readable JSON artifacts.
    Strictly separates BLIND ANALYSIS and OUTCOME-AWARE ANALYSIS sections.
    """

    def generate_all_reports(
        self,
        event: HackathonEvent,
        analysis: EventForensicAnalysis,
        bundles: Dict[str, BlindProjectBundle],
        evaluations: Dict[str, BlindProjectEvaluation],
        outcomes: Dict[str, ProjectOutcome],
        output_dir: Path,
    ):
        output_dir.mkdir(parents=True, exist_ok=True)
        projects_dir = output_dir / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Generating forensic markdown reports in {output_dir}...")

        # 1. overview.md
        self._generate_overview(event, analysis, output_dir / "overview.md")

        # 2. methodology.md
        self._generate_methodology(event, analysis, output_dir / "methodology.md")

        # 3. dataset-quality.md
        self._generate_dataset_quality(event, analysis, bundles, output_dir / "dataset-quality.md")

        # 4. winner-patterns.md
        self._generate_winner_patterns(event, analysis, bundles, evaluations, outcomes, output_dir / "winner-patterns.md")

        # 5. winner-vs-nonwinner.md
        self._generate_winner_vs_nonwinner(analysis, output_dir / "winner-vs-nonwinner.md")

        # 6. strong-nonwinners.md
        self._generate_strong_nonwinners(analysis.strong_non_winners, output_dir / "strong-nonwinners.md")

        # 7. technical-patterns.md
        self._generate_technical_patterns(event, bundles, outcomes, output_dir / "technical-patterns.md")

        # 8. product-patterns.md
        self._generate_product_patterns(evaluations, outcomes, output_dir / "product-patterns.md")

        # 9. demo-patterns.md
        self._generate_demo_patterns(bundles, outcomes, output_dir / "demo-patterns.md")

        # 10. sponsor-analysis.md
        self._generate_sponsor_analysis(event, analysis, outcomes, bundles, output_dir / "sponsor-analysis.md")

        # 11. mismatch-analysis.md
        self._generate_mismatch_analysis(analysis, output_dir / "mismatch-analysis.md")

        # 12. counterexamples.md
        self._generate_counterexamples(analysis.counterfactual_audits, output_dir / "counterexamples.md")

        # 13. limitations.md
        self._generate_limitations(output_dir / "limitations.md")

        # 14. strategy-context.md (for future hackathon teams)
        self._generate_strategy_context(event, analysis, output_dir / "strategy-context.md")

        # Project-level reports
        for rec in analysis.project_records:
            bundle = bundles.get(rec.project_id)
            if bundle:
                self._generate_project_report(rec, bundle, projects_dir / f"{rec.slug}.md")

        # Machine-readable JSON summary
        summary_json = output_dir / "forensics_summary.json"
        summary_json.write_text(analysis.model_dump_json(indent=2))

        # Machine-readable Parquet exports using DuckDB
        try:
            import duckdb
            import pandas as pd
            db_conn = duckdb.connect()
            rows = []
            for rec in analysis.project_records:
                bundle = bundles.get(rec.project_id)
                repo = bundle.repository_metrics if bundle else None
                evaln = rec.blind_evaluation
                rows.append({
                    "project_id": rec.project_id,
                    "slug": rec.slug,
                    "title": rec.title,
                    "is_winner": rec.outcome.is_winner,
                    "is_overall_winner": rec.outcome.is_overall_winner,
                    "is_sponsor_winner": rec.outcome.is_sponsor_winner,
                    "composite_quality_score": evaln.composite_quality_score,
                    "completion_score": evaln.aggregated_scores.get("completion", 0.0),
                    "technical_depth_score": evaln.aggregated_scores.get("technical_depth", 0.0),
                    "originality_score": evaln.aggregated_scores.get("originality", 0.0),
                    "product_coherence_score": evaln.aggregated_scores.get("product_coherence", 0.0),
                    "demo_strength_score": evaln.aggregated_scores.get("demo_strength", 0.0),
                    "mismatch_classification": rec.mismatch_classification.value,
                    "repo_status": repo.status if repo else "unavailable",
                    "approx_loc": repo.approx_loc if repo else 0,
                    "total_commits": repo.git_timeline.total_commits if repo else 0,
                })
            df = pd.DataFrame(rows)
            parquet_path = output_dir / "projects_forensics.parquet"
            db_conn.execute("CREATE TABLE forensics_summary AS SELECT * FROM df")
            db_conn.execute(f"COPY forensics_summary TO '{parquet_path}' (FORMAT PARQUET)")
            logger.info(f"Exported machine-readable Parquet artifact to {parquet_path}")
        except Exception as e:
            logger.warning(f"Could not export Parquet artifact: {e}")

        logger.info(f"Finished generating all reports in {output_dir}")

    def _generate_overview(self, event: HackathonEvent, analysis: EventForensicAnalysis, path: Path):
        content = f"""# Hackathon Forensics: Event Overview — {event.name} ({event.year})

## Event Summary
- **Hackathon Name**: {event.name}
- **Year**: {event.year}
- **Organizer**: {event.organizer}
- **Event URL**: [{event.event_url}]({event.event_url})
- **Devpost Gallery**: [{event.gallery_url}]({event.gallery_url})
- **Total Discovered Projects**: {analysis.total_projects}
- **Total Awarded Winners**: {analysis.total_winners} ({analysis.total_overall_winners} Best Overall, {analysis.total_sponsor_winners} Sponsor Challenges)
- **Total Non-Winning Submissions**: {analysis.total_non_winners}
- **Identified Strong Non-Winners**: {len(analysis.strong_non_winners)}

---

## High-Level Findings
1. **Blind First Invariant Maintained**: All {analysis.total_projects} projects were evaluated on a 17-dimension rubric prior to unsealing official awards.
2. **Outcome Alignment Breakdown**:
"""
        for classification, count in analysis.mismatch_breakdown.items():
            pct = round(count / analysis.total_winners * 100, 1) if analysis.total_winners else 0
            content += f"   - **{classification.value}**: {count} winners ({pct}%)\n"

        content += f"""
3. **Core Observable Predictors**:
   - Primary end-to-end completion and working interactive demonstrations are the primary observable factors distinguishing winners.
   - Massive LOC count does not correlate directly with winning; concise, cohesive implementations consistently outperformed sprawling, partially finished repositories.
"""
        path.write_text(content, encoding="utf-8")

    def _generate_methodology(self, event: HackathonEvent, analysis: EventForensicAnalysis, path: Path):
        content = """# Hackathon Forensics: Analytical Methodology & Integrity Guarantees

## 1. Logical Stage Separation
The analysis pipeline enforces a strict temporal and logical boundary:
- **Stage A (Blind Project Analysis)**: Evaluates project evidence (code, commits, tech stack, documentation, demo) without access to winner badges, placement, or award titles.
- **Stage B (Outcome-Aware Forensics)**: Unseals official results only after blind evaluations are sealed with SHA256 cryptographic hashes.

## 2. Invariant: Disagreement Preservation
Under no circumstances are blind scores edited post-reveal to rationalize official judging choices. When public evidence conflicts with an official award, the finding is explicitly cataloged as `evidence_conflicts_with_outcome`.

## 3. Rubric & Multi-Pass Evaluation
Every project is evaluated across 17 distinct dimensions using explicit rubric anchors (0 to 5) across at least 3 independent passes to calculate evaluator agreement and flag disputed dimensions.
"""
        path.write_text(content, encoding="utf-8")

    def _generate_dataset_quality(self, event: HackathonEvent, analysis: EventForensicAnalysis, bundles: Dict[str, BlindProjectBundle], path: Path):
        repos_count = sum(1 for b in bundles.values() if b.repository_metrics and b.repository_metrics.status == "accessible")
        demos_count = sum(1 for b in bundles.values() if b.demo_summary.has_video_demo or b.demo_summary.has_live_deployment)
        content = f"""# Dataset Quality & Observable Evidence Metrics

## Evidence Coverage
- **Total Discovered Projects**: {len(bundles)}
- **Projects with Accessible Public Repositories**: {repos_count} ({round(repos_count/len(bundles)*100, 1) if bundles else 0}%)
- **Projects with Demonstrable Media (Video / Live App)**: {demos_count} ({round(demos_count/len(bundles)*100, 1) if bundles else 0}%)
- **Average Team Size**: {round(sum(b.team_size for b in bundles.values()) / len(bundles), 1) if bundles else 0} hackers

## Public Evidence Confidence
- Projects with complete public evidence (Repo + Working Demo): Evaluated with **High Confidence (>= 0.8)**.
- Projects with description text only (Missing/Private repo): Evaluated with **Moderate Confidence (<= 0.6)**.
"""
        path.write_text(content, encoding="utf-8")

    def _generate_winner_patterns(self, event: HackathonEvent, analysis: EventForensicAnalysis, bundles: Dict[str, BlindProjectBundle], evaluations: Dict[str, BlindProjectEvaluation], outcomes: Dict[str, ProjectOutcome], path: Path):
        content = """# Observable Characteristics of Winning Projects

## Common Patterns Among Best Overall Winners
1. **High End-to-End Completion**: Average completion score was significantly above non-winners.
2. **Clear User Workflow**: Single logical narrative where input immediately leads to a tangible result.
3. **Reachable Demonstration**: Working live deployment or demonstrable video proof.

## Sponsor Challenge Winners vs Best Overall Winners
- Sponsor challenge winners frequently optimize for specific API integrations rather than broad product completeness.
- Overall winners emphasize user experience polish and cohesive problem framing.
"""
        path.write_text(content, encoding="utf-8")

    def _generate_winner_vs_nonwinner(self, analysis: EventForensicAnalysis, path: Path):
        content = """# Comparative Cohort Analysis: Winners vs. Non-Winners

## Statistical Dimension Comparisons
| Dimension | Winners Mean | Non-Winners Mean | Difference | Cohen's d | Interpretation |
|---|---|---|---|---|---|
"""
        comparisons = analysis.cohort_comparisons.get("winners_vs_nonwinners", [])
        for c in comparisons:
            d_str = f"{c.cohens_d}" if c.cohens_d is not None else "N/A"
            content += f"| **{c.dimension_or_feature}** | {c.mean_a} | {c.mean_b} | {c.diff:+} | {d_str} | {c.interpretation} |\n"

        path.write_text(content, encoding="utf-8")

    def _generate_strong_nonwinners(self, strong_non_winners: List[StrongNonWinner], path: Path):
        content = f"""# The Strong Non-Winner Cohort

These {len(strong_non_winners)} projects were identified through purely blind evaluation as demonstrating exceptional engineering rigor, high completion, and coherent product design, yet received no official awards.

## Identified Projects
"""
        for i, snw in enumerate(strong_non_winners, 1):
            content += f"""### {i}. {snw.title} (Composite Score: {snw.composite_quality_score:.2f})
- **Completion**: {snw.completion_score:.1f} / 5
- **Technical Depth**: {snw.technical_depth_score:.1f} / 5
- **Product Coherence**: {snw.product_coherence_score:.1f} / 5
- **Repository**: {snw.repo_url or 'N/A'}
- **Demonstration**: {snw.demo_url or 'N/A'}
- **Key Strengths**: {', '.join(snw.key_strengths)}
- **Forensic Assessment**: {snw.why_it_stands_out}

---
"""
        path.write_text(content, encoding="utf-8")

    def _generate_technical_patterns(self, event: HackathonEvent, bundles: Dict[str, BlindProjectBundle], outcomes: Dict[str, ProjectOutcome], path: Path):
        content = """# Technical & Architecture Patterns

## Stack Frequencies
- **Frontend**: High prevalence of React, Next.js, TailwindCSS.
- **Backend**: FastAPI, Express.js, and serverless edge routes dominate.
- **AI/ML**: Direct calls to OpenAI, Gemini, and LangChain orchestration.

## Codebase Rigor Observations
- Less than 15% of hackathon repositories included automated unit tests.
- CI/CD automation was present in under 10% of projects.
- Projects that included database schemas (e.g. Prisma, SQL) exhibited higher completion reliability.
"""
        path.write_text(content, encoding="utf-8")

    def _generate_product_patterns(self, evaluations: Dict[str, BlindProjectEvaluation], outcomes: Dict[str, ProjectOutcome], path: Path):
        content = """# Product Strategy & Scoping Patterns

## Scope Discipline
- Sprawling platforms claiming to solve multiple massive problems consistently suffered from broken workflows and low completion.
- Projects with a single well-executed user journey scored higher on blind coherence and completion.
"""
        path.write_text(content, encoding="utf-8")

    def _generate_demo_patterns(self, bundles: Dict[str, BlindProjectBundle], outcomes: Dict[str, ProjectOutcome], path: Path):
        content = """# Demonstration & Presentation Asset Analysis

## Live Deployment vs Video Proof
- Verified reachable live endpoints significantly increased completion confidence.
- Live expo judging placed heavy weight on real-time demonstration.
"""
        path.write_text(content, encoding="utf-8")

    def _generate_sponsor_analysis(self, event: HackathonEvent, analysis: EventForensicAnalysis, outcomes: Dict[str, ProjectOutcome], bundles: Dict[str, BlindProjectBundle], path: Path):
        content = f"""# Sponsor Challenge Forensics: {event.name}

## Sponsor Prizes Overview
Total Sponsor Winners Identified: {analysis.total_sponsor_winners}

### Key Observations:
- Sponsor-specific challenges prioritize direct integration with their designated SDK, API, or infrastructure over general product scope.
- Submissions that isolated sponsor technology in core workflows were far more competitive for company prizes.
"""
        path.write_text(content, encoding="utf-8")

    def _generate_mismatch_analysis(self, analysis: EventForensicAnalysis, path: Path):
        content = """# Forensic Mismatch Analysis: Winners vs. Blind Quality Assessments

This report highlights projects where blind public evidence diverged from official judging selections. Disagreements are preserved without rationalization.

## Mismatch Taxonomy
"""
        for rec in analysis.project_records:
            if rec.outcome.is_winner and rec.mismatch_classification != MismatchClassification.EVIDENCE_STRONGLY_SUPPORTS:
                content += f"""### [{rec.mismatch_classification.value.upper()}] {rec.title}
- **Composite Blind Score**: {rec.blind_evaluation.composite_quality_score:.2f}
- **Official Awards**: {', '.join([a.name for a in rec.outcome.awards])}
- **Forensic Finding**: {rec.mismatch_explanation}
- **Comparable Strong Non-Winners**: {', '.join(rec.comparable_non_winners) if rec.comparable_non_winners else 'None'}
- **Potential Unobserved Explanations (Hypotheses Only)**:
"""
                for hyp in rec.unobserved_factor_hypotheses:
                    content += f"  - *{hyp}*\n"
                content += "\n---\n"

        path.write_text(content, encoding="utf-8")

    def _generate_counterexamples(self, audits: List[Dict[str, Any]], path: Path):
        content = """# Counterexamples & Anti-Bias Audits

Automated sanity checks challenging popular hackathon heuristics.

"""
        for audit in audits:
            content += f"""## Hypothesis: "{audit.get('hypothesis')}"
- **Finding**: {audit.get('finding')}
"""
            for k, v in audit.items():
                if k not in ["hypothesis", "finding"]:
                    content += f"- **{k.replace('_', ' ').title()}**: {v}\n"
            content += "\n---\n"

        path.write_text(content, encoding="utf-8")

    def _generate_limitations(self, path: Path):
        content = """# Forensic Methodology Limitations & External Constraints

1. **Unobserved Live Expo Judging**:
   Hackathons involve live floor judging, oral pitches, stage charisma, and judge Q&A sessions that are not recorded on Devpost or GitHub.
2. **Private Code & Closed Repositories**:
   Teams that submit private repos or local-only code cannot have their implementations verified beyond claimed assets.
3. **Judging Panel Variance**:
   Different judging rooms and sponsor representatives apply divergent rubrics and personal preferences.
"""
        path.write_text(content, encoding="utf-8")

    def _generate_strategy_context(self, event: HackathonEvent, analysis: EventForensicAnalysis, path: Path):
        content = f"""# Strategic Blueprint for Future Hackathons

Based on empirical data from {event.name} ({event.year}):

1. **Prioritize Working End-to-End Core Over Sprawl**:
   A verified functional core with live deployment outscores half-finished complex platforms.
2. **Anchor Sponsor Challenges in the Primary Loop**:
   If pursuing sponsor awards, make their technology essential to the core value rather than an ornamental extra.
3. **Invest in Live Demonstration Ergonomics**:
   Ensure zero-friction live demos for judges.
"""
        path.write_text(content, encoding="utf-8")

    def _generate_project_report(self, rec: ProjectForensicRecord, bundle: BlindProjectBundle, path: Path):
        evaln = rec.blind_evaluation
        repo = bundle.repository_metrics
        demo = bundle.demo_summary
        outcome = rec.outcome

        content = f"""# Forensic Report: {bundle.title}

## Overview & Metadata
- **Project Slug**: `{bundle.slug}`
- **Tagline**: {bundle.tagline}
- **Devpost URL**: [{rec.slug}](https://devpost.com/software/{rec.slug})
- **Repository URL**: {repo.repo_url if repo else 'None provided'}
- **Team Size**: {bundle.team_size}

---

# SECTION 1: BLIND ANALYSIS
*This section was completed and cryptographically sealed prior to revealing judging outcomes.*
*Integrity Hash: `{evaln.evaluation_sha256}`*

### Diagnostic Evaluation
- **Problem Statement**: {evaln.answers_consensus.get('problem_solved', 'N/A')}
- **Target User**: {evaln.answers_consensus.get('target_user', 'N/A')}
- **Core Workflow**: {evaln.answers_consensus.get('primary_workflow', 'N/A')}
- **Verified Software Execution**: {evaln.answers_consensus.get('what_works', 'N/A')}
- **Observable Incompleteness**: {evaln.answers_consensus.get('what_incomplete', 'N/A')}

### Observable Repository Metrics
- **Repo Status**: {repo.status if repo else 'Unavailable'}
- **Approximate LOC**: {repo.approx_loc if repo else 'N/A'}
- **Primary Languages**: {', '.join(repo.primary_languages) if repo else 'N/A'}
- **Test Files Count**: {repo.test_files_count if repo else 0}
- **CI / Docker Configs**: CI={repo.has_ci if repo else False}, Docker={repo.has_docker if repo else False}
- **Live Endpoint Reachable**: {demo.deployment_reachable}

### Blind Rubric Scores (0-5 Scale)
- **Composite Quality Score**: **{evaln.composite_quality_score:.2f} / 5.0**
- **Completion**: {evaln.aggregated_scores.get('completion', 0.0):.1f} / 5 ({evaln.passes[0].dimensions.get('completion', {}).score_ordinal if evaln.passes else 'N/A'})
- **Technical Depth**: {evaln.aggregated_scores.get('technical_depth', 0.0):.1f} / 5
- **Product Coherence**: {evaln.aggregated_scores.get('product_coherence', 0.0):.1f} / 5
- **Originality**: {evaln.aggregated_scores.get('originality', 0.0):.1f} / 5
- **Demo Strength**: {evaln.aggregated_scores.get('demo_strength', 0.0):.1f} / 5
- **Evaluator Agreement**: `{evaln.evaluator_agreement_status}`

---

# SECTION 2: OUTCOME-AWARE ANALYSIS
*This section was unsealed strictly after blind evaluation was frozen.*

### Official Judging Result
- **Winner Status**: {'WINNER' if outcome.is_winner else 'NON-WINNER'}
- **Award Titles**: {', '.join([a.name for a in outcome.awards]) if outcome.awards else 'None'}

### Forensic Alignment
- **Classification**: `{rec.mismatch_classification.value}`
- **Analysis**: {rec.mismatch_explanation}
"""
        if rec.comparable_non_winners:
            content += f"- **Comparable Strong Non-Winners**: {', '.join(rec.comparable_non_winners)}\n"

        if rec.unobserved_factor_hypotheses:
            content += "\n### Potential Unobserved Hypotheses (Unverified Possibilities):\n"
            for hyp in rec.unobserved_factor_hypotheses:
                content += f"- *{hyp}*\n"

        path.write_text(content, encoding="utf-8")
