# Super-easy host setup for the Knight Home Tech fader bridge on Windows.
# Creates a venv, installs deps, seeds host\.env, and (unless -NoService)
# registers a Scheduled Task that runs the bridge at logon (auto-detecting faders).
#
#   ./install/install.ps1
#   ./install/install.ps1 -NoService
param([switch]$NoService)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Write-Host "==> Repo: $repo"

# 1) venv + dependencies
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $py) { throw "Python not found on PATH. Install Python 3 first." }
Write-Host "==> Creating venv (.venv)"
& $py -m venv "$repo\.venv"
& "$repo\.venv\Scripts\python.exe" -m pip install --upgrade pip | Out-Null
Write-Host "==> Installing host requirements"
& "$repo\.venv\Scripts\pip.exe" install -r "$repo\host\requirements.txt"

# 2) .env (broker config)
if (-not (Test-Path "$repo\host\.env")) {
  Copy-Item "$repo\host\.env.example" "$repo\host\.env"
  Write-Host "==> Seeded host\.env from the example - edit it to set your broker."
} else {
  Write-Host "==> host\.env already exists - leaving it as-is."
}

# 3) Scheduled Task (runs at logon)
if (-not $NoService) {
  Write-Host "==> Registering Scheduled Task 'Console10FaderBridge' (runs at logon)"
  $runner = "$repo\install\run_bridge.ps1"
  $action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runner`""
  $trigger = New-ScheduledTaskTrigger -AtLogOn
  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
  Register-ScheduledTask -TaskName "Console10FaderBridge" -Action $action -Trigger $trigger `
    -Settings $settings -Force | Out-Null
  Write-Host "==> Task registered. Start it now with:"
  Write-Host "    Start-ScheduledTask -TaskName Console10FaderBridge"
} else {
  Write-Host "==> Skipped service. Run manually:  ./install/run_bridge.ps1"
}

Write-Host ""
Write-Host "Done."
Write-Host "  Flash a board:  python tools\flash_firmware.py"
Write-Host "  List faders:    ./install/run_bridge.ps1 --list"
