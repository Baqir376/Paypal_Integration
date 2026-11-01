# ==============================================================================
# Salix Offline Demo Runner (PowerShell)
# 100% Hermetic / Offline Execution for Hackathon Presentations
# Zero Internet Required - Uses Local Mock Providers, Datasets & SQLite
# ==============================================================================

[CmdletBinding()]
param(
    [int]$ApiPort = 8010,
    [int]$WebPort = 3000,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  SALIX -- MULTILINGUAL OFFLINE DEMO LAUNCHER" -ForegroundColor Cyan
Write-Host "  English | Urdu (Nastaliq) | Roman Urdu" -ForegroundColor Cyan
Write-Host "  Mode: 100% OFFLINE (Hermetic Mock Inference)" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check Python virtual environment
$PythonExe = Join-Path $ScriptDir "api\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Error "Python virtualenv not found at api\.venv\Scripts\python.exe. Please ensure the venv is set up."
    exit 1
}

# 2. Check Node.js
try {
    $NodeVer = & node -v
    Write-Host "[OK] Node.js detected: $NodeVer" -ForegroundColor Green
} catch {
    Write-Error "Node.js is not installed or not in PATH."
    exit 1
}

# 3. Force offline mock environment variables
$env:SALIX_PROVIDER_MODE = "mock"
$env:SALIX_API_URL = "http://127.0.0.1:$ApiPort"
$env:PORT = "$WebPort"

Write-Host "[OK] Environment configured: SALIX_PROVIDER_MODE=mock" -ForegroundColor Green

# 4. Start Backend API Process
Write-Host "[*] Starting FastAPI Backend on http://127.0.0.1:$ApiPort ..." -ForegroundColor Cyan
$ApiCwd = Join-Path $ScriptDir "api"
$ApiProcess = Start-Process -FilePath $PythonExe `
    -ArgumentList "-m", "uvicorn", "salix.app:app", "--host", "127.0.0.1", "--port", "$ApiPort" `
    -WorkingDirectory $ApiCwd `
    -PassThru

# 5. Wait for API to become healthy
Write-Host "[*] Waiting for backend healthcheck..." -ForegroundColor Gray
$HealthUrl = "http://127.0.0.1:$ApiPort/api/health"
$MaxRetries = 20
$ApiReady = $false

for ($i = 0; $i -lt $MaxRetries; $i++) {
    Start-Sleep -Milliseconds 600
    try {
        $response = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($response -and $response.status -eq "ok") {
            $ApiReady = $true
            Write-Host "[OK] Backend ready! Seeded calls: $($response.calls), Plays: $($response.plays)" -ForegroundColor Green
            break
        }
    } catch {
        # continue waiting
    }
}

if (-not $ApiReady) {
    Write-Warning "Backend is still starting or took longer than expected. Continuing..."
}

# 6. Start Web Frontend
$WebCwd = Join-Path $ScriptDir "web"
$NpmCmd = (Get-Command "npm.cmd" -ErrorAction SilentlyContinue).Source
if (-not $NpmCmd) { $NpmCmd = "npm" }

Write-Host "[*] Starting Next.js Web Server on http://localhost:$WebPort ..." -ForegroundColor Cyan

# Use npm run start if production build exists, otherwise npm run dev
$NextBuildDir = Join-Path $WebCwd ".next"
$WebScript = if (Test-Path $NextBuildDir) { "start" } else { "dev" }

Write-Host "[*] Launching frontend via 'npm run $WebScript'..." -ForegroundColor Gray
$WebProcess = Start-Process -FilePath $NpmCmd `
    -ArgumentList "run", "$WebScript", "--", "-p", "$WebPort" `
    -WorkingDirectory $WebCwd `
    -PassThru

# 7. Launch browser
if (-not $NoBrowser) {
    Start-Sleep -Seconds 2
    $TargetUrl = "http://localhost:$WebPort"
    Write-Host "[*] Opening browser to $TargetUrl ..." -ForegroundColor Cyan
    Start-Process $TargetUrl
}

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "  SALIX IS RUNNING OFFLINE!" -ForegroundColor Green
Write-Host "  Web UI:    http://localhost:$WebPort" -ForegroundColor White
Write-Host "  API:       http://127.0.0.1:$ApiPort/api" -ForegroundColor White
Write-Host "  Samples:   storage\samples\" -ForegroundColor White
Write-Host "  Press CTRL+C in this window to stop both servers." -ForegroundColor Yellow
Write-Host "==========================================================`n" -ForegroundColor Green

try {
    # Keep script alive until interrupted
    while ($true) {
        if ($ApiProcess.HasExited) {
            Write-Warning "API process exited unexpectedly."
            break
        }
        if ($WebProcess.HasExited) {
            Write-Warning "Web process exited unexpectedly."
            break
        }
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Host "`n[*] Stopping services..." -ForegroundColor Gray
    if ($ApiProcess -and -not $ApiProcess.HasExited) {
        Stop-Process -Id $ApiProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($WebProcess -and -not $WebProcess.HasExited) {
        Stop-Process -Id $WebProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "[OK] Shutdown complete." -ForegroundColor Green
}
