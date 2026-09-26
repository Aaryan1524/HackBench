"""
Turn an event's sponsor_challenges.yaml into the event_metadata.json HackBench reads.

    uv run --with pyyaml python scripts/import_event_yaml.py data/raw/shellhacks2026/2026/event

PyYAML is only needed for this one-off import, so it is not a project dependency.
Nothing is invented: unknown URLs stay empty, and prize items (gift cards, swag) are kept only in the raw
`sponsor_challenges` record, never turned into judging criteria.
"""
import json
import re
import sys
from pathlib import Path

import yaml

# Technologies a sponsor challenge asks projects to use (taken from the challenge titles/descriptions).
REQUIRED_TECH = {
    "Best Use of ElevenLabs": ["ElevenLabs"],
    "Best Use of Gemini API": ["Gemini API"],
    "Best Use of Solana": ["Solana"],
    "Best Use of Tiger Data": ["Tiger Data"],
    "Best Use of DigitalOcean": ["DigitalOcean"],
    "Best Use of Snowflake API": ["Snowflake API"],
    "Best Use of MongoDB Atlas": ["MongoDB Atlas"],
    "Best Domain Name from GoDaddy Registry": ["GoDaddy Registry"],
}


def clean(text: str) -> str:
    return re.sub(r"[ \t]+\n", "\n", (text or "").strip())


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def main(event_dir: Path) -> None:
    data = yaml.safe_load((event_dir / "sponsor_challenges.yaml").read_text(encoding="utf-8"))
    name = data["event"]["name"]
    year = int(re.search(r"\d{4}", name).group(0))
    event_slug = f"shellhacks{year}"

    prizes = []
    for award in data.get("general_awards", []):
        title = award["name"]
        placements = award.get("placements") or []
        is_overall = "overall" in title.lower()
        prizes.append({
            "prize_id": f"{event_slug}_{slug(title)}",
            "title": title,
            "prize_type": "overall" if is_overall else "beginner",
            "sponsor_name": None,
            "description": (f"{title}: " + ", ".join(placements) + ".") if placements else "",
            "value_usd": None,
            "number_of_winners": len(placements) or 1,
            "technologies_required_or_encouraged": [],
            "source_url": "",
        })

    for c in data.get("sponsor_challenges", []):
        sponsor, challenge = c["sponsor"], c["challenge"]
        is_mlh = sponsor.startswith("MLH")
        partner = sponsor.split("-", 1)[1].strip() if is_mlh else sponsor
        parts = [clean(c.get("description", ""))]
        reqs = c.get("requirements") or c.get("requirement") or []
        if reqs:
            parts.append("Requirements: " + " ".join(clean(r) for r in reqs))
        prizes.append({
            "prize_id": f"{event_slug}_{slug(sponsor)}_{slug(challenge)}",
            "title": (f"MLH × {partner} — {challenge}" if is_mlh else f"{partner} — {challenge}"),
            "prize_type": "sponsor",
            "sponsor_name": partner,
            "description": "\n\n".join(p for p in parts if p),
            "value_usd": None,
            "number_of_winners": 1,
            "technologies_required_or_encouraged": REQUIRED_TECH.get(challenge, []),
            "source_url": "",
        })

    event = {
        "name": name,
        "slug": event_slug,
        "year": year,
        "organizer": "",
        "event_url": "",
        "devpost_url": "",
        "gallery_url": "",
        "prize_categories": prizes,
        # The raw record, including prize items, is kept for reference only.
        "sponsor_challenges": data.get("sponsor_challenges", []),
        "technologies_encouraged": sorted({t for ts in REQUIRED_TECH.values() for t in ts}),
    }
    out = event_dir / "event_metadata.json"
    out.write_text(json.dumps(event, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out} with {len(prizes)} prize categories")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
