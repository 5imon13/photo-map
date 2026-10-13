"""Spot history: merge each run's extraction into data/spots.json, score, and expire old spots."""
import json
import uuid
from datetime import date
from pathlib import Path

RETENTION_DAYS = 14

REGIONS = {
    "北部": ["基隆", "臺北", "新北", "桃園", "新竹"],
    "中部": ["苗栗", "臺中", "彰化", "南投", "雲林"],
    "南部": ["嘉義", "臺南", "高雄", "屏東"],
    "東部": ["宜蘭", "花蓮", "臺東"],
    "離島": ["澎湖", "金門", "連江", "馬祖"],
}

STATUS_TIMING = {"peak": 5, "starting": 4, "ongoing": 4, "fading": 2, "unknown": 2, "ended": 0}
WEIGHTS = {"appeal": 0.5, "timing": 0.4, "buzz": 0.1}


def region_of(county: str) -> str:
    county = county.replace("台", "臺")
    for region, names in REGIONS.items():
        if any(county.startswith(n) for n in names):
            return region
    return "其他"


def _days(a: str, b: date) -> int | None:
    try:
        return (date.fromisoformat(a) - b).days
    except ValueError:
        return None


def is_ended(spot: dict, today: date) -> bool:
    if spot["status"] == "ended":
        return True
    end = spot["date_end"] or (spot["date_start"] if spot["category"] == "event" else "")
    days = _days(end, today) if end else None
    return days is not None and days < 0


def maybe_over(spot: dict, today: date) -> bool:
    """Past the AI-estimated end date, but no report confirms it's over."""
    days = _days(spot.get("est_end", ""), today)
    return days is not None and days < 0 and not is_ended(spot, today)


def timing_score(spot: dict, today: date) -> int:
    if is_ended(spot, today):
        return 0
    if maybe_over(spot, today):
        return 1
    if spot["status"] != "upcoming":
        return STATUS_TIMING[spot["status"]]
    days_until = _days(spot["date_start"], today)
    if days_until is None:
        return 2
    return 4 if days_until <= 7 else 3 if days_until <= 21 else 2


def buzz_score(article_count: int) -> int:
    return 1 if article_count <= 1 else 2 if article_count == 2 else 3 if article_count <= 4 else 4 if article_count <= 7 else 5


def score(spot: dict, today: date) -> None:
    parts = {
        "appeal": spot["appeal"],
        "timing": timing_score(spot, today),
        "buzz": buzz_score(len(spot["articles"])),
    }
    total = sum(parts[k] * WEIGHTS[k] for k in parts)
    spot["score_parts"] = parts
    spot["score_value"] = round(total, 1)
    spot["score"] = max(1, min(5, int(total + 0.5)))


def is_kept(spot: dict, today: date) -> bool:
    if (today - date.fromisoformat(spot["last_seen"])).days <= RETENTION_DAYS:
        return True
    # Keep announced future events even if the news went quiet
    for key in ("date_end", "date_start"):
        d = _days(spot[key], today)
        if d is not None:
            return d >= 0
    return False


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def merge(existing: list[dict], extracted: list[dict], today: date) -> list[dict]:
    by_id = {s["id"]: s for s in existing}
    stamp = today.isoformat()
    for new in extracted:
        old = by_id.get(new.pop("existing_id"))
        if old:
            links = {a["link"] for a in old["articles"]}
            new["articles"] = old["articles"] + [a for a in new["articles"] if a["link"] not in links]
            new.update(id=old["id"], first_seen=old["first_seen"])
        else:
            new.update(id=uuid.uuid4().hex[:8], first_seen=stamp)
        new["last_seen"] = stamp
        new["region"] = region_of(new["county"])
        by_id[new["id"]] = new

    spots = [s for s in by_id.values() if is_kept(s, today)]
    for s in spots:
        score(s, today)
    spots.sort(key=lambda s: (s["score_value"], s["last_seen"]), reverse=True)
    return spots
