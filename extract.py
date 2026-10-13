"""Use Claude to turn raw headlines into structured, photo-worthy spots in Taiwan.

Runs through the Claude Code CLI in headless mode (`claude -p`), so it uses your
Claude plan instead of API billing. ANTHROPIC_API_KEY is removed from the child
environment so it can never switch to pay-per-use.
"""
import json
import os
import shutil
import subprocess
from datetime import date

from sources import Article

CATEGORIES = ["flower", "foliage", "grass", "bird", "event", "landscape", "other"]
STATUSES = ["upcoming", "starting", "peak", "fading", "ongoing", "ended", "unknown"]

SPOT_SCHEMA = {
    "type": "object",
    "properties": {
        "spots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "existing_id": {"type": "string", "description": "id of the matching known spot, or empty string if new"},
                    "subject": {"type": "string", "description": "What to photograph, e.g. 芒草, 楓紅, 煙火"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "location_name": {"type": "string", "description": "Specific place, e.g. 草嶺古道"},
                    "county": {"type": "string", "description": "Taiwan county/city, e.g. 新北市"},
                    "lat": {"type": "number"},
                    "lng": {"type": "number"},
                    "status": {"type": "string", "enum": STATUSES},
                    "date_start": {"type": "string", "description": "YYYY-MM-DD, or empty string if unknown"},
                    "date_end": {"type": "string", "description": "YYYY-MM-DD, or empty string if unknown"},
                    "est_end": {"type": "string", "description": "Nature spots only: estimated YYYY-MM-DD the scene is over, or empty string"},
                    "est_basis": {"type": "string", "description": "Short reason for est_end in Traditional Chinese, or empty string"},
                    "summary": {"type": "string", "description": "One sentence in Traditional Chinese for a photographer"},
                    "appeal": {"type": "integer", "description": "1-5, how photogenic / rare the scene itself is"},
                    "appeal_reason": {"type": "string", "description": "Short reason for the appeal rating, Traditional Chinese"},
                    "article_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["existing_id", "subject", "category", "location_name", "county", "lat", "lng", "status",
                             "date_start", "date_end", "est_end", "est_basis", "summary", "appeal", "appeal_reason", "article_ids"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["spots"],
    "additionalProperties": False,
}

SYSTEM = """You help a landscape and event photographer in Taiwan find what is worth shooting.
You receive recent items from several kinds of sources, each tagged with where it came from:
- Google News headlines.
- Official event listings (觀光署): dated events with place and coordinates. Most are not photo subjects;
  keep only visually striking public events (fireworks, parades, festivals, lantern shows, indigenous ceremonies,
  flower/ecology events). Skip runs, markets, concerts in halls, sales, food events, admin notices.
- Official bloom / park / forest news (花IN台北, national parks, 林業保育署): reliable bloom status and seasonal
  events; ignore closures, construction, recruitment and admin notices unless they affect a photo spot.
- PTT first-hand reports: hikers' trip posts. Use only when they describe current scenery in Taiwan
  (silver grass, autumn colors, sea of clouds...); skip trips abroad and posts without scenery details.

Extract photo-worthy spots IN TAIWAN only: seasonal nature (flowers, autumn leaves, silver grass, birds),
landscapes (sea of clouds, stars), and public events (fireworks, parades, festivals, lantern shows).

Rules:
- Skip anything outside Taiwan (Japan/Korea/Hong Kong foliage etc.), ads, finance and unrelated news.
- When an item gives coordinates, use them for lat/lng.
- Skip generic listicles that don't name a specific place with current conditions or dates.
- Merge headlines about the same place and subject into one spot; list every related article id.
- If a spot matches one in "Known spots" (same place and subject), set existing_id to its id
  and update status/dates from the new headlines. Otherwise existing_id is "".
- lat/lng: your best estimate for the named place in Taiwan.
- status: use what the headline says (e.g. "3成轉紅" = starting, "盛開" = peak). Events with future dates = upcoming.
- status "ended" only when a headline says it is over (凋謝, 落盡, 已結束); events whose date has passed are also "ended".
- Dates: infer from the headline relative to today's date; leave empty if unknown.
- est_end (flower, foliage, grass, bird only; "" for events and landscapes): when no official end date is given,
  estimate when the scene will be over, from the reported status, the report date, and how long this plant's bloom
  or this bird's stay typically lasts in Taiwan at that altitude. est_basis says briefly how you estimated it,
  e.g. "10/7 三成轉紅，楓紅通常約3-4週後落葉". If you have no reasonable basis, leave both empty.
- appeal: rate only the scene itself, not timing or popularity.
  5 = rare or spectacular (large fireworks, rare bird, famous peak bloom), 4 = very photogenic seasonal scene,
  3 = nice but common, 2 = minor (small local show, commercial event), 1 = barely photogenic."""


def build_prompt(articles: list[Article], known: list[dict], today: date) -> str:
    known_lines = [f"- id={s['id']}: {s['subject']} @ {s['location_name']} ({s['county']})" for s in known]
    lines = [f"[{i}] <{a.query}> {a.title} ({a.source}, {a.published})" + (f" | {a.detail}" if a.detail else "")
             for i, a in enumerate(articles)]
    return (f"{SYSTEM}\n\nToday is {today.isoformat()}.\n\n"
            "Known spots:\n" + ("\n".join(known_lines) or "(none)") +
            "\n\nItems:\n" + "\n".join(lines))


def validate(raw: dict) -> list[dict]:
    """Check extraction output against SPOT_SCHEMA; drop malformed spots instead of failing the run."""
    item = SPOT_SCHEMA["properties"]["spots"]["items"]
    types = {"string": str, "number": (int, float), "integer": int, "array": list}
    valid = []
    for spot in raw.get("spots", []):
        problems = [k for k, rule in item["properties"].items()
                    if not isinstance(spot.get(k), types[rule["type"]])
                    or ("enum" in rule and spot[k] not in rule["enum"])]
        if problems:
            print(f"Dropped malformed spot {spot.get('subject', '?')}: bad {problems}")
        else:
            valid.append({k: spot[k] for k in item["properties"]})
    return valid


def attach_articles(spots: list[dict], articles: list[Article]) -> list[dict]:
    for spot in spots:
        spot["articles"] = [
            {"title": articles[i].title, "source": articles[i].source, "link": articles[i].link}
            for i in spot.pop("article_ids") if 0 <= i < len(articles)
        ]
    return spots


def extract_spots(articles: list[Article], known: list[dict], today: date) -> list[dict]:
    """Local mode: run the extraction through `claude -p`."""
    claude = shutil.which("claude")
    if not claude:
        raise RuntimeError("Claude Code CLI not found on PATH")

    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    result = subprocess.run(
        [claude, "-p", "--output-format", "json", "--json-schema", json.dumps(SPOT_SCHEMA), "--tools", ""],
        input=build_prompt(articles, known, today), capture_output=True, text=True, encoding="utf-8", env=env, timeout=1200,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude -p failed (exit {result.returncode}): {result.stderr or result.stdout}")

    output = json.loads(result.stdout)
    if output.get("is_error") or "structured_output" not in output:
        raise RuntimeError(f"claude -p returned no structured output: {output.get('result')}")

    print(f"Done in {output.get('duration_ms', 0) / 1000:.0f}s")
    return attach_articles(validate(output["structured_output"]), articles)
