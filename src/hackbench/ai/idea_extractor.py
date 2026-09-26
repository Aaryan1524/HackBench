import re
import json
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from .chatgpt import ChatGPTClient

logger = logging.getLogger("hackbench.ai.idea_extractor")

KNOWN_SPONSOR_KEYWORDS = {
    "google cloud": "Google Cloud",
    "gcp": "Google Cloud",
    "gemini": "Google Cloud",
    "solana": "Solana",
    "digitalocean": "DigitalOcean",
    "digital ocean": "DigitalOcean",
    "snowflake": "Snowflake",
    "tiger data": "Tiger Data",
    "timescale": "Tiger Data",
    "godaddy": "GoDaddy Registry",
    "elevenlabs": "ElevenLabs",
    "twilio": "Twilio",
    "hedera": "Hedera",
    "wolfram": "Wolfram",
    "mongodb": "MongoDB",
    "microsoft": "Microsoft",
    "azure": "Microsoft Azure",
    "github": "GitHub",
    "cohere": "Cohere",
    "pinecone": "Pinecone",
    "openai": "OpenAI",
    "vercel": "Vercel",
    "supabase": "Supabase",
    "aws": "AWS",
    "firebase": "Firebase",
    "stripe": "Stripe",
}

COMMON_TECH_KEYWORDS = [
    "react", "next.js", "nextjs", "vue", "angular", "svelte", "tailwind", "css",
    "python", "fastapi", "flask", "django", "nodejs", "node.js", "express", "go", "golang",
    "rust", "swift", "kotlin", "flutter", "react native", "ios", "android",
    "postgresql", "postgres", "sqlite", "redis", "mysql", "graphql", "rest", "docker",
    "webrtc", "websockets", "speech-to-text", "text-to-speech", "voice", "agent", "llm"
]


class ExtractedIdea(BaseModel):
    problem: Optional[str] = None
    target_user: Optional[str] = None
    proposed_product: Optional[str] = None
    core_workflow: Optional[str] = None
    intended_technologies: List[str] = Field(default_factory=list)
    likely_sponsor_technologies: List[str] = Field(default_factory=list)
    user_outcome: Optional[str] = None
    notable_constraints: Optional[str] = None
    confidence_scores: Dict[str, float] = Field(default_factory=dict)
    # The user's own words, kept in memory so prize matching can read them. Never serialized or sent anywhere.
    source_text: Optional[str] = Field(default=None, exclude=True)


class IdeaExtractor:
    """
    Extracts structured hackathon idea components from unstructured idea descriptions.
    Preserves uncertainty: if an attribute is not present, it remains None rather than being invented.
    """

    def __init__(self, chatgpt_client: Optional[ChatGPTClient] = None):
        self.client = chatgpt_client or ChatGPTClient()

    def extract(
        self,
        description: str,
        technologies_of_interest: Optional[List[str]] = None,
    ) -> ExtractedIdea:
        desc = (description or "").strip()
        if not desc:
            return ExtractedIdea()

        technologies_of_interest = [t.strip() for t in (technologies_of_interest or []) if t.strip()]

        # Try LLM-assisted extraction if configured
        if self.client.is_configured:
            try:
                llm_result = self._extract_with_llm(desc, technologies_of_interest)
                if llm_result:
                    llm_result.source_text = desc
                    return llm_result
            except Exception as e:
                logger.warning(f"LLM idea extraction failed: {e}. Falling back to heuristic extraction.")

        # Fallback to deterministic heuristic extraction
        result = self._extract_heuristic(desc, technologies_of_interest)
        result.source_text = desc
        return result

    def _extract_with_llm(self, description: str, technologies_of_interest: List[str]) -> Optional[ExtractedIdea]:
        prompt = f"""You are an objective parser extracting structured components from a hackathon idea description.

STRICT INVARIANTS:
1. ONLY extract information that is explicitly stated or directly entailed by the description.
2. If a field is NOT mentioned or cannot be determined with certainty, return null for that field.
3. DO NOT extrapolate, assume, or invent facts (e.g. do not invent target users or time constraints if not stated).

<IDEA_DESCRIPTION>
{description}
</IDEA_DESCRIPTION>

User-specified technologies of interest: {json.dumps(technologies_of_interest)}

Return ONLY a JSON object with this schema:
{{
  "problem": string or null,
  "target_user": string or null,
  "proposed_product": string or null,
  "core_workflow": string or null,
  "intended_technologies": [string],
  "likely_sponsor_technologies": [string],
  "user_outcome": string or null,
  "notable_constraints": string or null,
  "confidence_scores": {{"problem": float, "target_user": float, ...}}
}}"""

        import httpx
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.client.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.client.model,
            "messages": [
                {"role": "system", "content": "You are a precise data extractor that returns strictly valid JSON and never invents missing fields."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(timeout=self.client.timeout_seconds) as http_client:
            res = http_client.post(url, headers=headers, json=payload)
            if res.status_code == 200:
                data = json.loads(res.json()["choices"][0]["message"]["content"])
                
                # Merge explicit technologies of interest if not present
                intended = data.get("intended_technologies") or []
                for t in technologies_of_interest:
                    if t not in intended:
                        intended.append(t)
                data["intended_technologies"] = intended

                # Check sponsor mapping
                sponsors = data.get("likely_sponsor_technologies") or []
                for item in intended + [description]:
                    for kw, name in KNOWN_SPONSOR_KEYWORDS.items():
                        if kw in str(item).lower() and name not in sponsors:
                            sponsors.append(name)
                data["likely_sponsor_technologies"] = sponsors

                return ExtractedIdea.model_validate(data)
            else:
                logger.warning(f"OpenAI extraction returned status {res.status_code}: {res.text[:200]}")
                return None

    @staticmethod
    def _find_workflow(description: str, sentences: List[str]) -> Optional[str]:
        """
        A workflow is a sequence: 'X does A, does B, and does C' or 'A -> B'.
        A single-clause sentence is a description, not a workflow, so it stays unknown.
        """
        normalized = re.sub(r"\s*(?:-{1,2}>|=>|→)\s*", " → ", description)
        candidates: List[str] = []
        for m in re.finditer(r"\b(?:that|which|where|then)\s+([^.!?\n]+)", normalized, re.IGNORECASE):
            candidates.append(m.group(1).strip())
        candidates += [s for s in re.split(r"[.!?\n]+", normalized) if "→" in s]

        for cand in candidates:
            if "→" in cand:
                parts = [p for p in cand.split("→") if len(p.split()) >= 1]
                if len(parts) >= 2:
                    return " → ".join(p.strip() for p in parts).strip(" ,")
            clauses = [c for c in re.split(r",\s*(?:and\s+|then\s+)?|\s+and then\s+|\s+then\s+|\s+and\s+", cand) if len(c.split()) >= 2]
            if len(clauses) >= 2:
                return cand.strip(" ,")
        return None

    def _extract_heuristic(self, description: str, technologies_of_interest: List[str]) -> ExtractedIdea:
        desc_lower = description.lower()
        sentences = [s.strip() for s in re.split(r'[.!?\n]+', description) if s.strip()]

        problem: Optional[str] = None
        target_user: Optional[str] = None
        proposed_product: Optional[str] = None
        core_workflow: Optional[str] = None
        user_outcome: Optional[str] = None
        notable_constraints: Optional[str] = None
        confidences: Dict[str, float] = {}

        # 1. Proposed Product Extraction
        # Look for "want to build [X]", "building [X]", "a [X] that..."
        product_match = re.search(r"(?:want to build|building|build|create|creating)\s+(?:an?|the)?\s*([a-z0-9\s\-]+?)(?=\s+(?:for|that|which|to|where)\b|[.,;]|$)", description, re.IGNORECASE)
        if product_match:
            proposed_product = product_match.group(1).strip()
            confidences["proposed_product"] = 0.85
        elif sentences:
            # First clause of first sentence
            first_clause = re.split(r'[,;]', sentences[0])[0].strip()
            if len(first_clause.split()) <= 10:
                proposed_product = first_clause
                confidences["proposed_product"] = 0.60

        # 2. Target User Extraction
        # Look for "for [users]", "targeting [users]", "designed for [users]", "aimed at [users]"
        user_match = re.search(r"\b(?:for|targeting|designed for|built for|aimed at|helping)\s+([a-z0-9\s\-']+?)(?=\s+(?:who|that|which|to|and|so|but)\b|[.,;]|$)", description, re.IGNORECASE)
        if user_match:
            cand = re.sub(r"\s+(?:mostly|mainly|primarily|mostly)$", "", user_match.group(1).strip(), flags=re.IGNORECASE)
            # Exclude actions/gerunds like "managing", "tracking", "building", and pronouns
            words = cand.lower().split()
            # a lone singular word ("education", "fun") is a topic, not a person
            if len(words) == 1 and not words[0].endswith("s"):
                cand = ""
            if cand and not any(w.endswith("ing") for w in words[:1]) and not any(w in cand.lower() for w in ["this", "it", "free", "fun", "now", "example"]):
                target_user = cand
                confidences["target_user"] = 0.80

        # Secondary user check: managers, students, developers, etc.
        user_keywords = [
            "managers", "students", "developers", "hackers",
            "patients", "doctors", "guests", "consumers", "travelers", "shoppers",
            "educators", "teachers", "engineers", "designers", "researchers",
            "nurses", "owners", "farmers", "beekeepers", "parents", "caregivers"
        ]
        for uk in user_keywords:
            if uk in desc_lower:
                # If target_user was generic or none, prefer the explicit persona
                if not target_user or target_user in ["them"]:
                    target_user = uk
                    confidences["target_user"] = 0.85
                    break

        # 3. Problem Extraction
        # Look for "problem", "struggle", "pain point", "currently", "instead of", "waste", "trouble", "hard to", "difficult to"
        problem_keywords = [
            "problem", "struggle", "pain point", "painpoint", "hard to", "difficult to", "waste", "lacking",
            "without", "inefficient", "can't", "cannot", "afford", "forget", "expensive", "tedious", "manual",
        ]
        for s in sentences:
            if any(pk in s.lower() for pk in problem_keywords):
                problem = s
                confidences["problem"] = 0.75
                break

        # 4. Core Workflow Extraction
        # Look for sequential actions: "reads X ... flags Y ... sends Z" or "first ... then"
        core_workflow = self._find_workflow(description, sentences)
        if core_workflow:
            confidences["core_workflow"] = 0.80

        # 5. User Outcome Extraction
        # Look for "turns ... into", "generates", "delivers", "results in", "provides", "insights for"
        outcome_match = re.search(r'(?:turns?|generates?|provides?|delivers?|results? in|producing)\s+([a-z0-9\s\-]+?)(?:for|\.|$)', description, re.IGNORECASE)
        if outcome_match:
            user_outcome = outcome_match.group(0).strip()
            confidences["user_outcome"] = 0.75

        # 6. Notable Constraints Extraction
        # Look for "real-time", "offline", "mobile-only", "under 5 seconds"
        constraint_match = re.search(r'\b(real-?time|offline|mobile-?only|within \d+ [a-z]+|low latency)\b', desc_lower)
        if constraint_match:
            notable_constraints = constraint_match.group(1)
            confidences["notable_constraints"] = 0.80

        # 7. Intended Technologies & Sponsors
        intended: List[str] = []
        sponsors: List[str] = []

        # From explicit technologies_of_interest
        for t in technologies_of_interest:
            if t not in intended:
                intended.append(t)
            t_lower = t.lower()
            for kw, canonical in KNOWN_SPONSOR_KEYWORDS.items():
                if kw in t_lower and canonical not in sponsors:
                    sponsors.append(canonical)

        # From text matching
        for kw, canonical in KNOWN_SPONSOR_KEYWORDS.items():
            if re.search(r'\b' + re.escape(kw) + r'\b', desc_lower):
                if canonical not in sponsors:
                    sponsors.append(canonical)
                if canonical not in intended:
                    intended.append(canonical)

        for tk in COMMON_TECH_KEYWORDS:
            if re.search(r'\b' + re.escape(tk) + r'\b', desc_lower):
                capitalized = tk.capitalize() if tk not in ["css", "llm", "rest"] else tk.upper()
                if capitalized not in intended:
                    intended.append(capitalized)

        return ExtractedIdea(
            problem=problem,
            target_user=target_user,
            proposed_product=proposed_product,
            core_workflow=core_workflow,
            intended_technologies=intended,
            likely_sponsor_technologies=sponsors,
            user_outcome=user_outcome,
            notable_constraints=notable_constraints,
            confidence_scores=confidences,
        )
