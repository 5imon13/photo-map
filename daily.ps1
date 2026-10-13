# Daily update: refresh the map and publish it to GitHub Pages.
# Run by Windows Task Scheduler ("Photo Map daily update", 07:07 and 16:07) through run_hidden.vbs,
# so no window shows. Log: logs\YYYY-MM-DD.log

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue  # never fall back to API billing

$today = Get-Date -Format "yyyy-MM-dd"
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
New-Item -ItemType Directory -Force logs | Out-Null
Start-Transcript -Path "logs\$today.log" -Append | Out-Null

try {
    git pull --rebase --autostash --quiet
    if ($LASTEXITCODE) { throw "git pull failed" }

    & .\.venv\Scripts\python.exe update.py
    if ($LASTEXITCODE) { throw "update.py failed" }

    git add data/spots.json data/source_health.json docs/index.html
    git diff --cached --quiet
    if ($LASTEXITCODE) {
        git commit --quiet -m "Update $stamp"
        git push --quiet
        if ($LASTEXITCODE) { throw "git push failed" }
        Write-Output "Published update $stamp"
    } else {
        Write-Output "No changes to publish"
    }
} catch {
    Write-Output "FAILED: $_"
    exit 1
} finally {
    Stop-Transcript | Out-Null
}
