# Daily update routine

Instructions for the scheduled Claude Code routine (runs daily at 07:00 Taiwan time).

1. `pip install -r requirements.txt`
2. `python update.py prepare`
   - If it fetched 0 headlines, stop and report the error. Do not commit.
3. Read `data/work/prompt.txt` and follow its instructions exactly.
   Write your answer to `data/work/extracted.json`: a single JSON object matching `data/work/schema.json`.
   Do not use web search or fetch any other sources; work only from the headlines in the prompt.
4. `python update.py apply`
   - If it fails, fix `data/work/extracted.json` (not the code) and run it again.
5. Commit `data/spots.json` and `docs/index.html` to `main` with the message `Daily update YYYY-MM-DD`
   and push to `main`. Do not change any other files.
