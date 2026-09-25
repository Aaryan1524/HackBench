from typing import Dict, List, Tuple
from ..models import DimensionScore

# Rubric anchors for all 17 dimensions (0 to 5)
RUBRIC_ANCHORS: Dict[str, Dict[int, str]] = {
    "problem_clarity": {
        0: "Incoherent problem statement; purely a list of buzzwords; problem is unstated.",
        1: "Extremely vague problem; hard to identify specific pain point being targeted.",
        2: "Understandable problem area, but poorly scoped or presented generically.",
        3: "Clear, identifiable problem statement described in concrete, everyday terms.",
        4: "Crisp, compelling problem statement with tangible context and immediate lucidity.",
        5: "Masterful articulation; defines the exact bottleneck, root cause, or failure mode in under 30 seconds.",
    },
    "user_specificity": {
        0: "No target user identified ('for everyone in the world').",
        1: "Overly broad category with conflicting user needs.",
        2: "Broad persona identified (e.g. 'college students') without role nuance.",
        3: "Specific target role identified with identifiable workflow constraints.",
        4: "Distinct user segment with detailed day-in-the-life empathy and tailored workflow touchpoints.",
        5: "Hyper-targeted persona with documented user friction, niche domain requirements, and tailored UX constraints.",
    },
    "problem_importance": {
        0: "Trivial or artificial problem manufactured solely to showcase an API.",
        1: "Minor convenience issue with minimal real-world friction.",
        2: "Noticeable everyday annoyance or recreational optimization.",
        3: "Meaningful operational, financial, educational, or logistical problem with measurable friction.",
        4: "High-stakes or severe bottleneck affecting critical workflows, safety, cost, or accessibility.",
        5: "Critical, transformative challenge with substantial systemic impact or acute human necessity.",
    },
    "originality": {
        0: "Carbon copy of standard tutorial or hackathon cliché with zero novel twist.",
        1: "Generic application with superficial thematic dressing (e.g. standard ChatGPT wrapper for study notes).",
        2: "Familiar concept with one or two thoughtful, unconventional features or mechanics.",
        3: "Distinct angle or novel synthesis of two disparate domains; fresh take on an existing category.",
        4: "Highly creative, unexpected framing; tackles a problem rarely explored in hackathons.",
        5: "Radical paradigm shift; groundbreaking product insight that challenges conventional assumptions.",
    },
    "product_coherence": {
        0: "Fragmented assortment of disconnected demos on separate pages with no linking narrative.",
        1: "Loose collection of features sharing a nav bar but lacking a coherent end-to-end data flow.",
        2: "Clear primary feature, but multiple secondary features feel tacked on or unintegrated.",
        3: "Logical end-to-end flow where step A cleanly feeds into step B and step C.",
        4: "Tight, polished workflow where every single feature directly reinforces the core value proposition.",
        5: "Seamless, frictionless product harmony; every interaction feels deliberate, necessary, and unified.",
    },
    "scope_discipline": {
        0: "Grossly over-scoped fantasy platform with dozens of empty stubs, 404 links, and unfinished screens.",
        1: "Overambitious scope resulting in widespread shallow, half-broken implementations.",
        2: "Ambitious scope with several compromised or non-functioning edges.",
        3: "Well-bounded scope; focused on a tight core with clean execution and few broken paths.",
        4: "Disciplined scope management; intentionally cut non-essential features to achieve high polish.",
        5: "Flawless surgical scoping; delivered a complete, high-fidelity experience without loose ends.",
    },
    "completion": {
        0: "No working workflow visible; repository is empty, broken, or contains only non-functional templates.",
        1: "Isolated fragments or static UI mockups only; core data pipeline does not function.",
        2: "Partial workflow functions, but missing a critical intermediate or final step (e.g. outputs are hardcoded).",
        3: "Primary end-to-end workflow functions from input to output, though edge cases fail or secondary features are stubbed.",
        4: "Robust, fully functional primary workflow verifiable in code and demo without mock dependencies.",
        5: "Complete primary workflow plus error handling, edge-case coverage, and functional supporting features.",
    },
    "technical_depth": {
        0: "Static HTML/CSS or unedited boilerplate generated directly from starter templates.",
        1: "Simple CRUD or single API pass-through with minimal custom logic.",
        2: "Standard multi-tier web application (database schema, authenticated API routes, client state management).",
        3: "Custom algorithms, multi-stage data processing pipeline, non-trivial state synchronization, or hardware-software bridging.",
        4: "Complex distributed architecture, custom computer vision/ML pipeline, real-time protocol handling, or intricate low-level systems logic.",
        5: "Remarkable engineering feat for a hackathon; custom model fine-tuning/architecture, kernel-level/hardware integration, or algorithmic novelty.",
    },
    "technical_appropriateness": {
        0: "Absurd mismatch (e.g. using a blockchain to store local form state).",
        1: "Over-engineered or ill-suited tools that impede performance and add needless complexity.",
        2: "Workable stack, but suboptimal or exhibits obvious signs of resume-driven development.",
        3: "Pragmatic, well-suited stack that solves the core problem effectively.",
        4: "High synergy between problem constraints and tool choices; efficient, scalable, and lean.",
        5: "Masterful architectural choices that solve difficult constraints with elegant simplicity.",
    },
    "integration_depth": {
        0: "Mentioned in README or tags but zero code references found in repository.",
        1: "Single trivial call (e.g. default curl request or standard client import with 2 lines of code).",
        2: "Standard API interaction with basic response parsing.",
        3: "Multi-endpoint utilization with bidirectional data exchange, state handling, and error trapping.",
        4: "Complex orchestration, webhooks/event streaming, custom parameter optimization, or multi-service pipelines.",
        5: "Full-stack symbiosis; custom extensions, real-time bi-directional pipeline, or hybrid edge-cloud coordination.",
    },
    "ai_necessity": {
        0: "Pure gimmick where deterministic logic or a regex would be faster, cheaper, and more reliable; or AI is absent.",
        1: "Superficial LLM wrapper adding little value beyond basic text paraphrasing.",
        2: "AI provides nice-to-have enhancements (e.g. automated tagging) but core value exists without it.",
        3: "AI is an integral component; the product solves the problem significantly better with ML than without.",
        4: "Core value proposition is impossible without machine intelligence; models handle complex unstructured reasoning.",
        5: "Sophisticated compound AI system (multi-agent, hybrid RAG, multimodal reasoning) that defines the entire breakthrough.",
    },
    "demo_strength": {
        0: "No demo available, or video is private/unplayable.",
        1: "Unclear voiceover, slide-only presentation with no live software, or unreadable screen recording.",
        2: "Standard feature walkthrough; slow pacing; fails to highlight what makes the project distinctive.",
        3: "Crisp explanation of problem and live software demonstration within the first 60 seconds.",
        4: "Compelling; high energy, well-structured user journey, clearly proves live working software, memorable pacing.",
        5: "Electrifying; unforgettable narrative arc, flawless live demonstration of technical difficulty, immediate emotional resonance.",
    },
    "design_ux": {
        0: "Unusable UI; broken layouts, overlapping text, unreadable contrast.",
        1: "Bare unstyled HTML or basic bootstrap default with awkward ergonomics.",
        2: "Clean but generic template; adequate usability without aesthetic refinement.",
        3: "Thoughtful layout, clear visual hierarchy, intuitive ergonomics, cohesive styling.",
        4: "High craft; smooth transitions, responsive micro-interactions, accessible typography, tailored domain aesthetics.",
        5: "Studio Quality; world-class design execution rivaling venture-backed products; extraordinary attention to detail.",
    },
    "practicality": {
        0: "Concept is fundamentally unworkable, violates physics, or creates unacceptable legal/safety hazards.",
        1: "Enormous barriers to adoption, prohibitive operational costs, or negligible incentives for users.",
        2: "Core idea has merit, but requires complete rewriting and different economics to function.",
        3: "Viable utility that could realistically serve beta testers with moderate engineering hardening.",
        4: "High viability; clear path to ongoing utility, realistic economic model, immediate practical appeal.",
        5: "Production-ready concept; addresses an urgent real-world need with defensible viability.",
    },
    "memorability": {
        0: "Indistinguishable from the background noise of standard projects.",
        1: "Standard functionality with no standout moments.",
        2: "One interesting graphic, clever quip, or neat minor feature.",
        3: "Strong, distinct visual or technical hook that lingers in the mind.",
        4: "Striking; unusually clever mechanic or visceral live demo moment that commands attention.",
        5: "Legendary; a jaw-dropping hackathon moment that everyone at the venue talks about.",
    },
    "story_clarity": {
        0: "Scattered thoughts; cannot tell why the project was built or how components connect.",
        1: "Muddled; skips critical context, jumps into technical weeds before establishing why it matters.",
        2: "Adequate; basic sequential structure, but lacks dramatic tension or compelling conclusion.",
        3: "Well-structured; clear, logical narrative arc that guides the reviewer smoothly from pain point to outcome.",
        4: "Persuasive; highly compelling narrative; anticipates reviewer questions and answers them proactively with data.",
        5: "Masterclass; flawless storytelling; builds undeniable urgency and proves technical victory with effortless lucidity.",
    },
    "sponsor_alignment": {
        0: "Sponsor tool mentioned in tags but nowhere in code, or prompt completely disregarded.",
        1: "Nominal; superficial token usage (e.g. calling sponsor API once to fetch dummy data).",
        2: "Moderate; uses sponsor technology legitimately, but in a routine, generic manner.",
        3: "Strong; core workflow directly leverages key sponsor capabilities to solve the designated challenge.",
        4: "Exceptional; pushes sponsor technology to its limits, integrating advanced SDK features and addressing sponsor goals directly.",
        5: "Exemplary; flagship showcase; solves the sponsor's exact challenge with unprecedented ingenuity and depth.",
    },
}

SCORE_TO_ORDINAL = {
    0: "very_weak",
    1: "weak",
    2: "moderate",
    3: "strong",
    4: "very_strong",
    5: "very_strong",
}


def score_dimension(dimension: str, score: int, justification: str, confidence: float = 1.0) -> DimensionScore:
    clamped = max(0, min(5, int(score)))
    anchor = RUBRIC_ANCHORS.get(dimension, {}).get(clamped, "Unanchored score")
    ordinal = SCORE_TO_ORDINAL.get(clamped, "moderate")
    return DimensionScore(
        dimension=dimension,
        score_numeric=clamped,
        score_ordinal=ordinal,
        rubric_anchor=anchor,
        justification=justification,
        confidence=confidence,
    )


def compute_evaluator_agreement(
    passes: List[Dict[str, int]]
) -> Tuple[Dict[str, float], Dict[str, float], List[str], str]:
    """
    Computes dimension means, variances, and identifies disputed dimensions.
    Returns: (means, variances, disputed_dimensions, agreement_status)
    """
    if not passes:
        return {}, {}, [], "low_agreement_unstable"

    dimensions = list(passes[0].keys())
    means: Dict[str, float] = {}
    variances: Dict[str, float] = {}
    disputed: List[str] = []

    for dim in dimensions:
        vals = [p[dim] for p in passes if dim in p]
        if not vals:
            continue
        mean_v = sum(vals) / len(vals)
        var_v = sum((x - mean_v) ** 2 for x in vals) / len(vals)
        spread = max(vals) - min(vals)

        means[dim] = round(mean_v, 2)
        variances[dim] = round(var_v, 2)

        # Spread of >= 2.0 on core dimensions constitutes dispute
        if spread >= 2.0:
            disputed.append(dim)

    # Agreement status classification
    if len(disputed) >= 3:
        status = "low_agreement_unstable"
    elif len(disputed) >= 1:
        status = "moderate_agreement"
    else:
        status = "high_agreement"

    return means, variances, disputed, status
