"""
Prize Fit Evaluation Engine for HackBench.

Evaluates an extracted hackathon idea against documented event awards and tracks.
Strictly criteria-alignment grounded; produces ZERO win probability predictions.
"""
from enum import Enum
from typing import List, Optional, Dict, Any
from pathlib import Path
import os
import json
import logging
import re
from pydantic import BaseModel, Field

from ..models.event import HackathonEvent, PrizeCategory
from .idea_extractor import ExtractedIdea
from .chatgpt import ChatGPTClient
from .baselines import prize_has_criteria

logger = logging.getLogger("hackbench.ai.prize_matcher")

FORBIDDEN_WIN_TERMS = [
    r"\bwin probability\b",
    r"\bwinning probability\b",
    r"\bchance to win\b",
    r"\bchances to win\b",
    r"\bmost likely to win\b",
    r"\blikely to win\b",
    r"\bwill win\b",
    r"\bbest chance\b",
    r"\bhighest probability\b",
    r"\beasiest prize\b",
    r"\bpredict win\b",
    r"\bwin prediction\b",
    r"\bguaranteed prize\b",
    r"\beasy win\b",
]


class FitLevel(str, Enum):
    VERY_STRONG = "very_strong"
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    VERY_WEAK = "very_weak"
    INSUFFICIENT_CRITERIA = "insufficient_criteria"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class SponsorTechRole(str, Enum):
    CENTRAL = "central"
    DECORATIVE = "decorative"
    ABSENT = "absent"
    NOT_APPLICABLE = "not_applicable"


class PrizeFit(BaseModel):
    prize_id: str
    award_title: str
    sponsor_name: Optional[str] = None
    prize_type: str = "general"
    fit_level: FitLevel
    fit_label: str
    why_it_fits: str
    why_it_may_not_fit: str
    documented_requirements: List[str] = Field(default_factory=list)
    what_must_be_demonstrated: List[str] = Field(default_factory=list)
    biggest_missing_requirement: str
    sponsor_tech_role: SponsorTechRole = SponsorTechRole.NOT_APPLICABLE
    historical_context: Optional[str] = None
    insufficient_criteria: bool = False


class PrizeFitResult(BaseModel):
    targeting_mode: str = "auto"  # "auto" or "specific"
    top_fits: List[PrizeFit] = Field(default_factory=list)
    evaluated_count: int = 0
    insufficient_criteria_count: int = 0
    summary: str = ""


def sanitize_fit_language(text: str) -> str:
    """Strictly replaces any win probability language with criteria-fit terminology."""
    if not text:
        return text
    clean = text
    clean = re.sub(r"(?i)\bwin probability\b", "criteria fit", clean)
    clean = re.sub(r"(?i)\bwinning probability\b", "requirement alignment", clean)
    clean = re.sub(r"(?i)\bchance to win\b", "alignment level", clean)
    clean = re.sub(r"(?i)\bchances to win\b", "degree of fit", clean)
    clean = re.sub(r"(?i)\bmost likely to win\b", "strongest documented fit", clean)
    clean = re.sub(r"(?i)\blikely to win\b", "well-aligned", clean)
    clean = re.sub(r"(?i)\bbest chance\b", "strongest fit", clean)
    clean = re.sub(r"(?i)\bhighest probability\b", "closest match", clean)
    clean = re.sub(r"(?i)\beasiest prize\b", "most accessible criteria match", clean)
    clean = re.sub(r"(?i)\beasy win\b", "strong alignment", clean)
    clean = re.sub(r"(?i)\bpredict win\b", "assess criteria alignment", clean)
    return clean


_PRIZE_STOPWORDS = set("""
about above after also another around based been before being best build building built challenge challenges
create creating creative develop developing each every from give have hackathon hack hacks has into like make
more most must need other over prize prizes project projects should some team teams that their them then these
they this those through track using want what when where which will with without work would your you our
overall place second third first winner winners judging judges submission submissions idea ideas application
applications app apps tool tools solution solutions system systems use used uses users user
business businesses small large owner owners real time people community communities customer customers
service services data help helps helping make making better simple easy access world life daily
company companies people person student students
close either compare compared comparing public publicly future plan planned planning available various similar
include includes including example examples potential able around same where whether either both single multiple
often many much such very more less other another new existing current specific important key main
""".split())


def _stem(word: str) -> str:
    w = word
    for prefix in ("non-", "non", "in", "un"):
        if w.startswith(prefix) and len(w) - len(prefix) >= 6:
            w = w[len(prefix):]
            break
    for suffix in ("ing", "ed", "es", "ly", "s", "e"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 4:
            w = w[: -len(suffix)]
            break
    return w


def _salient_terms(text: str) -> Dict[str, str]:
    """Content words as {stem: original word}. Stems let 'spending' match 'spend' and 'accessible' match 'inaccessible'."""
    terms: Dict[str, str] = {}
    lowered = (text or "").lower()
    # Short acronyms that name a technology area. AI is handled separately by _ai_terms.
    for a in ("ar", "vr", "xr", "iot", "llm"):
        if re.search(rf"\b{a}\b", lowered):
            terms[a] = a
    for w in re.findall(r"[a-z][a-z\-]{3,}", lowered):
        if w in _PRIZE_STOPWORDS or w.rstrip("s") in _PRIZE_STOPWORDS:
            continue
        terms.setdefault(_stem(w), w)
    return terms


def _ai_terms(prize_text: str, idea_text: str) -> Dict[str, str]:
    """'AI' is in nearly every description, so it only counts when the challenge is about AI and the idea uses it."""
    prize = (prize_text or "").lower()
    idea = (idea_text or "").lower()
    if not re.search(r"\bai\b|artificial intelligence|machine learning", idea) and not re.search(
        r"\b(llm|gpt|vision model|speech recognition|neural|classifier|model)\b", idea
    ):
        return {}
    if re.search(r"\bai[- ]powered\b|\b(use|using|use of)\s+(of\s+)?ai\b", prize):
        return {"ai-a": "AI-powered", "ai-b": "uses AI"}  # counts double: the challenge asks for it outright
    if re.search(r"\bai\b", prize) or "artificial intelligence" in prize:
        return {"ai-a": "AI"}
    return {}


_EXCLUSION_PATTERNS = {
    "a chatbot": r"\bchat\s?bots?\b|\bchat (?:window|interface)\b",
}


def _violated_exclusion(description: str, idea_text: str) -> Optional[str]:
    """If the prize says something 'cannot be X' and the idea is X, return 'a X'."""
    for m in re.finditer(
        r"\b(?:cannot|can't|can not|must not|should not)\s+be\s+(an?\s+)?([a-z][a-z\-]{2,25})\b",
        description or "", re.IGNORECASE,
    ):
        term = m.group(2).lower()
        key = f"a {term}"
        pattern = _EXCLUSION_PATTERNS.get(key, rf"\b{re.escape(term)}s?\b")
        if re.search(pattern, idea_text or "", re.IGNORECASE):
            return key
    return None


def _requirement_phrases(description: str, limit: int = 3) -> List[str]:
    """Sentences from the prize's own description that state what a project must do, verbatim and short."""
    text = re.sub(r"\*+", "", description or "")
    text = re.sub(r"(?im)^\s*prize:.*$", "", text)
    # An explicit "Requirements:" section is what judges check, so it comes first.
    if "Requirements:" in text:
        head, _, tail = text.partition("Requirements:")
        text = f"{tail}\n{head}"
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.split()) >= 4]
    modal = re.compile(r"\b(must|should|require[sd]?|need|build|create|develop|design|use|using|integrat\w+|solve|challenge)\b", re.I)
    picked = [s for s in sentences if modal.search(s)] or sentences
    return [(p[:140] + "…") if len(p) > 140 else p for p in picked[:limit]]



class PrizeMatcher:
    """
    Evaluates hackathon ideas against documented prize criteria.
    Never invents unstated criteria. Never estimates win probability.
    """

    def __init__(self, chatgpt_client: Optional[ChatGPTClient] = None):
        self.client = chatgpt_client or ChatGPTClient()

    def load_event_prizes(self, event_id: str) -> List[PrizeCategory]:
        """Documented prizes for one year, or every year combined ("all:combined")."""
        from .baselines import load_prizes
        prizes, _exact = load_prizes(event_id)
        return prizes

    def match_prizes(
        self,
        extracted: ExtractedIdea,
        technologies_of_interest: Optional[List[str]] = None,
        event_id: str = "shellhacks2025:2025",
    ) -> PrizeFitResult:
        """
        Automatic Mode: Evaluates idea against all documented event prizes with sufficient criteria.
        Returns top matches sorted primarily by documented requirement alignment.
        """
        prizes = self.load_event_prizes(event_id)
        if not prizes:
            # Fallback default general prizes if no metadata exists
            prizes = [
                PrizeCategory(
                    prize_id="best_overall",
                    title="Best Overall",
                    prize_type="overall",
                    description="Best overall in-person projects based on creativity, technical execution, and user impact.",
                )
            ]

        technologies_of_interest = technologies_of_interest or []
        fits: List[PrizeFit] = []
        insufficient_count = 0

        # Pre-screen prizes for documented criteria sufficiency
        usable_prizes: List[PrizeCategory] = []
        for prize in prizes:
            # A title, a swag item, or a slogan is not criteria: never invent requirements for it.
            if not prize_has_criteria(prize):
                insufficient_count += 1
                fits.append(
                    PrizeFit(
                        prize_id=prize.prize_id,
                        award_title=prize.title,
                        sponsor_name=prize.sponsor_name,
                        prize_type=prize.prize_type,
                        fit_level=FitLevel.INSUFFICIENT_CRITERIA,
                        fit_label="Insufficient criteria",
                        why_it_fits="Cannot be determined from published documentation.",
                        why_it_may_not_fit="The documented prize criteria are insufficient for rigorous evaluation. We do not invent unstated requirements.",
                        documented_requirements=[],
                        what_must_be_demonstrated=[],
                        biggest_missing_requirement="Official challenge details not published.",
                        sponsor_tech_role=SponsorTechRole.NOT_APPLICABLE,
                        insufficient_criteria=True,
                    )
                )
            else:
                usable_prizes.append(prize)

        # 1st/2nd/3rd "Overall" placements are one category, not three separate targets.
        first_overall = next((p for p in usable_prizes if p.prize_type == "overall"), None)
        usable_prizes = [p for p in usable_prizes if p.prize_type != "overall" or p is first_overall]

        # Evaluate usable prizes
        evaluated_fits: List[PrizeFit] = []
        use_llm = os.getenv("ENABLE_LLM_PRIZE_MATCHER", "false").lower() in ("true", "1", "yes")
        if use_llm and self.client.is_configured and usable_prizes:
            try:
                evaluated_fits = self._evaluate_with_llm(extracted, technologies_of_interest, usable_prizes)
            except Exception as e:
                logger.warning(f"LLM prize evaluation failed: {e}. Falling back to deterministic matcher.")
                evaluated_fits = [
                    self._evaluate_deterministic(extracted, technologies_of_interest, p) for p in usable_prizes
                ]
        else:
            evaluated_fits = [
                self._evaluate_deterministic(extracted, technologies_of_interest, p) for p in usable_prizes
            ]

        # Sanitize all outputs to eliminate win-probability phrases
        for f in evaluated_fits:
            f.why_it_fits = sanitize_fit_language(f.why_it_fits)
            f.why_it_may_not_fit = sanitize_fit_language(f.why_it_may_not_fit)
            f.biggest_missing_requirement = sanitize_fit_language(f.biggest_missing_requirement)
            f.what_must_be_demonstrated = [sanitize_fit_language(x) for x in f.what_must_be_demonstrated]

        # Filter out insufficient criteria for top ranking
        valid_evaluated = [f for f in evaluated_fits if not f.insufficient_criteria]

        # Sorting: Primarily by documented requirement alignment
        level_scores = {
            FitLevel.VERY_STRONG: 5,
            FitLevel.STRONG: 4,
            FitLevel.MODERATE: 3,
            FitLevel.WEAK: 2,
            FitLevel.VERY_WEAK: 1,
            FitLevel.INSUFFICIENT_CRITERIA: 0,
            FitLevel.INSUFFICIENT_EVIDENCE: 0,
        }
        role_scores = {
            SponsorTechRole.CENTRAL: 3,
            SponsorTechRole.NOT_APPLICABLE: 2,
            SponsorTechRole.DECORATIVE: 1,
            SponsorTechRole.ABSENT: 0,
        }

        # Sort primarily by fit_level score, tie-breaker: sponsor tech centrality & demonstrated items count
        valid_evaluated.sort(
            key=lambda x: (
                level_scores.get(x.fit_level, 0),
                role_scores.get(x.sponsor_tech_role, 0),
                len(x.what_must_be_demonstrated),
            ),
            reverse=True,
        )

        top_fits = valid_evaluated[:3]

        # Generate summary
        has_strong = any(f.fit_level in (FitLevel.VERY_STRONG, FitLevel.STRONG) for f in top_fits)
        has_sponsor_strong = any(
            f.fit_level in (FitLevel.VERY_STRONG, FitLevel.STRONG) and f.prize_type in ("sponsor", "track")
            for f in top_fits
        )

        if not has_strong:
            summary = (
                "No clearly strong sponsor fit yet. "
                "Best Overall currently aligns better than the available sponsor tracks based on the documented criteria."
            )
        elif not has_sponsor_strong and any(f.prize_type == "overall" for f in top_fits):
            summary = (
                "Strongest alignment is with general hackathon excellence tracks. "
                "No sponsor challenges currently have central technical overlap with this concept."
            )
        else:
            top_names = [f.award_title for f in top_fits[:2]]
            summary = f"Closest documented requirement alignment with {', '.join(top_names)}."

        return PrizeFitResult(
            targeting_mode="auto",
            top_fits=top_fits,
            evaluated_count=len(usable_prizes),
            insufficient_criteria_count=insufficient_count,
            summary=summary,
        )

    @staticmethod
    def find_prize(prizes: List[PrizeCategory], award_id: str) -> Optional[PrizeCategory]:
        """The documented prize an id refers to: by id, else by (loosely matched) title."""
        clean = (award_id or "").lower().replace(" ", "_")
        for p in prizes:
            if p.prize_id == award_id or p.prize_id.lower() == clean:
                return p
        for p in prizes:
            if clean and clean in p.title.lower().replace(" ", "_"):
                return p
        return None

    def evaluate_specific_prize(
        self,
        extracted: ExtractedIdea,
        technologies_of_interest: Optional[List[str]],
        event_id: str,
        award_id: str,
    ) -> PrizeFitResult:
        """
        Specific-Prize Mode: Directly analyzes the idea against the chosen award.
        """
        prizes = self.load_event_prizes(event_id)
        target_prize = self.find_prize(prizes, award_id)
        clean_target = award_id.lower().replace(" ", "_")

        if not target_prize:
            # Synthesize fallback category if known standard track
            if "overall" in clean_target:
                target_prize = PrizeCategory(
                    prize_id="best_overall",
                    title="Best Overall",
                    prize_type="overall",
                    description="Best overall in-person projects based on creativity, technical execution, and user impact.",
                )
            else:
                target_prize = PrizeCategory(
                    prize_id=award_id,
                    title=award_id.replace("_", " ").title(),
                    prize_type="track",
                    description="Documented criteria for selected track.",
                )

        fit = self._evaluate_deterministic(extracted, technologies_of_interest or [], target_prize)
        fit.why_it_fits = sanitize_fit_language(fit.why_it_fits)
        fit.why_it_may_not_fit = sanitize_fit_language(fit.why_it_may_not_fit)
        fit.biggest_missing_requirement = sanitize_fit_language(fit.biggest_missing_requirement)
        fit.what_must_be_demonstrated = [sanitize_fit_language(x) for x in fit.what_must_be_demonstrated]

        return PrizeFitResult(
            targeting_mode="specific",
            top_fits=[fit],
            evaluated_count=1,
            insufficient_criteria_count=1 if fit.insufficient_criteria else 0,
            summary=f"Evaluated directly against {target_prize.title}.",
        )

    def _evaluate_deterministic(
        self,
        extracted: ExtractedIdea,
        technologies_of_interest: List[str],
        prize: PrizeCategory,
    ) -> PrizeFit:
        """
        Deterministic, rule-grounded fit evaluator based purely on observable criteria.
        """
        desc = (prize.description or "").strip()
        title_lower = prize.title.lower()
        desc_lower = desc.lower()

        # Check criteria sufficiency
        if not prize_has_criteria(prize):
            return PrizeFit(
                prize_id=prize.prize_id,
                award_title=prize.title,
                sponsor_name=prize.sponsor_name,
                prize_type=prize.prize_type,
                fit_level=FitLevel.INSUFFICIENT_CRITERIA,
                fit_label="Insufficient criteria",
                why_it_fits="Cannot be determined from published documentation.",
                why_it_may_not_fit="The documented prize criteria are insufficient for rigorous evaluation. We do not invent unstated requirements.",
                documented_requirements=[],
                what_must_be_demonstrated=[],
                biggest_missing_requirement="Official challenge details not published.",
                sponsor_tech_role=SponsorTechRole.NOT_APPLICABLE,
                insufficient_criteria=True,
            )

        # Context text of the idea
        idea_text = " ".join(
            filter(
                None,
                [
                    extracted.proposed_product,
                    extracted.core_workflow,
                    extracted.problem,
                    extracted.user_outcome,
                    extracted.source_text,
                ],
            )
        ).lower()
        all_tech = [t.lower() for t in (extracted.intended_technologies + technologies_of_interest)]

        # 1. Best Overall Track
        if prize.prize_type == "overall" or "overall" in title_lower or "best overall" in title_lower:
            has_product = bool(extracted.proposed_product)
            has_workflow = bool(extracted.core_workflow)
            has_user = bool(extracted.target_user)

            if has_product and has_workflow and has_user:
                return PrizeFit(
                    prize_id=prize.prize_id,
                    award_title=prize.title,
                    sponsor_name=None,
                    prize_type="overall",
                    fit_level=FitLevel.STRONG,
                    fit_label="Strong fit",
                    why_it_fits="Clear user problem, practical workflow, and strong live demo potential.",
                    why_it_may_not_fit="Technical differentiation and competitive moat are not yet obvious compared to open-ended cohort entries.",
                    documented_requirements=_requirement_phrases(desc) if len(desc.split()) >= 8 else [],
                    what_must_be_demonstrated=[
                        "End-to-end working demonstration",
                        "Clear solution to the identified problem",
                        "Practical utility for target users",
                    ],
                    biggest_missing_requirement="Observable proof of technical execution and differentiation.",
                    sponsor_tech_role=SponsorTechRole.NOT_APPLICABLE,
                    historical_context="Historical ShellHacks winners showed complete end-to-end user journeys during judging.",
                )
            else:
                return PrizeFit(
                    prize_id=prize.prize_id,
                    award_title=prize.title,
                    sponsor_name=None,
                    prize_type="overall",
                    fit_level=FitLevel.MODERATE,
                    fit_label="Moderate fit",
                    why_it_fits="Applies broadly to general hackathon judging dimensions.",
                    why_it_may_not_fit="Problem scope or core workflow needs further sharpening before implementation.",
                    documented_requirements=["Creativity", "Technical execution", "Working live demonstration"],
                    what_must_be_demonstrated=["Clear problem definition", "Concrete MVP user workflow"],
                    biggest_missing_requirement="Well-defined core user loop.",
                    sponsor_tech_role=SponsorTechRole.NOT_APPLICABLE,
                )

        # 2. Voice / Conversational AI Challenge (e.g. ElevenLabs)
        # Judge by the prize's own title (or its named sponsor tech); a description merely mentioning "voice" is not a voice challenge.
        is_voice_prize = any(k in title_lower for k in ["voice", "elevenlabs", "conversational ai", "speech"]) or any(
            k in desc_lower for k in ["elevenlabs", "conversational ai"]
        )
        if is_voice_prize:
            voice_pattern = (
                r"\b(voice|speech|spoken|speak\w*|dictat\w+|conversations?|conversational|phone calls?|"
                r"calls? (?:the )?(?:guests?|users?|customers?|patients?|owners?|people)|"
                r"call(?:s|ing) (?:the )?(?:guests?|users?|customers?|patients?|owners?|people)|talk(?:s|ing)? to)\b"
            )
            is_voice_in_loop = bool(re.search(voice_pattern, idea_text))
            is_voice_tech_listed = any("elevenlabs" in t or "voice" in t or "twilio" in t or "speech" in t for t in all_tech)

            if is_voice_in_loop:
                role = SponsorTechRole.CENTRAL
                return PrizeFit(
                    prize_id=prize.prize_id,
                    award_title=prize.title,
                    sponsor_name=prize.sponsor_name or "ElevenLabs",
                    prize_type=prize.prize_type,
                    fit_level=FitLevel.STRONG if not is_voice_tech_listed else FitLevel.VERY_STRONG,
                    fit_label="Very strong fit" if is_voice_tech_listed else "Strong fit",
                    why_it_fits="Voice is central to the proposed user experience rather than an auxiliary add-on.",
                    why_it_may_not_fit="Must ensure real-time latency and conversation quality remain high during live demo.",
                    documented_requirements=["Voice-first interaction", "Practical conversational utility", "Real-time speech flow"],
                    what_must_be_demonstrated=[
                        "Live voice interaction",
                        "Adaptive response behavior",
                        "Sponsor technology used in primary workflow",
                        "Meaningful end result",
                    ],
                    biggest_missing_requirement="Integration with conversational speech APIs.",
                    sponsor_tech_role=role,
                    historical_context="Historical sponsor winners often used the sponsor technology directly in the primary workflow.",
                )
            elif is_voice_tech_listed:
                # Listed technology but not in core loop -> DECORATIVE! Cannot receive very strong!
                return PrizeFit(
                    prize_id=prize.prize_id,
                    award_title=prize.title,
                    sponsor_name=prize.sponsor_name or "ElevenLabs",
                    prize_type=prize.prize_type,
                    fit_level=FitLevel.MODERATE,
                    fit_label="Moderate fit",
                    why_it_fits="The project mentions voice technology in its planned stack.",
                    why_it_may_not_fit="The core product loop does not rely primarily on voice interaction; sponsor technology appears auxiliary.",
                    documented_requirements=["Voice-first interaction", "Active use of speech API"],
                    what_must_be_demonstrated=["Central voice user interface in core workflow"],
                    biggest_missing_requirement="Making voice the primary interaction mode rather than an auxiliary feature.",
                    sponsor_tech_role=SponsorTechRole.DECORATIVE,
                )
            else:
                return PrizeFit(
                    prize_id=prize.prize_id,
                    award_title=prize.title,
                    sponsor_name=prize.sponsor_name,
                    prize_type=prize.prize_type,
                    fit_level=FitLevel.VERY_WEAK,
                    fit_label="Very weak fit",
                    why_it_fits="None identified from current concept.",
                    why_it_may_not_fit="The proposed concept does not use voice or speech interfaces.",
                    documented_requirements=["Conversational voice integration"],
                    what_must_be_demonstrated=["Complete voice interface"],
                    biggest_missing_requirement="Voice interaction integration.",
                    sponsor_tech_role=SponsorTechRole.ABSENT,
                )

        # 3. Autonomous AI Agent / Google Cloud ADK Challenge
        is_agent_prize = any(k in title_lower or k in desc_lower for k in ["autonomous ai agent", "adk", "agent development kit", "a2a", "agent2agent"])
        if is_agent_prize:
            agent_pattern = r"\b(agents?|autonomous|multi-agent|task-loop)\b"
            is_agent_in_loop = bool(re.search(agent_pattern, idea_text))
            names_google_stack = bool(re.search(r"\b(adk|a2a|google|gemini|vertex)\b", idea_text)) or any(
                re.search(r"google|gemini|adk|vertex", t) for t in all_tech
            )
            if is_agent_in_loop and not names_google_stack:
                return PrizeFit(
                    prize_id=prize.prize_id,
                    award_title=prize.title,
                    sponsor_name="Google Cloud",
                    prize_type=prize.prize_type,
                    fit_level=FitLevel.MODERATE,
                    fit_label="Moderate fit",
                    why_it_fits="The idea describes an agent, which is the challenge's subject.",
                    why_it_may_not_fit="It does not mention Google's Agent Development Kit or Agent2Agent protocol, which the challenge requires.",
                    documented_requirements=["Use Google Agent Development Kit (ADK) or A2A protocol", "Demonstrate autonomous continuous loop"],
                    what_must_be_demonstrated=[
                        "Continuous autonomous execution loop",
                        "ADK / A2A integration",
                    ],
                    biggest_missing_requirement="Documented integration with Google ADK framework.",
                    sponsor_tech_role=SponsorTechRole.ABSENT,
                )
            if is_agent_in_loop:
                return PrizeFit(
                    prize_id=prize.prize_id,
                    award_title=prize.title,
                    sponsor_name="Google Cloud",
                    prize_type=prize.prize_type,
                    fit_level=FitLevel.STRONG,
                    fit_label="Strong fit",
                    why_it_fits="The idea implements an autonomous agent workflow executing continuous follow-up and insight extraction.",
                    why_it_may_not_fit="Requires using Google's Agent Development Kit (ADK) or Agent2Agent protocol to qualify for this challenge.",
                    documented_requirements=["Use Google Agent Development Kit (ADK) or A2A protocol", "Demonstrate autonomous continuous loop"],
                    what_must_be_demonstrated=[
                        "Continuous autonomous execution loop",
                        "Structured tool usage or insight generation",
                        "ADK / A2A integration",
                    ],
                    biggest_missing_requirement="Documented integration with Google ADK framework.",
                    sponsor_tech_role=SponsorTechRole.CENTRAL,
                    historical_context="Historical sponsor winners often used the sponsor technology directly in the primary workflow.",
                )
            else:
                return PrizeFit(
                    prize_id=prize.prize_id,
                    award_title=prize.title,
                    sponsor_name="Google Cloud",
                    prize_type=prize.prize_type,
                    fit_level=FitLevel.WEAK,
                    fit_label="Weak fit",
                    why_it_fits="Could conceptually integrate an agent architecture.",
                    why_it_may_not_fit="The idea does not currently outline an autonomous multi-step agent loop.",
                    documented_requirements=["Google ADK integration", "Autonomous loop"],
                    what_must_be_demonstrated=["Multi-step autonomous execution"],
                    biggest_missing_requirement="Autonomous agent loop design.",
                    sponsor_tech_role=SponsorTechRole.ABSENT,
                )

        # 4. Finance / Capital One Challenge
        # Descriptions of unrelated prizes often name a bank; only a finance-titled prize is a finance challenge.
        is_finance = any(k in title_lower for k in ["finance", "financial", "fintech", "banking", "fraud", "capital one"]) or (
            "capital one" in desc_lower
        )
        if is_finance:
            finance_pattern = r"\b(finances?|financial|banking|banks?|payments?|fraud|receipts?|money|transactions?|credit|defi|blockchain)\b"
            has_finance = bool(re.search(finance_pattern, idea_text)) or any(re.search(finance_pattern, t) for t in all_tech)
            if has_finance:
                return PrizeFit(
                    prize_id=prize.prize_id,
                    award_title=prize.title,
                    sponsor_name=prize.sponsor_name or ("Capital One" if "capital one" in title_lower else None),
                    prize_type=prize.prize_type,
                    fit_level=FitLevel.STRONG,
                    fit_label="Strong fit",
                    why_it_fits="Concept operates directly in the financial services and consumer transaction domain.",
                    why_it_may_not_fit="Must demonstrate innovative technical depth beyond standard expense tracking.",
                    documented_requirements=["Financial services application", "Modern tech stack"],
                    what_must_be_demonstrated=["Transaction handling or financial insight generation"],
                    biggest_missing_requirement="Financial data integration.",
                    sponsor_tech_role=SponsorTechRole.CENTRAL,
                )
            else:
                return PrizeFit(
                    prize_id=prize.prize_id,
                    award_title=prize.title,
                    sponsor_name=prize.sponsor_name or ("Capital One" if "capital one" in title_lower else None),
                    prize_type=prize.prize_type,
                    fit_level=FitLevel.VERY_WEAK,
                    fit_label="Very weak fit",
                    why_it_fits="None identified.",
                    why_it_may_not_fit="The idea addresses a non-financial domain with no connection to banking or financial services.",
                    documented_requirements=["Financial services focus"],
                    what_must_be_demonstrated=["Core financial user value"],
                    biggest_missing_requirement="Financial problem domain alignment.",
                    sponsor_tech_role=SponsorTechRole.ABSENT,
                )

        # 5. Interactive Narrative / Netflix Challenge
        is_netflix = any(k in title_lower or k in desc_lower for k in ["netflix", "interactive entertainment", "choose-your-own-adventure"])
        if is_netflix:
            has_narrative = bool(re.search(r"\b(stor(?:y|ies)|storytelling|narratives?|adventures?|choose[- ]your[- ]own|branching|interactive fiction|interactive entertainment)\b", idea_text))
            if has_narrative:
                return PrizeFit(
                    prize_id=prize.prize_id,
                    award_title=prize.title,
                    sponsor_name="Netflix",
                    prize_type=prize.prize_type,
                    fit_level=FitLevel.STRONG,
                    fit_label="Strong fit",
                    why_it_fits="Focuses on interactive narrative or entertainment experience.",
                    why_it_may_not_fit="Must balance nonlinear storytelling with technical interactive execution.",
                    documented_requirements=["Choose-your-own-adventure style narrative", "Interactive entertainment prototype"],
                    what_must_be_demonstrated=["Branching interactive story flow"],
                    biggest_missing_requirement="Interactive narrative engine.",
                    sponsor_tech_role=SponsorTechRole.CENTRAL,
                )
            else:
                return PrizeFit(
                    prize_id=prize.prize_id,
                    award_title=prize.title,
                    sponsor_name="Netflix",
                    prize_type=prize.prize_type,
                    fit_level=FitLevel.VERY_WEAK,
                    fit_label="Very weak fit",
                    why_it_fits="None identified.",
                    why_it_may_not_fit="The idea is a utility/productivity tool, not an interactive storytelling entertainment application.",
                    documented_requirements=["Interactive narrative flow"],
                    what_must_be_demonstrated=["Branching story engine"],
                    biggest_missing_requirement="Entertainment/narrative focus.",
                    sponsor_tech_role=SponsorTechRole.ABSENT,
                )

        # 6. Auth0 Security Challenge
        is_auth0 = "auth0" in title_lower or "auth0" in desc_lower
        if is_auth0:
            has_auth = "auth0" in all_tech or "auth" in idea_text or "security" in idea_text
            if has_auth:
                return PrizeFit(
                    prize_id=prize.prize_id,
                    award_title=prize.title,
                    sponsor_name="Auth0",
                    prize_type=prize.prize_type,
                    fit_level=FitLevel.MODERATE,
                    fit_label="Moderate fit",
                    why_it_fits="The application can integrate user authentication or role-based access control.",
                    why_it_may_not_fit="Authentication is an infrastructure component rather than the core innovation of the project.",
                    documented_requirements=["Integrate Auth0 API (social sign-in, MFA, or passwordless)"],
                    what_must_be_demonstrated=["Working Auth0 authentication flow"],
                    biggest_missing_requirement="Auth0 SDK integration.",
                    sponsor_tech_role=SponsorTechRole.DECORATIVE,
                )
            else:
                return PrizeFit(
                    prize_id=prize.prize_id,
                    award_title=prize.title,
                    sponsor_name="Auth0",
                    prize_type=prize.prize_type,
                    fit_level=FitLevel.WEAK,
                    fit_label="Weak fit",
                    why_it_fits="Any web or mobile app could add Auth0 login.",
                    why_it_may_not_fit="The idea does not feature authentication as a central focus.",
                    documented_requirements=["Use Auth0 APIs"],
                    what_must_be_demonstrated=["Auth0 integration"],
                    biggest_missing_requirement="Authentication architecture.",
                    sponsor_tech_role=SponsorTechRole.ABSENT,
                )

        # Challenges that require a named technology: the idea has to actually plan to use it.
        if prize.technologies_required_or_encouraged:
            techs = prize.technologies_required_or_encouraged
            words = {re.split(r"\W+", t.strip().lower())[0] for t in techs}
            in_idea = any(re.search(rf"\b{re.escape(w)}", idea_text) for w in words)
            in_stack = any(re.search(rf"\b{re.escape(w)}", t) for t in all_tech for w in words)
            _p = _salient_terms(f"{prize.title} {desc}")
            _p.update(_ai_terms(f"{prize.title} {desc}", idea_text))
            _i = _salient_terms(idea_text)
            _i.update(_ai_terms(f"{prize.title} {desc}", idea_text))
            shared_terms = sorted(_p[k] for k in set(_p) & set(_i))
            required = ", ".join(techs)
            demo = [f"{t} used in the main workflow" for t in techs[:3]]
            base = dict(
                prize_id=prize.prize_id, award_title=prize.title, sponsor_name=prize.sponsor_name,
                prize_type=prize.prize_type, documented_requirements=_requirement_phrases(desc),
                what_must_be_demonstrated=demo,
            )
            if in_idea:
                return PrizeFit(
                    **base, fit_level=FitLevel.STRONG, fit_label="Strong fit",
                    why_it_fits=f"It plans to use {required} in its core workflow.",
                    why_it_may_not_fit="Judges will look for it in the live demo, so it has to be in the main path.",
                    biggest_missing_requirement=f"Show {required} working in the demo.",
                    sponsor_tech_role=SponsorTechRole.CENTRAL,
                )
            if in_stack:
                return PrizeFit(
                    **base, fit_level=FitLevel.MODERATE, fit_label="Moderate fit",
                    why_it_fits=f"{required} is in your planned stack.",
                    why_it_may_not_fit="It is not part of the core workflow described, so it could read as a side feature.",
                    biggest_missing_requirement=f"Make {required} part of the main workflow.",
                    sponsor_tech_role=SponsorTechRole.DECORATIVE,
                )
            level, label = (
                (FitLevel.MODERATE, "Moderate fit") if len(shared_terms) >= 3
                else (FitLevel.WEAK, "Weak fit") if shared_terms
                else (FitLevel.VERY_WEAK, "Very weak fit")
            )
            return PrizeFit(
                **base, fit_level=level, fit_label=label,
                why_it_fits=(f"Shared subject matter with the challenge: {', '.join(shared_terms[:5])}." if shared_terms
                             else "No shared subject matter with the challenge."),
                why_it_may_not_fit=f"It does not mention {required}, which this challenge requires.",
                biggest_missing_requirement=f"Use {required} in the project.",
                sponsor_tech_role=SponsorTechRole.ABSENT,
            )

        # Beginner prizes depend on who is on the team, which an idea does not say.
        if prize.prize_type == "beginner":
            return PrizeFit(
                prize_id=prize.prize_id,
                award_title=prize.title,
                sponsor_name=prize.sponsor_name,
                prize_type=prize.prize_type,
                fit_level=FitLevel.INSUFFICIENT_EVIDENCE,
                fit_label="Depends on your team",
                why_it_fits="Eligibility is about the team, not the idea.",
                why_it_may_not_fit="The idea says nothing about who is on the team.",
                documented_requirements=_requirement_phrases(desc),
                what_must_be_demonstrated=[],
                biggest_missing_requirement="Team eligibility.",
                sponsor_tech_role=SponsorTechRole.NOT_APPLICABLE,
            )

        # Any other documented track: compare the idea with what the prize's own description asks for.
        prize_terms = _salient_terms(f"{prize.title} {desc}")
        idea_terms = _salient_terms(idea_text + " " + " ".join(all_tech))
        ai = _ai_terms(f"{prize.title} {desc}", idea_text + " " + " ".join(all_tech))
        prize_terms.update(ai)
        idea_terms.update(ai)
        shared = sorted(prize_terms[k] for k in set(prize_terms) & set(idea_terms))
        level, label = {
            0: (FitLevel.VERY_WEAK, "Very weak fit"),
            1: (FitLevel.WEAK, "Weak fit"),
            2: (FitLevel.WEAK, "Weak fit"),
            3: (FitLevel.MODERATE, "Moderate fit"),
            4: (FitLevel.MODERATE, "Moderate fit"),
        }.get(len(shared), (FitLevel.STRONG, "Strong fit"))
        requirements = _requirement_phrases(desc)
        # A stated exclusion ("cannot be a chatbot") that the idea runs into caps the fit.
        broken_rule = _violated_exclusion(desc, idea_text)
        if broken_rule and level in (FitLevel.STRONG, FitLevel.MODERATE):
            level, label = FitLevel.WEAK, "Weak fit"
        return PrizeFit(
            prize_id=prize.prize_id,
            award_title=prize.title,
            sponsor_name=prize.sponsor_name,
            prize_type=prize.prize_type,
            fit_level=level,
            fit_label=label,
            why_it_fits=(
                f"This submission and the challenge's description share: {', '.join(shared[:5])}."
                if shared else "No shared subject matter with this challenge's description."
            ),
            why_it_may_not_fit=(
                f"The challenge says the core experience cannot be {broken_rule}, and this describes one."
                if broken_rule else
                "Matching is based on shared wording with the published description, so read the full challenge before targeting it."
                if shared else f"Nothing here touches the subject of '{prize.title}'."
            ),
            documented_requirements=requirements,
            # Only what the documentation itself names; never a generic placeholder.
            what_must_be_demonstrated=(
                [f"{t} used in the main workflow" for t in prize.technologies_required_or_encouraged[:3]]
                or requirements[:3]
            ),
            biggest_missing_requirement=(
                f"The core experience cannot be {broken_rule}." if broken_rule
                else "Nothing specific stands out from the description." if len(shared) >= 5
                else "Direct subject-matter alignment."
            ),
            sponsor_tech_role=SponsorTechRole.ABSENT,
        )

    def _evaluate_with_llm(
        self,
        extracted: ExtractedIdea,
        technologies_of_interest: List[str],
        usable_prizes: List[PrizeCategory],
    ) -> List[PrizeFit]:
        """
        Batched LLM evaluation against documented prize criteria.
        """
        prizes_data = [
            {
                "prize_id": p.prize_id,
                "title": p.title,
                "prize_type": p.prize_type,
                "sponsor_name": p.sponsor_name,
                "description": p.description,
                "required_or_encouraged_technologies": p.technologies_required_or_encouraged,
            }
            for p in usable_prizes
        ]

        prompt = f"""You are an objective hackathon prize criteria alignment analyst.
Evaluate this idea against each documented prize.

CRITICAL INVARIANTS:
1. "Strong prize fit" means the idea aligns well with the DOCUMENTED requirements.
2. It does NOT mean the team is likely to win. NEVER estimate win probability.
3. NEVER use forbidden win terms: "win probability", "best chance", "most likely to win", "easiest prize".
4. Use ONLY fit language: "strongest fit", "best-aligned category", "closest documented match".
5. SPONSOR TECH ROLE:
   - "central": The core problem/workflow cannot function without this technology (e.g. ElevenLabs in a voice agent).
   - "decorative": The technology is mentioned or auxiliary but NOT essential to the core user loop (e.g. Auth0 for generic login).
   - "absent": Not mentioned or used.
   - If decorative, the fit CANNOT be very_strong; it must be moderate or weak.
6. Only use documented criteria. If a prize lacks details, do not invent criteria.

<IDEA>
Proposed Product: {extracted.proposed_product}
Problem: {extracted.problem}
Target User: {extracted.target_user}
Core Workflow: {extracted.core_workflow}
Intended Technologies: {extracted.intended_technologies}
User Technologies of Interest: {technologies_of_interest}
</IDEA>

<DOCUMENTED_PRIZES>
{json.dumps(prizes_data, indent=2)}
</DOCUMENTED_PRIZES>

Evaluate each prize. Return a JSON object with schema:
{{
  "evaluations": [
    {{
      "prize_id": "...",
      "award_title": "...",
      "fit_level": "very_strong" | "strong" | "moderate" | "weak" | "very_weak",
      "fit_label": "Very strong fit" | "Strong fit" | "Moderate fit" | "Weak fit" | "Very weak fit",
      "why_it_fits": "concise explanation of criteria match",
      "why_it_may_not_fit": "concise main gap or limitation",
      "documented_requirements": ["..."],
      "what_must_be_demonstrated": ["..."],
      "biggest_missing_requirement": "...",
      "sponsor_tech_role": "central" | "decorative" | "absent" | "not_applicable",
      "historical_context": "..."
    }}
  ]
}}"""

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.client.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.client.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an objective hackathon criteria alignment engine. Return valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }

        import httpx
        with httpx.Client(timeout=25.0) as client:
            res = client.post(url, headers=headers, json=payload)
            if res.status_code != 200:
                raise RuntimeError(f"OpenAI API returned HTTP {res.status_code}: {res.text[:200]}")
            content = res.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            evals = parsed.get("evaluations", [])

            prizes_by_id = {p.prize_id: p for p in usable_prizes}
            results = []
            for item in evals:
                pid = item.get("prize_id")
                prize_obj = prizes_by_id.get(pid)
                if not prize_obj:
                    continue

                level_str = item.get("fit_level", "moderate").lower()
                try:
                    level = FitLevel(level_str)
                except ValueError:
                    level = FitLevel.MODERATE

                role_str = item.get("sponsor_tech_role", "not_applicable").lower()
                try:
                    role = SponsorTechRole(role_str)
                except ValueError:
                    role = SponsorTechRole.NOT_APPLICABLE

                # Invariant: decorative cannot be very_strong
                if role == SponsorTechRole.DECORATIVE and level == FitLevel.VERY_STRONG:
                    level = FitLevel.MODERATE

                fit_label = {
                    FitLevel.VERY_STRONG: "Very strong fit",
                    FitLevel.STRONG: "Strong fit",
                    FitLevel.MODERATE: "Moderate fit",
                    FitLevel.WEAK: "Weak fit",
                    FitLevel.VERY_WEAK: "Very weak fit",
                }.get(level, "Moderate fit")

                results.append(
                    PrizeFit(
                        prize_id=pid,
                        award_title=prize_obj.title,
                        sponsor_name=prize_obj.sponsor_name,
                        prize_type=prize_obj.prize_type,
                        fit_level=level,
                        fit_label=fit_label,
                        why_it_fits=item.get("why_it_fits", ""),
                        why_it_may_not_fit=item.get("why_it_may_not_fit", ""),
                        documented_requirements=item.get("documented_requirements", []),
                        what_must_be_demonstrated=item.get("what_must_be_demonstrated", []),
                        biggest_missing_requirement=item.get("biggest_missing_requirement", ""),
                        sponsor_tech_role=role,
                        historical_context=item.get("historical_context"),
                    )
                )

            return results
