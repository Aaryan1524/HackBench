"""The comparison baseline: one specific year, or every year pooled. Nothing falls back silently."""
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hackbench.ai.baselines import (
    ALL_YEARS_ID, DEFAULT_BASELINE, KNOWN_BASELINE_IDS, YEAR_BASELINES, _pool_rows, combined_prizes,
    label_for, load_history, load_prizes, prize_has_criteria,
)
from hackbench.ai.idea_extractor import IdeaExtractor
from hackbench.ai.prize_matcher import PrizeMatcher
from hackbench.api import server
from hackbench.models.event import PrizeCategory

FRAUD = ("We're building an agent that watches a small business's Stripe transactions, flags likely fraud in real time, "
         "and texts the owner a one-tap approve/decline. Built for corner-store owners who can't afford a fraud team.")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key in ("CHATGPT_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "JEV_API_KEY"):
        monkeypatch.setenv(key, "")


@pytest.fixture
def client():
    server.rate_limiter.requests.clear()
    return TestClient(server.app)


def analyze(client, event_id, description=FRAUD):
    r = client.post("/api/analyze", json={"analysis_mode": "idea", "event_id": event_id,
                                          "idea": {"description": description, "technologies_of_interest": ["Stripe"]}})
    assert r.status_code == 200
    return r.json()


# ---------- the list of baselines ----------

def test_baselines_are_the_three_real_years_plus_combined():
    assert KNOWN_BASELINE_IDS == [ALL_YEARS_ID, "shellhacks2025:2025", "shellhacks2024:2024", "shellhacks-2023:2023"]
    assert not any("2026" in b for b in KNOWN_BASELINE_IDS)


def test_ui_offers_exactly_these_baselines_and_2026_only_as_a_prize_source():
    src = Path("web/app/page.tsx").read_text()
    baselines_block = src[src.index("const BASELINE_OPTIONS"):src.index("// Where the prizes you are matched")]
    for baseline_id in KNOWN_BASELINE_IDS:
        assert f'"{baseline_id}"' in baselines_block, baseline_id
    assert "2026" not in baselines_block  # no results yet, so it is not a comparison baseline
    assert '"shellhacks2026:2026"' in src[src.index("const PRIZE_EVENT_OPTIONS"):]
    assert "All years combined" in src


def test_labels():
    assert label_for("shellhacks2024:2024") == "ShellHacks 2024"
    assert label_for(ALL_YEARS_ID) == "ShellHacks 2023–2025"


# ---------- history is specific to the year ----------

@pytest.mark.parametrize("event_id, label", [(b, l) for b, l in YEAR_BASELINES])
def test_each_year_has_its_own_history(event_id, label):
    history, exact = load_history(event_id)
    assert exact is True and history["label"] == label
    counts = history["counts"]
    assert counts["total_analyzed"] > 100 and 0 < counts["winners"] < counts["total_analyzed"]
    assert history["years"] == [event_id.split(":")[1]]


def test_years_have_different_data():
    sizes = {b: load_history(b)[0]["counts"]["total_analyzed"] for b, _ in YEAR_BASELINES}
    assert len(set(sizes.values())) == 3, sizes


def test_combined_history_is_the_sum_of_the_years():
    combined, exact = load_history(ALL_YEARS_ID)
    assert exact is True and combined["years"] == ["2025", "2024", "2023"]
    for key in ("total_analyzed", "winners", "strong_non_winners"):
        assert combined["counts"][key] == sum(load_history(b)[0]["counts"][key] for b, _ in YEAR_BASELINES)


def test_pooling_is_weighted_by_sample_size_and_only_claims_agreed_patterns():
    year_a = [{"dimension_or_feature": "x", "mean_a": 2.0, "mean_b": 1.0, "sample_a": 10, "sample_b": 100, "interpretation": "Negligible difference"}]
    year_b = [{"dimension_or_feature": "x", "mean_a": 4.0, "mean_b": 3.0, "sample_a": 30, "sample_b": 100, "interpretation": "Negligible difference"}]
    row = _pool_rows([year_a, year_b])[0]
    assert row["mean_a"] == pytest.approx(3.5) and row["mean_b"] == pytest.approx(2.0)
    assert (row["sample_a"], row["sample_b"]) == (40, 200)
    assert row["interpretation"] == "Negligible difference"
    year_b[0]["interpretation"] = "Small effect size (higher in Winners)"
    assert _pool_rows([year_a, year_b])[0]["interpretation"] == "Mixed across years"


def test_unknown_baseline_falls_back_and_says_so(client):
    r = analyze(client, "shellhacks2026:2026")
    assert any("shellhacks2026:2026" in n and "no data" in n.lower() for n in r["notes"])
    assert r["historical_comparison"]["baseline_label"] == "ShellHacks 2025"


@pytest.mark.parametrize("event_id, label", [(b, l) for b, l in YEAR_BASELINES] + [(ALL_YEARS_ID, "ShellHacks 2023–2025")])
def test_api_reports_the_chosen_baseline_with_no_fallback_note(client, event_id, label):
    r = analyze(client, event_id)
    hc = r["historical_comparison"]
    assert hc["baseline_label"] == label
    assert hc["sample_sizes"]["total_analyzed"] == load_history(event_id)[0]["counts"]["total_analyzed"]
    assert label in hc["sample_sizes"]["cohort_description"]
    assert r["notes"] == [] or all("every year" not in n and "no data" not in n.lower() for n in r["notes"])


def test_takeaway_and_facts_cite_the_chosen_year(client):
    r = analyze(client, "shellhacks2024:2024")
    text = (r["historical_comparison"].get("takeaway") or "") + " ".join(r["historical_comparison"]["facts"].values())
    assert "ShellHacks 2024" in text and "ShellHacks 2025" not in text


def test_project_advice_cites_the_chosen_year_not_2025(client):
    r = client.post("/api/analyze", json={"analysis_mode": "project", "event_id": "shellhacks2024:2024", "input_mode": "manual",
                                          "project": {"name": "X", "problem": "short", "target_user": "u", "what_it_does": "does a thing", "how_it_works": "python"}}).json()
    assert "ShellHacks 2025" not in json.dumps(r["recommendations"])


# ---------- prizes are specific to the year ----------

def test_prizes_come_from_the_chosen_year():
    titles = {b: {p.title for p in load_prizes(b)[0]} for b, _ in YEAR_BASELINES}
    assert "Second Best Overall" in titles["shellhacks2024:2024"]
    assert "Second Best Overall" not in titles["shellhacks2025:2025"]
    assert "Second Place Overall" in titles["shellhacks-2023:2023"]


def test_combined_prizes_are_deduplicated_and_have_one_overall_entry():
    prizes = combined_prizes()
    overall = [p for p in prizes if p.prize_type == "overall"]
    assert len(overall) == 1 and "2025" not in overall[0].title  # one entry, from the newest year
    keys = [re.sub(r"[^a-z0-9]+", " ", p.title.lower()).strip() for p in prizes if p.prize_type != "overall"]
    assert len(keys) == len(set(keys))
    all_titles = " ".join(p.title for p in prizes)
    assert "BNY" in all_titles and "Capital One" in all_titles  # 2024-only and 2025 prizes both present


def test_fraud_idea_matches_each_years_own_finance_prize():
    idea = IdeaExtractor().extract(FRAUD, ["Stripe"])

    def strong(event_id):
        fits = PrizeMatcher().match_prizes(idea, ["Stripe"], event_id=event_id).top_fits
        return {f.award_title for f in fits if f.fit_level.value in ("strong", "very_strong")}

    assert any("Capital One" in t for t in strong("shellhacks2025:2025"))
    assert any("BNY" in t for t in strong("shellhacks2024:2024"))
    assert not any("BNY" in t for t in strong("shellhacks2025:2025"))
    combined = strong(ALL_YEARS_ID)
    assert any("BNY" in t for t in combined) and any("Capital One" in t for t in combined)


def test_overall_placements_are_one_target_not_three():
    idea = IdeaExtractor().extract("A tool for beekeepers that detects queenless colonies from hive audio.")
    fits = PrizeMatcher().match_prizes(idea, [], event_id="shellhacks2024:2024").top_fits
    assert sum(1 for f in fits if f.prize_type == "overall") == 1


def test_specific_prize_list_endpoint_follows_the_baseline(client):
    ids = {}
    for eid in ("shellhacks2024:2024", ALL_YEARS_ID):
        body = client.get(f"/api/events/{eid}/prizes").json()
        ids[eid] = {p["title"] for p in body["prizes"]}
    assert "Second Best Overall" in ids["shellhacks2024:2024"]
    assert len(ids[ALL_YEARS_ID]) > 0 and ids[ALL_YEARS_ID] != ids["shellhacks2024:2024"]


# ---------- criteria: a title or a swag item is not criteria ----------

def test_titles_and_swag_are_not_criteria():
    def p(desc, tech=None):
        return PrizeCategory(prize_id="x", title="T", description=desc, technologies_required_or_encouraged=tech or [])

    assert not prize_has_criteria(p("Prize: JBL Wireless Headphones"))
    assert not prize_has_criteria(p("**Making Insurance Easy**"))
    assert not prize_has_criteria(p("The Assurant Way Challenge: Our purpose"))
    assert prize_has_criteria(p("Build an app that helps drivers avoid unsafe intersections using real-time sensor data and maps."))
    assert prize_has_criteria(p("Short", tech=["Auth0"]))


def test_older_prize_with_swag_only_is_never_shown_as_a_fit():
    idea = IdeaExtractor().extract("An app for hackers that uses headphones and audio.")
    fits = PrizeMatcher().match_prizes(idea, [], event_id="shellhacks-2023:2023").top_fits
    assert not any("Taipy" in f.award_title or "Soroban" in f.award_title for f in fits)
