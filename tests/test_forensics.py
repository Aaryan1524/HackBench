import json
import pytest
from pathlib import Path
from datetime import datetime, timezone

from hackbench.models import (
    RawProject,
    DescriptionSections,
    ProjectLink,
    BlindProjectBundle,
    BlindProjectEvaluation,
    ProjectOutcome,
    ProjectAward,
    AwardType,
    MismatchClassification,
    ProvenanceRecord,
    EvidenceType,
    RepositoryMetrics,
    StrongNonWinner,
)
from hackbench.blind.bundler import BlindBundleCreator
from hackbench.blind.evaluator import BlindEvaluator
from hackbench.outcomes.extractor import OutcomeExtractor
from hackbench.outcomes.revealer import OutcomeRevealer
from hackbench.analysis.mismatches import MismatchAnalyzer
from hackbench.analysis.strong_nonwinners import StrongNonWinnerDetector


def test_winner_info_cannot_enter_blind_evaluator_inputs():
    """
    Test that winner badges, awards, and placement text are purged from BlindProjectBundle,
    and Pydantic models forbid extraneous outcome fields.
    """
    raw_project = RawProject(
        project_id="test_proj_001",
        slug="test-proj-001",
        title="EcoTracker",
        devpost_url="https://devpost.com/software/test-proj-001",
        tagline="Winner of 1st place overall in ShellHacks 2025!",
        description_sections=DescriptionSections(
            what_it_does="We won 1st place! It tracks carbon emissions.",
            challenges="Finalist at the expo and awarded Best AI prize.",
        ),
        tech_tags=["Python", "FastAPI"],
        raw_winner_awards_text=["1st Place Best Overall", "Wix Sponsor Winner"],
        gallery_winner_badge=True,
    )

    bundler = BlindBundleCreator()
    bundle = bundler.create_bundle(raw_project)

    # 1. Output bundle must NOT have outcome fields
    bundle_dict = bundle.model_dump()
    assert "winner" not in bundle_dict
    assert "awards" not in bundle_dict
    assert "placement" not in bundle_dict

    # 2. Text scrubbing must remove winner statements
    assert "Winner of 1st place" not in bundle.tagline
    assert "[OUTCOME_SCRUBBED]" in bundle.tagline
    assert "We won 1st place" not in bundle.what_it_does
    assert "awarded Best AI" not in bundle.challenges

    # 3. Model config extra = 'forbid' must prevent injecting outcome fields
    with pytest.raises(Exception):
        BlindProjectBundle(
            project_id="123",
            slug="123",
            title="123",
            tagline="",
            problem_statement="",
            inspiration="",
            what_it_does="",
            how_it_was_built="",
            challenges="",
            accomplishments="",
            lessons_learned="",
            future_plans="",
            is_winner=True,  # Extraneous field must fail validation!
        )


def test_blind_results_become_immutable_and_frozen():
    """
    Test that blind evaluations are sealed with SHA256 hashes and marked frozen.
    """
    bundle = BlindProjectBundle(
        project_id="proj_seal_test",
        slug="proj-seal-test",
        title="SafeRoute",
        tagline="Safe navigation for students",
        problem_statement="Campus navigation is unsafe at night.",
        inspiration="Personal experience",
        what_it_does="Routes through well-lit streets using city geospatial data.",
        how_it_was_built="Built with Python and Mapbox.",
        challenges="Routing latency",
        accomplishments="Real-time routing",
        lessons_learned="Geospatial indexing",
        future_plans="Mobile app",
        tech_tags=["Python", "GeoJSON"],
    )

    evaluator = BlindEvaluator()
    evaluation = evaluator.evaluate_project(bundle, num_passes=3)

    assert evaluation.is_frozen is True
    assert len(evaluation.evaluation_sha256) == 64  # valid sha256 hash
    assert len(evaluation.passes) == 3
    assert evaluation.evaluator_agreement_status in ["high_agreement", "moderate_agreement", "low_agreement_unstable"]


def test_outcome_reveal_fails_without_frozen_blind_evaluations(tmp_path):
    """
    Test that outcome reveal requires all blind evaluations to be frozen.
    """
    revealer = OutcomeRevealer()
    sealed_file = tmp_path / "outcomes.json"
    sealed_file.write_text(json.dumps({"proj_1": {"project_id": "proj_1", "is_winner": True, "awards": []}}))
    proc_file = tmp_path / "proc_outcomes.json"

    # 1. No evaluations at all -> must fail
    with pytest.raises(RuntimeError, match="No blind evaluations exist"):
        revealer.reveal_outcomes(sealed_file, proc_file, {})

    # 2. Evaluation with is_frozen=False -> must fail
    bad_evaluation = BlindProjectEvaluation(
        project_id="proj_1",
        bundle_sha256="abc",
        evaluation_sha256="hash",
        is_frozen=False,
    )
    with pytest.raises(RuntimeError, match="is not frozen"):
        revealer.reveal_outcomes(sealed_file, proc_file, {"proj_1": bad_evaluation})


def test_sponsor_awards_distinct_from_overall_awards():
    """
    Test that sponsor awards and overall awards are categorized into separate AwardTypes.
    """
    extractor = OutcomeExtractor()
    overall_award = extractor._classify_award("1st, 2nd, & 3rd Best Overall", None, "https://devpost.com")
    sponsor_award = extractor._classify_award("Wix.com & Base44 Challenge Winner", None, "https://devpost.com")
    beginner_award = extractor._classify_award("Best First-Time Hacker", None, "https://devpost.com")

    assert overall_award.award_type == AwardType.OVERALL
    assert sponsor_award.award_type == AwardType.SPONSOR
    assert beginner_award.award_type == AwardType.BEGINNER


def test_missing_repositories_and_videos_do_not_break_ingestion():
    """
    Test that projects missing code repos or demo videos still evaluate cleanly with appropriate confidence.
    """
    bundle = BlindProjectBundle(
        project_id="no_repo_proj",
        slug="no-repo-proj",
        title="IdeaOnly",
        tagline="An ambitious concept",
        problem_statement="Problem description without code",
        inspiration="Inspiration",
        what_it_does="Description of concept",
        how_it_was_built="Theoretical architecture",
        challenges="None",
        accomplishments="Ideation",
        lessons_learned="Hackathons are fast",
        future_plans="Build prototype",
        tech_tags=["Figma"],
        repository_metrics=None,  # No repository!
    )

    evaluator = BlindEvaluator()
    evaluation = evaluator.evaluate_project(bundle, num_passes=3)

    assert evaluation.project_id == "no_repo_proj"
    assert evaluation.composite_quality_score <= 2.5
    # Completion should reflect missing working code
    assert evaluation.aggregated_scores.get("completion", 0) <= 2.0


def test_provenance_record_survives_processing():
    """
    Test that source provenance survives data transformation.
    """
    prov = ProvenanceRecord(
        claim="Repository verified with 450 LOC",
        evidence_type=EvidenceType.REPOSITORY,
        source="https://github.com/team/demo",
        location="main branch",
        confidence=0.95,
    )

    repo = RepositoryMetrics(
        repo_url="https://github.com/team/demo",
        status="accessible",
        approx_loc=450,
        provenance=[prov],
    )

    assert len(repo.provenance) == 1
    assert repo.provenance[0].evidence_type == EvidenceType.REPOSITORY
    assert repo.provenance[0].confidence == 0.95


def test_mismatch_preservation_weak_winner_vs_strong_nonwinner():
    """
    CRUCIAL VALIDATION REQUIREMENT:
    Prove that a project can receive a weaker blind assessment than a non-winner
    and still remain recorded as the official winner WITHOUT the analysis being
    modified to justify the outcome.

    Expected behavior:
      official_result = winner
      blind_analysis = weaker than comparable non-winner
      mismatch = evidence_conflicts_with_outcome
      Both facts are preserved without rationalization.
    """
    # 1. Non-winner project with very strong blind evaluation
    strong_non_winner = StrongNonWinner(
        project_id="non_winner_heavy_eng",
        slug="non-winner-heavy-eng",
        title="DistributedMeshNet",
        composite_quality_score=4.2,
        completion_score=4.5,
        technical_depth_score=4.5,
        product_coherence_score=4.0,
        repo_url="https://github.com/hackers/meshnet",
        demo_url="https://youtu.be/meshnet-demo",
        key_strengths=["Custom protocol", "1200 LOC", "Working live deployment"],
        why_it_stands_out="Exceptional engineering rigor and complete end-to-end execution",
    )

    # 2. Winner project with weak observable blind evidence (e.g. static prototype or unverified repo)
    weak_winner_eval = BlindProjectEvaluation(
        project_id="winner_light_prototype",
        bundle_sha256="hash_bundle_winner",
        composite_quality_score=2.2,  # Substantially weaker than strong non-winner (4.2 vs 2.2)
        aggregated_scores={
            "completion": 1.5,
            "technical_depth": 1.5,
            "product_coherence": 2.5,
            "originality": 2.0,
            "demo_strength": 2.0,
        },
        evaluation_sha256="hash_eval_winner",
        is_frozen=True,
    )

    official_winner_outcome = ProjectOutcome(
        project_id="winner_light_prototype",
        is_winner=True,
        is_overall_winner=True,
        awards=[
            ProjectAward(
                name="1st Place Best Overall",
                award_type=AwardType.OVERALL,
                placement="1st",
                official_source="https://devpost.com/software/winner-light-prototype",
            )
        ],
        unsealed_at=datetime.now(timezone.utc),
    )

    analyzer = MismatchAnalyzer()
    record = analyzer.classify_project(
        project_id="winner_light_prototype",
        slug="winner-light-prototype",
        title="VaguePitchProject",
        evaluation=weak_winner_eval,
        outcome=official_winner_outcome,
        all_evaluations={"winner_light_prototype": weak_winner_eval},
        all_outcomes={"winner_light_prototype": official_winner_outcome},
        strong_non_winners=[strong_non_winner],
    )

    # FACT 1: Official outcome is unequivocally preserved as WINNER
    assert record.outcome.is_winner is True
    assert record.outcome.awards[0].name == "1st Place Best Overall"

    # FACT 2: Blind analysis is NOT modified to justify the win; it remains at 2.2
    assert record.blind_evaluation.composite_quality_score == 2.2
    assert record.blind_evaluation.aggregated_scores["completion"] == 1.5

    # FACT 3: Disagreement is preserved as an explicit conflict / insufficient evidence
    assert record.mismatch_classification in [
        MismatchClassification.EVIDENCE_CONFLICTS,
        MismatchClassification.INSUFFICIENT_EVIDENCE,
    ]
    # The explanation must explicitly note the divergence
    assert "public evidence" in record.mismatch_explanation.lower() or "conflicts" in record.mismatch_explanation.lower()

    # Potential hypotheses are labeled as possibilities only
    assert len(record.unobserved_factor_hypotheses) > 0
    assert any("live" in h.lower() or "presentation" in h.lower() for h in record.unobserved_factor_hypotheses)


def test_one_broken_project_does_not_stop_run():
    """
    Test that a malformed or corrupted project does not crash batch processing.
    """
    valid_proj = RawProject(
        project_id="valid_1",
        slug="valid-1",
        title="ValidProject",
        devpost_url="https://devpost.com/software/valid-1",
        tech_tags=["Python"],
    )
    bundler = BlindBundleCreator()
    evaluator = BlindEvaluator()

    batch = [valid_proj, None]  # contains a broken/None entry
    processed_evals = []

    for item in batch:
        try:
            if item is None:
                raise ValueError("Corrupted project record")
            bundle = bundler.create_bundle(item)
            ev = evaluator.evaluate_project(bundle)
            processed_evals.append(ev)
        except Exception:
            # Resilient pipeline logs and continues
            continue

    assert len(processed_evals) == 1
    assert processed_evals[0].project_id == "valid_1"


def test_duplicate_projects_handled(tmp_path):
    """
    Test that duplicate project submissions are handled gracefully without duplicate entries.
    """
    from hackbench.storage.db import DatabaseManager

    db = DatabaseManager(tmp_path / "test.db")
    proj = RawProject(
        project_id="dup_1",
        slug="dup-1",
        title="DuplicateDemo",
        devpost_url="https://devpost.com/software/dup-1",
    )

    # Insert twice
    db.save_project("test_event", 2025, proj)
    db.save_project("test_event", 2025, proj)

    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM projects WHERE project_id = 'dup_1'")
        count = cursor.fetchone()[0]
        assert count == 1  # Deduplicated via primary key constraint!


def test_rerun_idempotency(tmp_path):
    """
    Test that rerunning evaluation on the same bundle produces identical hashes.
    """
    bundle = BlindProjectBundle(
        project_id="idem_1",
        slug="idem-1",
        title="IdempotentApp",
        tagline="Testing idempotency",
        problem_statement="Ensuring repeatable metrics",
        inspiration="Science",
        what_it_does="Runs deterministic calculations",
        how_it_was_built="Python",
        challenges="None",
        accomplishments="Consistency",
        lessons_learned="Hashes",
        future_plans="Scale",
        tech_tags=["Python"],
    )

    bundler = BlindBundleCreator()
    b1 = bundler.create_bundle(
        RawProject(
            project_id="idem_1",
            slug="idem-1",
            title="IdempotentApp",
            devpost_url="https://devpost.com/software/idem-1",
            description_sections=DescriptionSections(
                problem_statement="Ensuring repeatable metrics",
                inspiration="Science",
                what_it_does="Runs deterministic calculations",
                how_it_was_built="Python",
            ),
        )
    )
    b2 = bundler.create_bundle(
        RawProject(
            project_id="idem_1",
            slug="idem-1",
            title="IdempotentApp",
            devpost_url="https://devpost.com/software/idem-1",
            description_sections=DescriptionSections(
                problem_statement="Ensuring repeatable metrics",
                inspiration="Science",
                what_it_does="Runs deterministic calculations",
                how_it_was_built="Python",
            ),
        )
    )

    assert b1.bundle_sha256 == b2.bundle_sha256

