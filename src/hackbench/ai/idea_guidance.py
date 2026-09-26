"""
Pre-hackathon build guidance for Idea Mode.

Turns an extracted idea plus documented prize fits into short, actionable guidance:
strongest part, biggest conceptual gap, what to build first, what to skip for now.

Everything here is derived from the idea text, the documented prize criteria, and the
historical report. Nothing is keyed to a specific product domain, and nothing is
invented: when there is no evidence for a recommendation, the field is left empty.
"""
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .idea_extractor import ExtractedIdea
from .prize_matcher import FitLevel, PrizeFit, SponsorTechRole

MAX_STEPS = 5
MAX_DONT_BUILD = 3
MAX_TEXT_CHARS = 170

# Things a hacker should never be told to start with (unless the idea's core loop is that thing).
FORBIDDEN_FIRST_STEPS = re.compile(
    r"\b(auth(entication|orization)?|log[- ]?in|sign[- ]?up|settings?|multi[- ]?tenant|"
    r"analytics|dashboards?|billing|admin panels?|infrastructure)\b",
    re.IGNORECASE,
)

_ACTION_PLACEHOLDER_WORDS = re.compile(
    r"\b(consider|potentially|prioriti[sz]ing|implementation of|leverage|optimi[sz]e (the )?(score|alignment))\b",
    re.IGNORECASE,
)

_USER_LIKE_WORDS = {
    "managers", "students", "developers", "hackers", "patients", "doctors",
    "guests", "consumers", "travelers", "shoppers", "educators", "teachers",
    "engineers", "designers", "researchers", "users", "customers", "people", "nurses",
}

# (label, pattern). A match only counts when the term is NOT part of the idea's own core loop.
DONT_BUILD_RULES = [
    ("Multi-tenant or multi-site support",
     r"multi[- ]?(?:tenant|property|location|site|campus)|enterprise|across (?:all |many |multiple )?(?:\w+ )?(?:locations|campuses|cities|properties|stores)|\bchains?\b"),
    ("Login, accounts, and roles",
     r"user accounts?|accounts? (?:creation|management)|log[- ]?in|sign[- ]?(?:in|up)|authenticat\w+|role[- ]based|permissions?|\bsso\b|oauth"),
    ("Secondary integrations",
     r"integrat\w+|\bsync\w*|plug[- ]?ins?|\bcrm\b|salesforce|slack|zapier|calendar|webhooks?|third[- ]party"),
    ("Analytics dashboards and reports",
     r"dashboards?|analytics|trend(?:s| analysis)?|reports?|historical data|metrics"),
    ("Extensive settings and customization",
     r"settings|preferences|customi[sz]\w+|personali[sz]\w+|configurable|themes?"),
    ("Billing and subscriptions",
     r"billing|subscriptions?|monetiz\w+|pricing tiers?|paywall"),
    ("Scaling and infrastructure hardening",
     r"millions of|scal(?:e|able|ability)\b|high availability|load balanc\w+|kubernetes|microservices?"),
]

_RISKY_TECH_CONSTRAINTS = ("real-time", "realtime", "real time", "offline", "low latency")


class GuidanceItem(BaseModel):
    title: str
    detail: str
    headline: str  # short phrase used to build the editorial headline
    action: Optional[str] = None  # what to do about it (gaps only)
    kind: str = ""


class IdeaGuidance(BaseModel):
    strongest: GuidanceItem
    biggest_gap: GuidanceItem
    build_first_steps: List[str]
    build_first: str
    dont_build_yet: List[str] = Field(default_factory=list)
    before_hackathon: List[Dict[str, str]] = Field(default_factory=list)  # {action, reason}
    headline: str
    summary: str
    historical_takeaway: Optional[str] = None


def _short(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:-")
    return cut + "…"


def _imperative(clause: str) -> str:
    """'calls users daily' -> 'Call users daily'. Only touches a leading 3rd-person verb."""
    clause = clause.strip(" ,.;")
    if not clause:
        return clause
    words = clause.split()
    first = words[0]
    low = first.lower()
    irregular = {"goes": "go", "does": "do", "has": "have"}
    if low in irregular:
        words[0] = irregular[low]
    elif low.endswith("s") and low not in _USER_LIKE_WORDS and not low.endswith(("ss", "us", "is")) and len(low) > 3:
        if low.endswith("ies"):
            low = low[:-3] + "y"
        elif low.endswith(("ches", "shes", "sses", "xes", "zes")):
            low = low[:-2]
        else:
            low = low[:-1]
        words[0] = low
    return " ".join(words)[:1].upper() + " ".join(words)[1:]


def parse_workflow_steps(core_workflow: Optional[str]) -> List[str]:
    if not core_workflow:
        return []
    text = re.sub(r"\s*(?:-{1,2}>|=>)\s*", " → ", core_workflow)
    parts = re.split(r"\s*→\s*|\s*;\s*|\s*,\s*(?:and\s+|then\s+)?|\s+and then\s+|\s+then\s+|\s+and\s+", text)
    merged: List[str] = []
    for part in (p.strip() for p in parts if p and p.strip()):
        # a short fragment ("staff") is the tail of a noun list, not a step of its own
        if merged and len(part.split()) < 3 and "→" not in text:
            merged[-1] = f"{merged[-1]} and {part}"
        else:
            merged.append(part)
    return [_imperative(p) for p in merged if len(p.split()) >= 2]


def _first_top_fit(fits: List[PrizeFit], sponsor_only: bool = False) -> Optional[PrizeFit]:
    for f in fits:
        if f.insufficient_criteria:
            continue
        if sponsor_only and f.prize_type not in ("sponsor", "track"):
            continue
        return f
    return None


def _idea_text(idea: ExtractedIdea, description: str) -> str:
    return " ".join(filter(None, [description, idea.problem, idea.core_workflow, idea.user_outcome]))


def _core_loop_text(idea: ExtractedIdea) -> str:
    return " ".join(filter(None, [idea.core_workflow, idea.user_outcome, idea.proposed_product])).lower()


def build_first_steps(idea: ExtractedIdea, fits: List[PrizeFit]) -> List[str]:
    """Smallest end-to-end path: trigger -> processing -> result. Uses only the idea's own words."""
    steps = parse_workflow_steps(idea.core_workflow)
    user = (idea.target_user or "the user").strip()

    if len(steps) < 2:
        # Workflow not described: give the shape of the loop, without inventing its content.
        return [
            f"One real input from {user}",
            "The product does its one core job on that input",
            "One concrete result is shown on screen",
        ]

    if len(steps) == 2:
        steps.append(f"Show the result to {user} on screen")
    if len(steps) > MAX_STEPS:
        steps = steps[: MAX_STEPS - 1] + [steps[-1]]

    top = _first_top_fit(fits, sponsor_only=True)
    if (
        top
        and top.sponsor_name
        and top.sponsor_tech_role == SponsorTechRole.CENTRAL
        and top.fit_level in (FitLevel.STRONG, FitLevel.VERY_STRONG)
        and top.sponsor_name.lower() in [s.lower() for s in idea.likely_sponsor_technologies]
        and top.sponsor_name.lower() not in " ".join(steps).lower()
    ):
        steps[1] = f"{steps[1]} (using {top.sponsor_name})"
    return steps


def find_dont_build(idea: ExtractedIdea, description: str, fits: List[PrizeFit]) -> List[str]:
    """Only items the idea text actually points at, and never ones a prize requires or the core loop is about."""
    text = _idea_text(idea, description)
    core = _core_loop_text(idea)
    required = " ".join(
        " ".join(f.documented_requirements + f.what_must_be_demonstrated) for f in fits if not f.insufficient_criteria
    ).lower()

    items: List[str] = []
    for label, pattern in DONT_BUILD_RULES:
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            continue
        if re.search(pattern, core, re.IGNORECASE) or re.search(pattern, required, re.IGNORECASE):
            continue
        items.append(f"{label} — you mention “{m.group(0).strip()}”; the core demo doesn't need it yet.")
        if len(items) == MAX_DONT_BUILD:
            break
    return items


def _technical_signals(idea: ExtractedIdea, description: str) -> Dict[str, Any]:
    tech = [t for t in idea.intended_technologies if t]
    constraint = next((c for c in _RISKY_TECH_CONSTRAINTS if c in _idea_text(idea, description).lower()), None)
    if idea.notable_constraints and any(c in idea.notable_constraints.lower() for c in _RISKY_TECH_CONSTRAINTS):
        constraint = idea.notable_constraints
    return {"tech": tech, "constraint": constraint}


def pick_strongest(idea: ExtractedIdea, description: str, fits: List[PrizeFit], steps_defined: bool) -> GuidanceItem:
    sponsor_fit = _first_top_fit(fits, sponsor_only=True)
    sig = _technical_signals(idea, description)

    if (
        steps_defined
        and sponsor_fit
        and sponsor_fit.fit_level in (FitLevel.STRONG, FitLevel.VERY_STRONG)
        and sponsor_fit.sponsor_tech_role == SponsorTechRole.CENTRAL
    ):
        return GuidanceItem(
            title=f"Built around what {sponsor_fit.award_title} asks for",
            detail=_short(sponsor_fit.why_it_fits),
            headline="The concept fits a documented challenge closely.",
            kind="sponsor_fit",
        )
    if len(sig["tech"]) >= 2 and sig["constraint"]:
        return GuidanceItem(
            title="A technically ambitious core",
            detail=_short(f"Combines {', '.join(sig['tech'][:3])} under a hard “{sig['constraint']}” requirement."),
            headline="An ambitious technical core.",
            kind="technical",
        )
    if steps_defined and idea.user_outcome:
        return GuidanceItem(
            title="A complete loop from input to result",
            detail=_short(f"You already describe the path: {idea.core_workflow}."),
            headline="A clear end-to-end loop.",
            kind="loop",
        )
    if idea.target_user and idea.problem:
        return GuidanceItem(
            title="A specific user with a stated problem",
            detail=_short(f"Built for {idea.target_user}. {idea.problem}"),
            headline="A specific user and problem.",
            kind="user_problem",
        )
    if idea.target_user:
        return GuidanceItem(
            title="A specific user",
            detail=_short(f"Built for {idea.target_user}."),
            headline="A specific user.",
            kind="user",
        )
    if steps_defined:
        return GuidanceItem(
            title="A described workflow",
            detail=_short(f"You describe the path: {idea.core_workflow}."),
            headline="A described workflow.",
            kind="workflow",
        )
    return GuidanceItem(
        title="A recognizable product direction",
        detail=_short(f"The idea points at: {idea.proposed_product or 'a product'}."),
        headline="A recognizable direction.",
        kind="product",
    )


def pick_biggest_gap(
    idea: ExtractedIdea,
    description: str,
    fits: List[PrizeFit],
    steps_defined: bool,
    dont_build_count: int,
) -> GuidanceItem:
    sponsor_fit = _first_top_fit(fits, sponsor_only=True)
    sig = _technical_signals(idea, description)

    if not steps_defined:
        return GuidanceItem(
            title="The step-by-step workflow is undefined",
            detail="The description says what the product is, but not what happens from first input to final result.",
            headline="The workflow needs defining.",
            action="Write the one path a user takes, from first input to final result, before you write code.",
            kind="workflow_undefined",
        )
    if not idea.target_user:
        return GuidanceItem(
            title="No specific user",
            detail="The idea does not say who uses it, so it is hard to judge what a good result looks like.",
            headline="The user needs naming.",
            action="Name one specific user and say what they do today without this.",
            kind="user_undefined",
        )
    if not idea.problem and not idea.user_outcome:
        return GuidanceItem(
            title="No stated problem or outcome",
            detail="The workflow is described, but not why it matters or what the user ends up with.",
            headline="The problem needs stating.",
            action="State the problem in one sentence and the result the user walks away with.",
            kind="problem_undefined",
        )
    if (
        sponsor_fit
        and sponsor_fit.sponsor_name
        and sponsor_fit.sponsor_name.lower() in [t.lower() for t in idea.likely_sponsor_technologies]
        and sponsor_fit.sponsor_tech_role in (SponsorTechRole.DECORATIVE, SponsorTechRole.ABSENT)
    ):
        tech = sponsor_fit.sponsor_name
        return GuidanceItem(
            title=f"{tech} is not in the core loop",
            detail=_short(sponsor_fit.why_it_may_not_fit),
            headline="The sponsor technology is on the sidelines.",
            action=f"Put {tech} in the main workflow, or stop targeting that sponsor.",
            kind="sponsor_decorative",
        )
    if sig["constraint"] and len(sig["tech"]) >= 2:
        return GuidanceItem(
            title="The hardest claim is unproven",
            detail=_short(f"“{sig['constraint']}” is the part most likely to break, and the rest depends on it."),
            headline="The hardest technical claim is unproven.",
            action=f"Prove the {sig['constraint']} path first, with fake data everywhere else.",
            kind="technical_risk",
        )
    if len(parse_workflow_steps(idea.core_workflow)) > MAX_STEPS or dont_build_count >= 3:
        return GuidanceItem(
            title="Scope is wider than one loop",
            detail="The description covers more than one workflow, which is a lot to finish and demo well.",
            headline="The scope is wider than one loop.",
            action="Cut to one path and write down what you are deliberately skipping.",
            kind="scope",
        )
    if not idea.user_outcome:
        return GuidanceItem(
            title="No visible end result",
            detail="It is not clear what the user sees at the end of the workflow.",
            headline="The end result needs to be visible.",
            action="Decide the single result the user sees at the end, and build toward it.",
            kind="outcome_undefined",
        )
    if (
        sponsor_fit
        and sponsor_fit.biggest_missing_requirement
        and sponsor_fit.fit_level in (FitLevel.MODERATE, FitLevel.STRONG, FitLevel.VERY_STRONG)
    ):
        return GuidanceItem(
            title="A documented requirement is not addressed yet",
            detail=_short(f"{sponsor_fit.award_title}: {sponsor_fit.biggest_missing_requirement}"),
            headline="One documented requirement is uncovered.",
            action=f"Decide how the idea meets this before you start: {_short(sponsor_fit.biggest_missing_requirement, 90)}",
            kind="prize_requirement",
        )
    return GuidanceItem(
        title="What makes it different is not stated",
        detail="Nothing in the description says why this beats an obvious alternative.",
        headline="The differentiator needs stating.",
        action="Write one sentence on what this does that the obvious alternative doesn't.",
        kind="differentiator",
    )


def historical_takeaway(history: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    One short, data-backed sentence about the chosen baseline. Returns None when the data does not support a claim.
    `history` is baselines.load_history's result: a label plus cohort comparison rows.
    """
    if not history:
        return None
    try:
        label = history.get("label") or "this dataset"
        rows = {r["dimension_or_feature"]: r for r in history["cohort_comparisons"]["winners_vs_nonwinners"]}
        tech = rows.get("technical_depth")
        demo = rows.get("demo_strength")
        parts = []
        if tech and str(tech.get("interpretation", "")).lower().startswith("negligible"):
            parts.append(
                f"Technical depth barely separated winners from non-winners in {label} "
                f"(n={tech['sample_a']} vs {tech['sample_b']}), so extra backend work alone is not the priority."
            )
        if demo and "higher in winners" in str(demo.get("interpretation", "")).lower():
            parts.append(f"Demo strength was one dimension that leaned toward winners in {label}.")
        return " ".join(parts) or None
    except (KeyError, TypeError):
        return None


def load_history_summary(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except Exception:
        return None


def build_idea_guidance(
    idea: ExtractedIdea,
    description: str,
    prize_fits: List[PrizeFit],
    history_takeaway: Optional[str] = None,
) -> IdeaGuidance:
    steps_defined = len(parse_workflow_steps(idea.core_workflow)) >= 2
    steps = build_first_steps(idea, prize_fits)
    dont_build = find_dont_build(idea, description, prize_fits)
    strongest = pick_strongest(idea, description, prize_fits, steps_defined)
    gap = pick_biggest_gap(idea, description, prize_fits, steps_defined, len(dont_build))
    sponsor_fit = _first_top_fit(prize_fits, sponsor_only=True)

    if steps_defined:
        first_action = {
            "action": f"Build the complete loop first: {steps[0].lower()} through to “{steps[-1].lower()}”.",
            "reason": "Nothing else matters until one real input becomes one visible result.",
        }
    else:
        first_action = {
            "action": "Pick one real input and build the whole path to one visible result.",
            "reason": "A single working path is worth more than several half-built features.",
        }
    actions: List[Dict[str, str]] = [first_action]

    named = sponsor_fit and sponsor_fit.sponsor_name and sponsor_fit.sponsor_name.lower() in [
        t.lower() for t in idea.likely_sponsor_technologies
    ]
    if (
        sponsor_fit
        and sponsor_fit.fit_level in (FitLevel.STRONG, FitLevel.VERY_STRONG)
        and sponsor_fit.sponsor_name
        and sponsor_fit.what_must_be_demonstrated
        and (named or steps_defined)
    ):
        first_proof = sponsor_fit.what_must_be_demonstrated[0].lower()
        if named:
            actions.append({
                "action": f"Make the {sponsor_fit.sponsor_name} integration visible in the demo.",
                "reason": f"{sponsor_fit.award_title} asks judges to see: {first_proof}.",
            })
        else:
            actions.append({
                "action": f"If you go for {sponsor_fit.award_title}, show this in the demo: {first_proof}.",
                "reason": "It is the first thing that challenge's documented criteria ask judges to see.",
            })
    else:
        actions.append({
            "action": f"Script a 2-minute demo that ends on “{steps[-1].lower()}”.",
            "reason": "The demo should show the whole loop working once, live.",
        })

    if gap.action:
        actions.append({"action": gap.action, "reason": gap.detail})

    headline = f"{strongest.headline}\n{gap.headline}"
    summary = _short(f"Strongest: {strongest.title[:1].lower() + strongest.title[1:]}. Biggest gap: {gap.title[:1].lower() + gap.title[1:]}.", 200)

    return IdeaGuidance(
        strongest=strongest,
        biggest_gap=gap,
        build_first_steps=steps,
        build_first=" → ".join(steps),
        dont_build_yet=dont_build,
        before_hackathon=[{k: _short(v, 200) for k, v in a.items()} for a in actions[:3]],
        headline=headline,
        summary=summary,
        historical_takeaway=history_takeaway,
    )


def is_valid_build_first(text: Optional[str]) -> bool:
    """An LLM-supplied build_first is only accepted if it is a real end-to-end chain that doesn't open with infrastructure."""
    if not text:
        return False
    steps = [s.strip() for s in text.split("→") if s.strip()]
    if not (3 <= len(steps) <= MAX_STEPS + 1):
        return False
    return not FORBIDDEN_FIRST_STEPS.search(steps[0])


def is_valid_action(text: Optional[str]) -> bool:
    return bool(text) and len(text) <= 220 and not _ACTION_PLACEHOLDER_WORDS.search(text)
