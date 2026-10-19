# Daily update: refresh the map and publish it to GitHub Pages.
# Run by Windows Task Scheduler ("Photo Map daily update", 07:07 and 16:07) through run_hidden.vbs,
# so no window shows. Log: logs\YYYY-MM-DD.log
# The morning run usually fires right after the laptop wakes, when github.com can be unreachable for a
# few minutes, so git steps wait for GitHub and retry here. (Task Scheduler's own "restart on failure" ignores a
# non-zero exit code, verified 2026-10-19, so it cannot do this for us.) Task time limit: 60 min.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue  # never fall back to API billing

$today = Get-Date -Format "yyyy-MM-dd"
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
New-Item -ItemType Directory -Force logs | Out-Null
Start-Transcript -Path "logs\$today.log" -Append | Out-Null

# Block until github.com accepts a TCP connection on 443 (checked every 30 s, up to 10 min).
# Without this, git waits out a 5-minute connect timeout and the whole run fails.
function Wait-ForGitHub {
    $deadline = (Get-Date).AddMinutes(10)
    $attempt = 0
    while ($true) {
        $attempt++
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            if ($client.ConnectAsync("github.com", 443).Wait(10000) -and $client.Connected) {
                if ($attempt -gt 1) { Write-Output "github.com reachable after $attempt checks" }
                return
            }
        } catch { } finally { $client.Dispose() }
        if ((Get-Date) -ge $deadline) { throw "github.com unreachable for 10 minutes" }
        if ($attempt -eq 1) { Write-Output "github.com not reachable yet, waiting..." }
        Start-Sleep -Seconds 30
    }
}

# Run a git command, waiting for GitHub first and retrying up to 3 times (60 s apart).
function Invoke-GitWithRetry {
    param([string[]]$GitArgs)
    for ($try = 1; $try -le 3; $try++) {
        Wait-ForGitHub
        git @GitArgs
        if (-not $LASTEXITCODE) { return }
        Write-Output "git $($GitArgs[0]) failed (attempt $try of 3)"
        if ($try -lt 3) { Start-Sleep -Seconds 60 }
    }
    throw "git $($GitArgs[0]) failed after 3 attempts"
}

try {
    Invoke-GitWithRetry @("pull", "--rebase", "--autostash", "--quiet")

    & .\.venv\Scripts\python.exe update.py
    if ($LASTEXITCODE) { throw "update.py failed" }

    git add data/spots.json data/seasonal.json data/source_health.json docs/index.html
    git diff --cached --quiet
    if ($LASTEXITCODE) {
        git commit --quiet -m "Update $stamp"
        Invoke-GitWithRetry @("push", "--quiet")
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
