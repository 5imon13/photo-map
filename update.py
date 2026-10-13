"""Update the map: news headlines -> Claude extraction -> merge into history -> docs/index.html

    python update.py           Local, all steps (extraction via `claude -p` on your Claude plan)
    python update.py prepare   Fetch headlines, write data/work/prompt.txt for an external extractor
    python update.py apply     Read data/work/extracted.json, merge into history, rebuild the site

The cloud routine runs `prepare`, does the extraction itself, then runs `apply`.
"""
import json
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import health
import store
from extract import SPOT_SCHEMA, attach_articles, build_prompt, extract_spots, validate
from sources import Article, fetch_articles

ROOT = Path(__file__).parent
SPOTS_FILE = ROOT / "data" / "spots.json"
HEALTH_FILE = ROOT / "data" / "source_health.json"
WORK_DIR = ROOT / "data" / "work"
SITE_FILE = ROOT / "docs" / "index.html"
TAIWAN = timezone(timedelta(hours=8))  # cloud machines run in UTC


def now() -> datetime:
    return datetime.now(TAIWAN)


def build_site(spots: list[dict], status: dict[str, str], alerts: list[dict]) -> None:
    template = (ROOT / "map_template.html").read_text(encoding="utf-8")
    page = (template.replace("__SPOTS__", json.dumps(spots, ensure_ascii=False))
                    .replace("__STATUS__", json.dumps(status, ensure_ascii=False))
                    .replace("__ALERTS__", json.dumps(alerts, ensure_ascii=False))
                    .replace("__UPDATED__", now().strftime("%Y-%m-%d %H:%M")))
    SITE_FILE.parent.mkdir(exist_ok=True)
    SITE_FILE.write_text(page, encoding="utf-8")


def save(known: list[dict], extracted: list[dict], status: dict[str, str]) -> None:
    spots = store.merge(known, extracted, now().date())
    print(f"Extracted {len(extracted)} spots this run, {len(spots)} on the map\n")
    for s in spots:
        p = s["score_parts"]
        print(f"  {s['score_value']:.1f} {s['subject']} @ {s['location_name']} ({s['region']}) "
              f"- {s['status']}  [appeal {p['appeal']} / timing {p['timing']} / buzz {p['buzz']}]")
    SPOTS_FILE.write_text(json.dumps(spots, ensure_ascii=False, indent=2), encoding="utf-8")
    alerts = health.update(HEALTH_FILE, status, now())
    for a in alerts:
        print(f"WARNING: source {a['source']} bad for {a['bad_runs']} runs since {a['bad_since']}: {a['last_problem']}")
    build_site(spots, status, alerts)
    print(f"\nWrote {SPOTS_FILE.relative_to(ROOT)} and {SITE_FILE.relative_to(ROOT)}")


def prepare() -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    articles, status = fetch_articles()
    known = store.load(SPOTS_FILE)
    (WORK_DIR / "status.json").write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
    (WORK_DIR / "headlines.json").write_text(
        json.dumps([asdict(a) for a in articles], ensure_ascii=False), encoding="utf-8")
    (WORK_DIR / "prompt.txt").write_text(build_prompt(articles, known, now().date()), encoding="utf-8")
    (WORK_DIR / "schema.json").write_text(json.dumps(SPOT_SCHEMA, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Fetched {len(articles)} items, {len(known)} known spots")
    print(f"Wrote data/work/prompt.txt and schema.json; write the result to data/work/extracted.json")


def apply() -> None:
    articles = [Article(**a) for a in json.loads((WORK_DIR / "headlines.json").read_text(encoding="utf-8"))]
    raw = json.loads((WORK_DIR / "extracted.json").read_text(encoding="utf-8"))
    status = json.loads((WORK_DIR / "status.json").read_text(encoding="utf-8"))
    save(store.load(SPOTS_FILE), attach_articles(validate(raw), articles), status)


def run_local() -> None:
    SPOTS_FILE.parent.mkdir(exist_ok=True)
    known = store.load(SPOTS_FILE)
    articles, status = fetch_articles()
    print(f"Fetched {len(articles)} items, {len(known)} known spots")
    save(known, extract_spots(articles, known, now().date()), status)


if __name__ == "__main__":
    {"prepare": prepare, "apply": apply}.get(sys.argv[1] if len(sys.argv) > 1 else "", run_local)()
