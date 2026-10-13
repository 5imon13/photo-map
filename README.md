# Photo Map Taiwan

Finds photo-worthy scenes and events in Taiwan (芒草, 楓紅, 花季, 煙火, 賞鳥...) from recent news and shows them on a map.

Pipeline: Google News RSS → Claude extracts spots (place, status, dates, coordinates) → merged into `data/spots.json` → `docs/index.html`

## Run locally

```powershell
.\.venv\Scripts\Activate.ps1
python update.py
start docs\index.html
```

- Extraction runs through Claude Code headless mode (`claude -p`), using your Claude plan; no API key or API billing.
  Keep "extra usage" off in your claude.ai settings so hitting the limit fails instead of charging.
- The daily cloud routine follows `ROUTINE.md` (`update.py prepare` → Claude extracts → `update.py apply`).
- Each run merges into `data/spots.json`; spots drop off 14 days after the news last mentioned them
  (announced future events stay until their date passes).
- Score = appeal (Claude's rating of the scene) × 0.5 + timing (status/dates) × 0.4 + buzz (article count) × 0.1.
- For plants and birds, Claude estimates an end date (`est_end`); the map always labels it as an AI estimate.
- `python sources.py` lists the raw headlines only (no Claude call). Search terms are in `QUERIES` in `sources.py`.
