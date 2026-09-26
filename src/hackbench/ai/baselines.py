"""
Baselines: which hackathon year(s) a review is compared against.

A baseline is one ShellHacks year ("shellhacks2024:2024") or every year pooled ("all:combined").
Both the prize list and the historical comparison come from that baseline, so a review is
specific to the year you pick. Nothing here invents data: a year without prizes or a history
report is reported as unavailable so callers can say so.
"""
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..models.event import HackathonEvent, PrizeCategory

logger = logging.getLogger("hackbench.ai.baselines")

ALL_YEARS_ID = "all:combined"
DEFAULT_BASELINE = "shellhacks2025:2025"
# The current hackathon: its prizes are known, but it has no results yet, so it is a prize source only,
# never a historical baseline.
CURRENT_EVENT_ID = "shellhacks2026:2026"

# Newest first. This is the single list the UI, prize matching and history all agree on.
YEAR_BASELINES: List[Tuple[str, str]] = [
    ("shellhacks2025:2025", "ShellHacks 2025"),
    ("shellhacks2024:2024", "ShellHacks 2024"),
    ("shellhacks-2023:2023", "ShellHacks 2023"),
]
KNOWN_BASELINE_IDS = [ALL_YEARS_ID] + [b for b, _ in YEAR_BASELINES]
# Where prizes can come from: this year's challenges, any past year, or every past year combined.
KNOWN_PRIZE_EVENT_IDS = [CURRENT_EVENT_ID, ALL_YEARS_ID] + [b for b, _ in YEAR_BASELINES]


def is_known(event_id: str) -> bool:
    return event_id in KNOWN_BASELINE_IDS


def is_known_prize_event(event_id: str) -> bool:
    return event_id in KNOWN_PRIZE_EVENT_IDS


def label_for(event_id: str) -> str:
    if event_id == CURRENT_EVENT_ID:
        return "ShellHacks 2026"
    if event_id == ALL_YEARS_ID:
        years = sorted(int(b.split(":")[1]) for b, _ in YEAR_BASELINES)
        return f"ShellHacks {years[0]}–{years[-1]}"
    return dict(YEAR_BASELINES).get(event_id, event_id)


_EVENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,39}:[0-9]{4}$")


def is_valid_event_id(event_id: object) -> bool:
    """Shape check applied before any id is used in a file path. Anything else is treated as unknown."""
    return isinstance(event_id, str) and bool(_EVENT_ID_RE.match(event_id)) or event_id == ALL_YEARS_ID


def _split(event_id: str) -> Tuple[str, str]:
    if not is_valid_event_id(event_id) or event_id == ALL_YEARS_ID:
        return DEFAULT_BASELINE.split(":")[0], DEFAULT_BASELINE.split(":")[1]
    slug, year = event_id.split(":")
    return slug, year


def _metadata_path(event_id: str) -> Path:
    slug, year = _split(event_id)
    return Path(f"data/raw/{slug}/{year}/event/event_metadata.json")


def _summary_path(event_id: str) -> Path:
    slug, year = _split(event_id)
    return Path(f"reports/{slug}_{year}/forensics_summary.json")


def _read_prizes(event_id: str) -> List[PrizeCategory]:
    path = _metadata_path(event_id)
    if not path.exists():
        return []
    try:
        return HackathonEvent.model_validate(json.loads(path.read_text(encoding="utf-8"))).prize_categories
    except Exception as e:
        logger.error("Failed to load event metadata for %s: %s", event_id, type(e).__name__)
        return []


def prize_has_criteria(prize: PrizeCategory) -> bool:
    """
    True only when the description states something a project could be judged against.
    A title, a swag item ("Prize: JBL Headphones"), or a slogan is not criteria.
    """
    if prize.technologies_required_or_encouraged:
        return True
    if prize.prize_type == "overall":
        return True  # judged on the general dimensions every review already covers, not on a stated rule
    text = re.sub(r"\*+|_{2,}", " ", prize.description or "")
    text = re.sub(r"(?im)^\s*prize:.*$", " ", text)
    return len(re.findall(r"[A-Za-z][A-Za-z'’\-]*", text)) >= 12


def _normalize_title(title: str) -> str:
    t = re.sub(r"\[[^\]]*\]|\|\|.*$", " ", title.lower())
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def combined_prizes() -> List[PrizeCategory]:
    """
    Union of every year's prizes. Overall prizes come from the newest year only; other prizes are
    de-duplicated by title, keeping the newest year's version.
    """
    merged: List[PrizeCategory] = []
    seen_titles = set()
    overall_year_taken = False
    for event_id, _ in YEAR_BASELINES:  # newest first
        year_prizes = _read_prizes(event_id)
        year_has_overall = any(p.prize_type == "overall" for p in year_prizes)
        for p in year_prizes:
            if p.prize_type == "overall":
                if overall_year_taken:
                    continue
            else:
                key = _normalize_title(p.title)
                if key in seen_titles:
                    continue
                seen_titles.add(key)
            merged.append(p)
        if year_has_overall:
            overall_year_taken = True
    return merged


def load_prizes(event_id: str) -> Tuple[List[PrizeCategory], bool]:
    """Returns (prizes, exact). exact is False when we had to fall back to the default year."""
    if event_id == ALL_YEARS_ID:
        return combined_prizes(), True
    prizes = _read_prizes(event_id)
    if prizes:
        return prizes, True
    return _read_prizes(DEFAULT_BASELINE), False


def _pool_rows(per_year: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Sample-size-weighted pooling of per-year cohort rows. Effect sizes are dropped: they cannot be pooled."""
    by_dim: Dict[str, List[Dict[str, Any]]] = {}
    for rows in per_year:
        for r in rows:
            by_dim.setdefault(r["dimension_or_feature"], []).append(r)
    pooled = []
    for dim, rows in by_dim.items():
        def weighted(mean_key: str, n_key: str):
            usable = [r for r in rows if r.get(mean_key) is not None and r.get(n_key)]
            n = sum(r[n_key] for r in usable)
            return (sum(r[mean_key] * r[n_key] for r in usable) / n if n else None), n
        mean_a, n_a = weighted("mean_a", "sample_a")
        mean_b, n_b = weighted("mean_b", "sample_b")
        interps = {r.get("interpretation") for r in rows}
        pooled.append({
            "dimension_or_feature": dim,
            "group_a_name": rows[0].get("group_a_name"),
            "group_b_name": rows[0].get("group_b_name"),
            "mean_a": round(mean_a, 3) if mean_a is not None else None,
            "mean_b": round(mean_b, 3) if mean_b is not None else None,
            "sample_a": n_a,
            "sample_b": n_b,
            # Only claim a pattern if every year agrees on it.
            "interpretation": interps.pop() if len(interps) == 1 else "Mixed across years",
        })
    return pooled


def _year_counts(data: Dict[str, Any]) -> Dict[str, int]:
    recs = data.get("project_records", [])
    return {
        "total_analyzed": len(recs),
        "winners": sum(1 for r in recs if r.get("outcome", {}).get("is_winner")),
        "strong_non_winners": len(data.get("strong_non_winners", [])),
    }


def load_history(event_id: str) -> Tuple[Optional[Dict[str, Any]], bool]:
    """
    Returns (history, exact). history has: label, counts, cohort_comparisons
    (winners_vs_nonwinners, winners_vs_strong_nonwinners), years.
    exact is False when the requested baseline had no report and the default year was used.
    """
    def read(eid: str) -> Optional[Dict[str, Any]]:
        p = _summary_path(eid)
        try:
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
        except Exception:
            return None

    if event_id == ALL_YEARS_ID:
        loaded = [(eid, read(eid)) for eid, _ in YEAR_BASELINES]
        loaded = [(eid, d) for eid, d in loaded if d]
        if not loaded:
            return None, False
        counts = {k: 0 for k in ("total_analyzed", "winners", "strong_non_winners")}
        for _, d in loaded:
            for k, v in _year_counts(d).items():
                counts[k] += v
        comps = {
            key: _pool_rows([d.get("cohort_comparisons", {}).get(key, []) for _, d in loaded])
            for key in ("winners_vs_nonwinners", "winners_vs_strong_nonwinners")
        }
        return {
            "label": label_for(ALL_YEARS_ID),
            "counts": counts,
            "cohort_comparisons": comps,
            "years": [eid.split(":")[1] for eid, _ in loaded],
        }, len(loaded) == len(YEAR_BASELINES)

    data = read(event_id)
    exact = data is not None
    if data is None:
        data = read(DEFAULT_BASELINE)
        event_id = DEFAULT_BASELINE
    if data is None:
        return None, False
    return {
        "label": label_for(event_id),
        "counts": _year_counts(data),
        "cohort_comparisons": {
            k: data.get("cohort_comparisons", {}).get(k, [])
            for k in ("winners_vs_nonwinners", "winners_vs_strong_nonwinners")
        },
        "years": [event_id.split(":")[1]],
    }, exact
