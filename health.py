"""Track each source's health across runs, so a broken crawler gets flagged on the site.

A source counts as bad on a run if it failed or returned 0 items (a site redesign often
breaks parsing silently instead of raising an error). One bad run is usually a temporary
outage; ALERT_AFTER bad runs in a row means the crawler probably needs updating.
"""
import json
from datetime import datetime
from pathlib import Path

ALERT_AFTER = 3


def update(path: Path, status: dict[str, str], now: datetime) -> list[dict]:
    """Record this run's status; return alerts for sources that have been bad for ALERT_AFTER runs."""
    health = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    stamp = now.strftime("%Y-%m-%d %H:%M")
    for name, st in status.items():
        h = health.setdefault(name, {"bad_runs": 0, "bad_since": "", "last_ok": "", "last_problem": ""})
        h["last_status"] = st
        if st.startswith("FAILED") or st.startswith("0 "):
            if h["bad_runs"] == 0:
                h["bad_since"] = stamp
            h["bad_runs"] += 1
            h["last_problem"] = st
        else:
            h.update(bad_runs=0, bad_since="", last_ok=stamp)
    path.write_text(json.dumps(health, ensure_ascii=False, indent=2), encoding="utf-8")
    return [{"source": name, **h} for name, h in health.items()
            if name in status and h["bad_runs"] >= ALERT_AFTER]


def last_status(path: Path) -> tuple[dict[str, str], list[dict]]:
    """Status and alerts from the last recorded run, for rebuilding the site without fetching."""
    health = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    status = {name: h.get("last_status") or ("正常" if h["bad_runs"] == 0 else h["last_problem"]) for name, h in health.items()}
    return status, [{"source": n, **h} for n, h in health.items() if h["bad_runs"] >= ALERT_AFTER]
