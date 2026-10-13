# Daily update: refresh the map and publish it to GitHub Pages.
# Run by Windows Task Scheduler ("Photo Map daily update"). Log: logs\YYYY-MM-DD.log

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue  # never fall back to API billing

$today = Get-Date -Format "yyyy-MM-dd"
New-Item -ItemType Directory -Force logs | Out-Null
Start-Transcript -Path "logs\$today.log" -Append | Out-Null

try {
    git pull --rebase --quiet
    if ($LASTEXITCODE) { throw "git pull failed" }

    & .\.venv\Scripts\python.exe update.py
    if ($LASTEXITCODE) { throw "update.py failed" }

    git add data/spots.json docs/index.html
    git diff --cached --quiet
    if ($LASTEXITCODE) {
        git commit --quiet -m "Daily update $today"
        git push --quiet
        if ($LASTEXITCODE) { throw "git push failed" }
        Write-Output "Published update for $today"
    } else {
        Write-Output "No changes to publish"
    }
} catch {
    Write-Output "FAILED: $_"
    exit 1
} finally {
    Stop-Transcript | Out-Null
}
