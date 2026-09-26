import os
import re
import json
import logging
import uuid
import time
import shutil
import threading
import hmac
import ipaddress
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, List, Dict, Any

# Auto-load .env into environment if present
env_file = Path(".env")
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'").strip('"')
            if k and k not in os.environ:
                os.environ[k] = v

from fastapi import FastAPI, HTTPException, Path as FastPath, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from ..ai.router import EvaluationRouter
from ..ai.jev import JevClient, SCORE_LEVEL_VALUES
from ..ai.chatgpt import ChatGPTClient, GeminiClient
from ..ai.idea_guidance import historical_takeaway
from ..ai.prize_matcher import PrizeMatcher, PrizeFitResult
from ..ai.idea_extractor import IdeaExtractor
from ..ai.baselines import prize_has_criteria, DEFAULT_BASELINE, load_history, is_known, is_known_prize_event, label_for, YEAR_BASELINES, ALL_YEARS_ID
from ..collectors.git_repo import RepositoryAnalyzer
from ..collectors.devpost import DevpostCollector
from ..collectors.base import CachedHttpClient
from .security import (
    is_safe_public_url, sanitize_untrusted_text, InMemoryRateLimiter, is_allowed_repo_url,
    client_ip_for, BodySizeLimitMiddleware,
)

logger = logging.getLogger("hackbench.api")

PRODUCTION = os.getenv("HACKBENCH_ENV", "").lower() == "production"
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "").lower() in ("1", "true", "yes")
MAX_REQUEST_BYTES = 64 * 1024
MAX_CONCURRENT_CLONES = 3
REPO_TTL_SECONDS = 3600
MAX_REPO_FILES = 5000
MAX_REPO_READ_BYTES = 500_000
REPO_ANALYSIS_SECONDS = 20
PARTICIPANT_REPOS_DIR = Path("data/raw/participant_repos")
_clone_slots = threading.BoundedSemaphore(MAX_CONCURRENT_CLONES)
MAX_CONCURRENT_ANALYSES = int(os.getenv("MAX_CONCURRENT_ANALYSES", "8"))
_analysis_slots = threading.BoundedSemaphore(MAX_CONCURRENT_ANALYSES)


class DailyBudget:
    """Counts reviews per UTC day and refuses past the limit. In-memory: one instance per backend process."""

    def __init__(self, limit: int):
        self.limit = limit
        self._day = ""
        self._used = 0
        self._lock = threading.Lock()

    def take(self) -> bool:
        if self.limit <= 0:
            return True  # 0 disables the cap
        today = time.strftime("%Y-%m-%d", time.gmtime())
        with self._lock:
            if today != self._day:
                self._day, self._used = today, 0
            if self._used >= self.limit:
                return False
            self._used += 1
            return True

    def refund(self) -> None:
        with self._lock:
            self._used = max(0, self._used - 1)


_daily_budget = DailyBudget(int(os.getenv("DAILY_ANALYSIS_LIMIT", "1500")))


def _sweep_stale_repos() -> None:
    """Delete leftover clones (e.g. from a crash) older than the TTL."""
    if not PARTICIPANT_REPOS_DIR.exists():
        return
    cutoff = time.time() - REPO_TTL_SECONDS
    for child in PARTICIPANT_REPOS_DIR.iterdir():
        try:
            if child.is_dir() and child.stat().st_mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
        except OSError:
            pass


@asynccontextmanager
async def lifespan(_app):
    _sweep_stale_repos()
    if PRODUCTION and not os.getenv("BACKEND_SHARED_SECRET"):
        logger.warning("BACKEND_SHARED_SECRET is not set: /api is open to anyone who can reach this service.")
    yield


app = FastAPI(
    title="HackBench API",
    description="Idea and project review API.",
    version="0.1.0",
    lifespan=lifespan,
    # The interactive docs are for development only.
    docs_url=None if PRODUCTION else "/docs",
    redoc_url=None,
    openapi_url=None if PRODUCTION else "/openapi.json",
)
app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_REQUEST_BYTES)


BACKEND_SHARED_SECRET = os.getenv("BACKEND_SHARED_SECRET", "")


@app.middleware("http")
async def require_shared_secret(request: Request, call_next):
    """
    When BACKEND_SHARED_SECRET is set, only our own frontend (which knows it) may use /api.
    Direct calls to a publicly reachable backend get 401, so nobody can run up the AI bill around the frontend.
    A valid caller may also pass the visitor's real address (X-Client-IP), which is used for rate limiting.
    """
    if BACKEND_SHARED_SECRET and request.url.path.startswith("/api"):
        supplied = request.headers.get("x-backend-secret", "")
        if not hmac.compare_digest(supplied.encode(), BACKEND_SHARED_SECRET.encode()):
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        forwarded = request.headers.get("x-client-ip", "").strip()
        try:
            request.state.client_ip = str(ipaddress.ip_address(forwarded)) if forwarded else None
        except ValueError:
            request.state.client_ip = None
    return await call_next(request)


@app.exception_handler(Exception)
async def unexpected_error(_request: Request, exc: Exception):
    logger.error("Unhandled error: %s", type(exc).__name__)  # class only: messages can echo user input
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our side. Try again in a moment."},
        headers={"X-Failure-Stage": "unknown"},
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Cache-Control", "no-store")
    return response

# CORS configuration
allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
env_origin = os.getenv("FRONTEND_URL")
if env_origin:
    allowed_origins.append(env_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

rate_limiter = InMemoryRateLimiter(requests_per_minute=25)


# Request Models
class IdeaInput(BaseModel):
    description: str = Field(max_length=4000)
    technologies_of_interest: Optional[List[str]] = Field(default_factory=list, max_length=20)

    @field_validator("technologies_of_interest")
    @classmethod
    def _short_tech_names(cls, v):
        return [t[:60] for t in (v or [])]


class ProjectManualInput(BaseModel):
    name: str = Field(default="Candidate Project", max_length=200)
    tagline: str = Field(default="", max_length=300)
    problem: str = Field(default="", max_length=3000)
    target_user: str = Field(default="", max_length=500)
    sponsor_requirements: str = Field(default="", max_length=3000)
    what_it_does: str = Field(default="", max_length=3000)
    how_it_works: str = Field(default="", max_length=3000)
    tech_tags: List[str] = Field(default_factory=list, max_length=30)


class AnalyzeRequest(BaseModel):
    analysis_mode: Optional[str] = None  # "idea" or "project"
    prize_targeting_mode: Optional[str] = "auto"  # "auto" ("Find the best fits for me") or "specific" ("Choose a specific prize")
    event_id: str = Field(default="shellhacks2025:2025", max_length=60, pattern=r"^[A-Za-z0-9:\-]+$")  # past results to compare against
    prize_event_id: Optional[str] = Field(default=None, max_length=60, pattern=r"^[A-Za-z0-9:\-]+$")  # where prizes come from; defaults to event_id
    award_id: str = Field(default="best_overall", max_length=120, pattern=r"^[A-Za-z0-9_\-\.: ]+$")
    idea: Optional[IdeaInput] = None
    input_mode: Optional[str] = "link"  # "link" or "manual"
    github_url: Optional[str] = Field(default=None, max_length=500)
    devpost_url: Optional[str] = Field(default=None, max_length=500)
    demo_url: Optional[str] = Field(default=None, max_length=500)
    deployment_url: Optional[str] = Field(default=None, max_length=500)
    sponsor_requirements: Optional[str] = Field(default=None, max_length=3000)
    project: Optional[ProjectManualInput] = None


@app.get("/health")
def health_check():
    """
    Health check verifying service availability and historical data presence
    without exposing credentials or private keys.
    """
    history_summary = Path("reports/shellhacks2025_2025/forensics_summary.json")
    chatgpt_active = bool(os.getenv("CHATGPT_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY"))
    return {
        "status": "healthy",
        "service": "hackbench-api",
        "version": "0.1.0",
        "jev_configured": bool(os.getenv("JEV_API_KEY")),
        "chatgpt_configured": chatgpt_active,
        "openai_configured": chatgpt_active,
        "gemini_configured": chatgpt_active,
        "historical_dataset_ready": history_summary.exists(),
        "timestamp": time.time(),
    }


@app.get("/api/events/{event_id}/prizes")
def get_event_prizes(event_id: str = FastPath(max_length=60, pattern=r"^[A-Za-z0-9:\-]+$")):
    """
    Returns documented prizes and tracks for an event with criteria completeness flags.
    """
    from ..ai.prize_matcher import PrizeMatcher
    matcher = PrizeMatcher()
    prizes = matcher.load_event_prizes(event_id)
    return {
        "event_id": event_id,
        "prizes": [
            {
                "prize_id": p.prize_id,
                "title": p.title,
                "prize_type": p.prize_type,
                "sponsor_name": p.sponsor_name,
                "description": p.description,
                "technologies_required_or_encouraged": p.technologies_required_or_encouraged,
                "has_sufficient_criteria": prize_has_criteria(p),
            }
            for p in prizes
        ],
    }


@app.post("/api/analyze")
def analyze_project(req: AnalyzeRequest, request: Request):
    """
    Main evaluation endpoint. Two modes:
    1. 'idea': pre-build guidance on clarity, gaps, what to build first, and prize fit.
    2. 'project': evidence-grounded review of a repository, demo and description.
    Admission control lives here; the work itself is in _analyze.
    """
    # Per-visitor rate limit
    client_ip = getattr(request.state, "client_ip", None) or client_ip_for(request, TRUST_PROXY_HEADERS)
    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please wait a minute before analyzing another project.",
        )
    # Whole-service protection: a daily cap (so the AI bill has a ceiling) and a cap on reviews running at once.
    if not _daily_budget.take():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HackBench has reached its review limit for today. Please try again tomorrow.",
            headers={"X-Failure-Stage": "unknown"},
        )
    if not _analysis_slots.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HackBench is busy right now. Try again in a minute.",
            headers={"X-Failure-Stage": "unknown"},
        )
    try:
        return _analyze(req)
    except HTTPException as e:
        if e.status_code == status.HTTP_400_BAD_REQUEST:
            _daily_budget.refund()  # rejected input did no paid work, so it must not eat the day's allowance
        raise
    finally:
        _analysis_slots.release()


def _analyze(req: AnalyzeRequest):

    # Determine mode:
    if req.analysis_mode == "project":
        is_idea = False
    elif req.analysis_mode == "idea":
        is_idea = True
    elif req.idea is not None:
        is_idea = True
    elif req.project is not None or req.github_url or req.devpost_url or req.deployment_url:
        is_idea = False
    else:
        # Default experience is idea mode
        is_idea = True

    if is_idea:
        # --- FLOW 1: REVIEW AN IDEA ---
        if not req.idea or not req.idea.description or not req.idea.description.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please provide an idea description under 'Tell us what you're thinking of building'.",
            )

        prize_event = req.prize_event_id or req.event_id
        req.idea.description = sanitize_untrusted_text(req.idea.description.strip(), max_chars=4000)
        from ..ai.idea_extractor import IdeaExtractor
        extractor = IdeaExtractor()
        extracted = extractor.extract(
            description=req.idea.description,
            technologies_of_interest=req.idea.technologies_of_interest,
        )

        # Deterministic Code Metrics: ALL not_evaluated
        deterministic_metrics = {
            "status": "not_evaluated",
            "approx_loc": 0,
            "primary_languages": [],
            "frontend_frameworks": [],
            "backend_frameworks": [],
            "databases": [],
            "model_providers": [],
            "test_files_count": 0,
            "api_routes_count": 0,
            "has_ci": False,
            "live_deployment_reachable": False,
            "deployment_url_status": "not_evaluated",
            "deployment_verification": "not_evaluated",
            "deployment_evidence": "Idea stage evaluation — implementation and deployment are not yet applicable.",
            "todo_fixme_count": 0,
        }

        # Prize Fit Engine: Evaluate idea against documented prizes and tracks
        from ..ai.prize_matcher import PrizeMatcher
        prize_matcher = PrizeMatcher()
        targeting_mode = req.prize_targeting_mode or "auto"
        if targeting_mode == "auto":
            prize_fit_result = prize_matcher.match_prizes(
                extracted=extracted,
                technologies_of_interest=req.idea.technologies_of_interest,
                event_id=prize_event,
            )
            if prize_fit_result.top_fits:
                primary_fit = prize_fit_result.top_fits[0]
                target_award_title = primary_fit.award_title
                award_criteria_text = ", ".join(primary_fit.documented_requirements) if primary_fit.documented_requirements else primary_fit.why_it_fits
                sponsor_req = primary_fit.sponsor_name or ""
            else:
                target_award_title = "Best Overall"
                award_criteria_text = "Overall innovation, practical execution feasibility, and distinct value proposition."
                sponsor_req = ""
        else:
            prize_fit_result = prize_matcher.evaluate_specific_prize(
                extracted=extracted,
                technologies_of_interest=req.idea.technologies_of_interest,
                event_id=prize_event,
                award_id=req.award_id,
            )
            if prize_fit_result.top_fits:
                primary_fit = prize_fit_result.top_fits[0]
                target_award_title = primary_fit.award_title
                award_criteria_text = ", ".join(primary_fit.documented_requirements) if primary_fit.documented_requirements else primary_fit.why_it_fits
                sponsor_req = primary_fit.sponsor_name or ""
            else:
                target_award_title = req.award_id.replace("_", " ").title()
                sponsor_technologies = extracted.likely_sponsor_technologies
                sponsor_req = ", ".join(sponsor_technologies) if sponsor_technologies else ""
                if sponsor_req:
                    award_criteria_text = f"Sponsor / API Focus: {sponsor_req}"
                else:
                    award_criteria_text = "Overall innovation, practical execution feasibility, and distinct value proposition."

        # Judge Surface Evaluation in Idea Mode
        router = EvaluationRouter()
        idea_name = extracted.proposed_product or "Candidate Hackathon Idea"
        judge_evals = router.evaluate_judge_surface(
            project_name=idea_name,
            tagline=extracted.user_outcome or extracted.core_workflow or "",
            problem=extracted.problem or req.idea.description,
            target_user=extracted.target_user or "Not specified",
            what_it_does=extracted.proposed_product or req.idea.description,
            how_it_works=extracted.core_workflow or "Workflow outlined in idea description.",
            demo_evidence="",
            award_criteria_text=award_criteria_text,
            has_video_demo=False,
            has_live_deployment=False,
            analysis_mode="idea",
        )
        idea_notes = _event_notes(req.event_id, prize_event)
        if _ai_unavailable(judge_evals):
            idea_notes.append("The AI reviewer is unavailable right now, so the dimension comparison is hidden. The guidance above is unaffected.")

        history, history_exact = load_history(req.event_id)
        historical_stats = _compute_historical_comparisons(judge_evals, history, analysis_mode="idea")
        historical_stats["takeaway"] = historical_takeaway(history)
        if history and not history_exact and is_known(req.event_id):
            idea_notes.append(f"History for that baseline is not available yet, so past-winner comparisons use {history['label']}.")

        synthesis_client = ChatGPTClient()
        synthesis_resp = synthesis_client.synthesize_report(
            project_name=idea_name,
            untrusted_evidence=req.idea.description,
            deterministic_metrics=deterministic_metrics,
            jev_classifications={k: v.model_dump() for k, v in judge_evals.items()},
            historical_comparisons=historical_stats,
            criteria_alignment={
                "award_title": target_award_title,
                "criteria": award_criteria_text,
                "prize_fits": [f.model_dump() for f in prize_fit_result.top_fits],
            },
            analysis_mode="idea",
            extracted_idea=extracted.model_dump(),
        )

        return {
            "analysis_id": f"an_{uuid.uuid4().hex[:12]}",
            "analysis_mode": "idea",
            "idea": {
                "description": req.idea.description,
                "technologies_of_interest": req.idea.technologies_of_interest or [],
                "extracted": extracted.model_dump(),
            },
            "extracted_idea": extracted.model_dump(),
            "prize_fits": prize_fit_result.model_dump(),
            "prize_event_id": prize_event,
            "project": {
                "name": idea_name,
                "tagline": extracted.user_outcome or extracted.core_workflow or "",
                "github_url": None,
                "devpost_url": None,
                "demo_url": None,
                "deployment_url": None,
                "tech_tags": extracted.intended_technologies,
            },
            "judge_surface": {k: v.model_dump() for k, v in judge_evals.items()},
            "historical_comparison": historical_stats,
            "criteria_alignment": {
                "target_award": target_award_title,
                "criteria_summary": award_criteria_text,
                "alignment_level": judge_evals.get("award_alignment", {}).label if "award_alignment" in judge_evals else "moderate",
                "sponsor_requirements": sponsor_req,
            },
            "recommendations": synthesis_resp.synthesis.model_dump(),
            "notes": idea_notes,
            "telemetry": _routing_telemetry(judge_evals, synthesis_resp.model, idea_notes, True),
            "disclaimer": (
                "HISTORICAL BENCHMARK NOTICE: This idea analysis evaluates your concept against historical "
                "distributions of past ShellHacks winners and strong non-winners before implementation begins. "
                "It is strictly NOT a prediction of future competition outcomes or winning probability."
            ),
        }

    # --- FLOW 2: REVIEW A PROJECT (PRESERVED) ---
    # 2. SSRF URL Validation
    notes: List[str] = _event_notes(req.event_id, req.prize_event_id or req.event_id)
    for url_field, attr in [
        ("GitHub URL", "github_url"),
        ("Devpost URL", "devpost_url"),
        ("Demo URL", "demo_url"),
        ("Deployment URL", "deployment_url"),
    ]:
        url_val = getattr(req, attr)
        if url_val:
            is_safe, msg = is_safe_public_url(url_val)
            if not is_safe and msg.startswith("Could not resolve hostname"):
                # A dead link is not an attack: skip it, say so, and review what remains.
                setattr(req, attr, None)
                notes.append(f"We couldn't reach the {url_field.replace(' URL', '').lower()} link, so it was skipped.")
            elif not is_safe:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Security rejection for {url_field}: {msg}",
                )

    if req.github_url and not is_allowed_repo_url(req.github_url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository links must be https links to GitHub, GitLab, or Bitbucket.",
        )
    if req.devpost_url and (urlparse(req.devpost_url).hostname or "").lower() not in ("devpost.com", "www.devpost.com"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Devpost links must point to devpost.com.")

    proj_in = req.project or ProjectManualInput()
    has_links = any([req.github_url, req.devpost_url, req.demo_url, req.deployment_url])
    has_text = any((getattr(proj_in, f) or "").strip() for f in ("tagline", "problem", "what_it_does", "how_it_works"))
    if not has_links and not has_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add a GitHub, Devpost, or demo link, or describe your project, and try again.",
        )

    # 3. Normalize Inputs & Extract Evidence
    proj = req.project or ProjectManualInput()
    name = "" if (proj.name or "").strip() in ("", "Candidate Project") else sanitize_untrusted_text(proj.name)
    tagline = sanitize_untrusted_text(proj.tagline)
    problem = sanitize_untrusted_text(proj.problem)
    target_user = sanitize_untrusted_text(proj.target_user)
    what_it_does = sanitize_untrusted_text(proj.what_it_does)
    how_it_works = sanitize_untrusted_text(proj.how_it_works)
    tech_tags = [sanitize_untrusted_text(t) for t in proj.tech_tags]

    # Attempt to extract from Devpost if provided
    if req.devpost_url:
        try:
            client = CachedHttpClient(safe_mode=True)
            collector = DevpostCollector(client)
            devpost_details = collector.fetch_project_details(req.devpost_url, "candidate", {})
            name = name or sanitize_untrusted_text(devpost_details.title)
            tagline = tagline or devpost_details.tagline
            problem = problem or devpost_details.description_sections.problem_statement
            secs = devpost_details.description_sections
            what_it_does = what_it_does or secs.what_it_does or (secs.raw_full_text or "")[:1500]
            how_it_works = how_it_works or devpost_details.description_sections.how_it_was_built
            tech_tags = tech_tags or devpost_details.tech_tags
            if not req.github_url and devpost_details.github_urls:
                req.github_url = devpost_details.github_urls[0]
            if not req.demo_url and devpost_details.demo_urls:
                req.demo_url = devpost_details.demo_urls[0]
        except Exception as e:
            logger.warning("Could not scrape Devpost link: %s. Proceeding with manual fields.", str(e)[:120])
            notes.append("We couldn't read the Devpost page, so its description was not used.")

    if not name and req.github_url:
        name = _project_name_from_repo_url(req.github_url)
    name = name or "Candidate Project"

    # 4. Deterministic Code Analysis (Layer 1)
    readme_excerpt = ""
    deterministic_metrics: Dict[str, Any] = {
        "status": "no_repo_provided",
        "approx_loc": 0,
        "primary_languages": [],
        "frontend_frameworks": [],
        "backend_frameworks": [],
        "databases": [],
        "model_providers": [],
        "test_files_count": 0,
        "api_routes_count": 0,
        "has_ci": False,
        "live_deployment_reachable": False,
        "deployment_url_status": "none",
        "deployment_verification": "none",
        "deployment_evidence": "No deployment URL provided.",
        "todo_fixme_count": 0,
    }

    temp_dir = PARTICIPANT_REPOS_DIR
    temp_dir.mkdir(parents=True, exist_ok=True)
    # Strangers' repositories: bounded file count, bytes read per file, and total analysis time.
    analyzer = RepositoryAnalyzer(temp_dir, max_files=MAX_REPO_FILES, max_read_bytes=MAX_REPO_READ_BYTES, budget_seconds=REPO_ANALYSIS_SECONDS)

    if req.github_url:
        if not _clone_slots.acquire(blocking=False):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The service is busy reviewing other projects. Try again in a minute.",
                headers={"X-Failure-Stage": "repo_analysis"},
            )
        clone_id = f"part_{uuid.uuid4().hex[:8]}"
        try:
            repo_m = analyzer.analyze_repository(
                repo_url=req.github_url,
                project_id=clone_id,
                claimed_tech_tags=tech_tags,
                deployment_url=req.deployment_url,
                project_name=name,
            )
            dep = repo_m.deployment_check
            readme_excerpt = repo_m.readme_excerpt or ""
            if analyzer.analysis_truncated:
                notes.append("This repository is very large, so only part of it was analyzed. Code counts are partial.")
            deterministic_metrics = {
                "status": repo_m.status,
                "approx_loc": repo_m.approx_loc,
                "primary_languages": repo_m.primary_languages,
                "frontend_frameworks": repo_m.tech_stack.frontend_frameworks,
                "backend_frameworks": repo_m.tech_stack.backend_frameworks,
                "databases": repo_m.tech_stack.databases,
                "model_providers": repo_m.tech_stack.model_providers,
                "test_files_count": repo_m.test_files_count,
                "api_routes_count": repo_m.api_routes_count,
                "has_ci": repo_m.has_ci,
                "live_deployment_reachable": dep.is_reachable if dep else False,
                "deployment_url_status": dep.deployment_url_status if dep else "none",
                "deployment_verification": dep.deployment_verification if dep else "none",
                "deployment_evidence": dep.verification_evidence if dep else "No deployment URL provided.",
                "todo_fixme_count": repo_m.todo_fixme_count,
            }
        except Exception as e:
            logger.warning("Failed to analyze repository: %s", str(e)[:120])
            deterministic_metrics["status"] = f"error: {str(e)[:40]}"
            notes.append("We couldn't read the GitHub repository, so code was not reviewed.")
        finally:
            # Everything needed was extracted; never keep a participant's code on disk.
            shutil.rmtree(temp_dir / clone_id, ignore_errors=True)
            _clone_slots.release()
        if deterministic_metrics.get("status") == "repo_too_large":
            notes.append("That repository is too large to review here, so code was not reviewed.")
        elif deterministic_metrics.get("status") not in ("accessible", "no_repo_provided") and not any(
            "GitHub repository" in n for n in notes
        ):
            notes.append("We couldn't read the GitHub repository (it may be private or the link is wrong), so code was not reviewed.")
    elif req.deployment_url:
        try:
            dep = analyzer.check_deployment(req.deployment_url, project_name=name)
            deterministic_metrics["live_deployment_reachable"] = dep.is_reachable
            deterministic_metrics["deployment_url_status"] = dep.deployment_url_status
            deterministic_metrics["deployment_verification"] = dep.deployment_verification
            deterministic_metrics["deployment_evidence"] = dep.verification_evidence or ""
        except Exception as e:
            logger.warning("Failed to check deployment: %s", str(e)[:120])

    # Link-only submissions: fall back to the repository README as the description.
    text_from_readme = False
    if not any([problem, target_user, what_it_does, how_it_works, tagline]) and deterministic_metrics.get("status") == "accessible":
        if len(readme_excerpt) >= 120:
            first_line = readme_excerpt.splitlines()[0].lstrip("# ").strip()
            tagline = sanitize_untrusted_text(first_line[:160])
            what_it_does = sanitize_untrusted_text(readme_excerpt)
            text_from_readme = True
            notes.append("This project had no description, so the review uses the repository README. Add a one-line description for a sharper review.")
        else:
            notes.append("The repository has no README to read. Add one sentence about what the project does and run the review again for judge-facing ratings.")

    # 5. Judge Surface Evaluation (Layer 2 & Layer 3 via Router)
    router = EvaluationRouter()
    demo_evidence = f"Video: {req.demo_url}" if req.demo_url else ("Live URL: " + req.deployment_url if req.deployment_url else "")
    
    sponsor_req = sanitize_untrusted_text(proj.sponsor_requirements or req.sponsor_requirements or "")

    # The prize the user picked is judged on its own published description, not a generic line.
    prize_event = req.prize_event_id or req.event_id
    prize_fit_result, target_prize = _project_prize_fit(
        prize_event, req.award_id, name, tagline, problem, target_user, what_it_does, how_it_works, tech_tags,
    )
    if target_prize is not None and prize_has_criteria(target_prize):
        award_criteria_text = f"{target_prize.title}: {target_prize.description}"[:1500]
        if sponsor_req:
            award_criteria_text += f"\nAdditional requirements entered by the user: {sponsor_req}"
    elif sponsor_req:
        award_criteria_text = f"Sponsor & Track Requirements: {sponsor_req}"
    else:
        award_criteria_text = "Overall excellence in innovation, technical depth, design, and practical utility."
    target_award_title = target_prize.title if target_prize is not None else req.award_id.replace("_", " ").title()
    target_fit = prize_fit_result.top_fits[0] if prize_fit_result and prize_fit_result.top_fits else None

    judge_evals = router.evaluate_judge_surface(
        project_name=name,
        tagline=tagline,
        problem=problem,
        target_user=target_user,
        what_it_does=what_it_does,
        how_it_works=how_it_works,
        demo_evidence=demo_evidence,
        award_criteria_text=award_criteria_text,
        has_video_demo=bool(req.demo_url),
        has_live_deployment=bool(req.deployment_url),
        has_repository=deterministic_metrics.get("status") == "accessible",
        text_from_readme=text_from_readme,
    )

    if _ai_unavailable(judge_evals):
        notes.append("The AI reviewer is unavailable right now, so ratings use a simpler built-in check and are less precise.")

    # 6. Load Historical Winner & Non-Winner Distributions
    history, history_exact = load_history(req.event_id)
    historical_stats = _compute_historical_comparisons(judge_evals, history)
    if history and not history_exact and is_known(req.event_id):
        notes.append(f"History for that baseline is not available yet, so past-winner comparisons use {history['label']}.")

    # 7. ChatGPT Synthesis (Layer 3)
    synthesis_client = ChatGPTClient()
    untrusted_evidence_block = (
        f"Title: {name}\nTagline: {tagline}\nProblem: {problem}\nUser: {target_user}\n"
        f"Target Award: {target_award_title}\nSponsor / Track Requirements: {sponsor_req}\n"
        f"What: {what_it_does}\nHow: {how_it_works}\nCode LOC: {deterministic_metrics.get('approx_loc')}\n"
        f"Frameworks: {deterministic_metrics.get('frontend_frameworks') + deterministic_metrics.get('backend_frameworks')}"
    )
    if text_from_readme:
        untrusted_evidence_block += (
            "\nNote: nothing was submitted except the repository, so the description above is the README. "
            "Blank Problem, User and Tagline fields are not gaps in the project."
        )

    synthesis_resp = synthesis_client.synthesize_report(
        project_name=name,
        untrusted_evidence=untrusted_evidence_block,
        deterministic_metrics=deterministic_metrics,
        jev_classifications={k: v.model_dump() for k, v in judge_evals.items()},
        historical_comparisons=historical_stats,
        criteria_alignment={
            "award_title": target_award_title,
            "criteria": award_criteria_text,
            "prize_fit": _fit_summary_for_model(target_fit, prize_fit_result),
        },
    )

    return {
        "analysis_id": f"an_{uuid.uuid4().hex[:12]}",
        "analysis_mode": "project",
        "project": {
            "name": name,
            "tagline": tagline,
            "github_url": req.github_url,
            "devpost_url": req.devpost_url,
            "demo_url": req.demo_url,
            "deployment_url": req.deployment_url,
            "tech_tags": tech_tags,
        },
        "judge_surface": {k: v.model_dump() for k, v in judge_evals.items()},
        "engineering": deterministic_metrics,
        "historical_comparison": historical_stats,
        "prize_fits": prize_fit_result.model_dump() if prize_fit_result else None,
        "prize_event_id": prize_event,
        "criteria_alignment": {
            "target_award": target_award_title,
            "criteria_summary": (target_prize.description[:500] if target_prize is not None and prize_has_criteria(target_prize) else award_criteria_text),
            "alignment_level": (target_fit.fit_level.value if target_fit else (judge_evals["award_alignment"].label if "award_alignment" in judge_evals else "moderate")),
            "sponsor_requirements": (target_prize.sponsor_name if target_prize is not None and target_prize.sponsor_name else sponsor_req) or "",
        },
        "recommendations": synthesis_resp.synthesis.model_dump(),
        "notes": notes,
        "telemetry": _routing_telemetry(judge_evals, synthesis_resp.model, notes, False),
        "disclaimer": (
            "HISTORICAL BENCHMARK NOTICE: This analysis compares public submission evidence against historical "
            "distributions of past ShellHacks winners and strong non-winners. It is strictly NOT a prediction of "
            "future competition outcomes or winning probability."
        ),
    }


def _routing_telemetry(judge_evals: Dict[str, Any], synthesis_model: str, notes: List[str], is_idea: bool) -> Dict[str, Any]:
    """
    Safe, low-cardinality facts about how a review was produced, for product analytics.
    Booleans and one enum only: no provider names beyond these flags, no errors, no prompt or output content.
    `gemini_used` is the name analytics uses for the second AI provider; in this deployment that is ChatGPT.
    """
    values = list(judge_evals.values())
    providers = {getattr(v, "provider", "") for v in values}
    synthesis_local = synthesis_model == "chatgpt-local-calibrated"
    gated_fallback = any(
        getattr(v, "provider", "") == "chatgpt" and getattr(v, "fallback_reason", None) not in (None, "jev_key_not_configured")
        for v in values
    )
    fallback_used = "offline_calibrated" in providers or synthesis_local or gated_fallback
    has_gap = (not is_idea) and any(getattr(v, "label", "") == "insufficient_evidence" for v in values)
    return {
        "jev_used": "jev" in providers,
        "gemini_used": "chatgpt" in providers or not synthesis_local,
        "fallback_used": bool(fallback_used),
        "result_quality": "partial" if (notes or fallback_used or has_gap) else "full",
    }


def _ai_unavailable(judge_evals: Dict[str, Any]) -> bool:
    return any(getattr(v, "provider", "") == "offline_calibrated" for v in judge_evals.values())


def _project_name_from_repo_url(url: str) -> str:
    """'https://github.com/owner/Claude-Sentinel/tree/main' -> 'Claude Sentinel'."""
    parts = [p for p in urlparse(url).path.split("/") if p]
    slug = parts[1] if len(parts) >= 2 else (parts[0] if parts else "")
    slug = re.sub(r"\.git$", "", slug)
    return sanitize_untrusted_text(re.sub(r"[-_]+", " ", slug).strip())[:80]


def _project_prize_fit(prize_event, award_id, name, tagline, problem, target_user, what_it_does, how_it_works, tech_tags):
    """
    Evaluate the project against the challenge it targeted, using that challenge's published description,
    and add up to two strictly closer documented fits when the chosen one is a poor match.
    Returns (PrizeFitResult | None, PrizeCategory | None). Never raises: a review must not fail over prize data.
    """
    try:
        matcher = PrizeMatcher()
        prizes = matcher.load_event_prizes(prize_event)
        target = matcher.find_prize(prizes, award_id)
        if target is None:
            return None, None
        text = "\n".join(t for t in (name, tagline, problem, target_user, what_it_does, how_it_works) if t)[:4000]
        idea = IdeaExtractor().extract_offline(text, tech_tags)
        chosen = matcher.evaluate_specific_prize(idea, tech_tags, prize_event, target.prize_id)
        target_fit = chosen.top_fits[0]

        order = {"very_strong": 5, "strong": 4, "moderate": 3, "weak": 2, "very_weak": 1}
        level = lambda f: order.get(f.fit_level.value, 0)
        alternatives = [
            f for f in matcher.match_prizes(idea, tech_tags, event_id=prize_event).top_fits
            if f.prize_id != target.prize_id and level(f) >= 3 and level(f) > level(target_fit)
        ][:2]
        summary = f"Evaluated directly against {target.title}."
        if alternatives:
            summary += " Closer documented fits: " + ", ".join(f.award_title for f in alternatives) + "."
        return PrizeFitResult(
            targeting_mode="specific", top_fits=[target_fit] + alternatives, evaluated_count=1 + len(alternatives),
            insufficient_criteria_count=0, summary=summary,
        ), target
    except Exception as e:  # noqa: BLE001
        logger.warning("Project prize-fit failed: %s", type(e).__name__)
        return None, None


def _fit_summary_for_model(target_fit, result) -> Optional[Dict[str, Any]]:
    """The facts the model needs to judge alignment honestly, without any user text."""
    if target_fit is None:
        return None
    return {
        "fit_level": target_fit.fit_level.value,
        "why_it_fits": target_fit.why_it_fits,
        "why_it_may_not_fit": target_fit.why_it_may_not_fit,
        "biggest_missing_requirement": target_fit.biggest_missing_requirement,
        "must_demonstrate": target_fit.what_must_be_demonstrated,
        "closer_fits": [f.award_title for f in (result.top_fits[1:] if result else [])],
    }


def _event_notes(event_id: str, prize_event_id: Optional[str] = None) -> List[str]:
    """Say so when a chosen year is unknown and something else was used instead."""
    notes: List[str] = []
    if not is_known(event_id):
        notes.append(f"We have no data for “{event_id}”, so past-winner comparisons use {label_for(DEFAULT_BASELINE)}.")
    prize_event_id = prize_event_id or event_id
    if not is_known_prize_event(prize_event_id):
        notes.append(f"We have no prizes for “{prize_event_id}”, so prizes come from {label_for(DEFAULT_BASELINE)}.")
    return notes


def _compute_historical_comparisons(
    current_evals: Dict[str, Any],
    history: Optional[Dict[str, Any]],
    analysis_mode: str = "project",
) -> Dict[str, Any]:
    """
    Cohort comparisons for the chosen baseline (one year, or every year pooled), with explicit sample sizes.
    `history` comes from baselines.load_history. With no history at all, every dimension says so.
    """
    counts = (history or {}).get("counts", {"total_analyzed": 0, "winners": 0, "strong_non_winners": 0})
    label = (history or {}).get("label", "")
    cc = (history or {}).get("cohort_comparisons", {})
    report_rows: Dict[str, Dict[str, Any]] = {r["dimension_or_feature"]: r for r in cc.get("winners_vs_nonwinners", [])}
    strong_rows: Dict[str, Dict[str, Any]] = {r["dimension_or_feature"]: r for r in cc.get("winners_vs_strong_nonwinners", [])}

    total_analyzed = counts["total_analyzed"]
    winners_count = counts["winners"]
    snw_count = counts["strong_non_winners"]
    non_winners_count = max(0, total_analyzed - winners_count)
    cohort_desc = (
        f"{label}: {total_analyzed} analyzed projects, {winners_count} award-winning and "
        f"{non_winners_count} non-winning, including {snw_count} strong non-winners."
        if history else "No historical data is available for this baseline."
    )

    def _pct(row_key: str) -> Optional[Dict[str, Any]]:
        row = report_rows.get(row_key)
        if row and row.get("mean_a") is not None and row.get("mean_b") is not None:
            return row
        return None

    dep, tst = _pct("has_live_deployment"), _pct("has_tests")
    facts: Dict[str, str] = {}
    if dep:
        facts["deployment"] = (
            f"In {label} (n={dep['sample_a']} winners, {dep['sample_b']} non-winners), "
            f"{dep['mean_a']:.0%} of winners and {dep['mean_b']:.0%} of non-winners had a live deployment."
        )
    if tst:
        facts["tests"] = (
            f"In {label} (n={tst['sample_a']} winners, {tst['sample_b']} non-winners), "
            f"{tst['mean_a']:.0%} of winners and {tst['mean_b']:.0%} of non-winners had tests."
        )

    comparisons = {
        "baseline_label": label,
        "sample_sizes": {
            "historical_winners": winners_count,
            "non_winners": non_winners_count,
            "strong_non_winners": snw_count,
            "total_analyzed": total_analyzed,
            "cohort_description": cohort_desc,
        },
        "facts": facts,
        "dimensions": {},
    }

    # Only dimensions that the historical report actually measured get a number; the rest say so.
    report_dim = {
        "problem_clarity": "problem_clarity",
        "product_clarity": "product_coherence",
        "originality": "originality",
        "demo_strength": "demo_strength",
        "completion_appearance": "completion",
    }
    all_dims = [
        "problem_clarity", "user_clarity", "product_clarity", "originality", "scope_clarity", "story_clarity",
        "practicality", "potential_demo_clarity", "award_alignment", "demo_strength", "completion_appearance",
        "memorability",
    ]
    cohort_benchmarks: Dict[str, Any] = {}
    for dim in all_dims:
        row = report_rows.get(report_dim.get(dim, ""))
        srow = strong_rows.get(report_dim.get(dim, ""))
        if row and row.get("mean_a") is not None and row.get("mean_b") is not None:
            cohort_benchmarks[dim] = (
                f"avg {row['mean_a']:.1f} of 5 (n={row['sample_a']})",
                f"avg {srow['mean_b']:.1f} of 5 (n={srow['sample_b']})" if srow else "No historical data",
                float(row["mean_a"]),
            )
        else:
            cohort_benchmarks[dim] = ("No historical data", "No historical data", None)

    for dim, (win_stat, snw_stat, win_mean) in cohort_benchmarks.items():
        if analysis_mode == "idea" and dim in ("completion_appearance", "demo_strength"):
            comparisons["dimensions"][dim] = {
                "you": "Not evaluated (idea stage)",
                "historical_overall_winners": win_stat,
                "strong_non_winners": snw_stat,
                "interpretation": "Completion and live demo proofs are evaluated after software is built.",
            }
            continue

        if dim not in current_evals and analysis_mode == "project" and dim in ("scope_clarity", "potential_demo_clarity", "originality"):
            continue

        curr_eval = current_evals.get(dim)
        curr_label = curr_eval.label if curr_eval else "moderate"
        if curr_label == "not_evaluated":
            interp = "Not evaluated at this stage."
            display_you = "Not evaluated"
        elif curr_label == "insufficient_evidence":
            interp = "Not enough submitted evidence to compare."
            display_you = "Insufficient evidence"
        else:
            display_you = curr_label.replace("_", " ").title()
            if win_mean is None:
                interp = "The historical data does not measure this dimension."
            elif SCORE_LEVEL_VALUES.get(curr_label, 3.0) >= win_mean:
                interp = "At or above the average for past winners."
            else:
                interp = "Below the average for past winners."

        comparisons["dimensions"][dim] = {
            "you": display_you,
            "historical_overall_winners": win_stat,
            "strong_non_winners": snw_stat,
            "interpretation": interp,
        }

    return comparisons
