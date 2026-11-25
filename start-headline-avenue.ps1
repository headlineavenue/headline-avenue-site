param(
    [switch]$WithTunnel
)

$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "Backend virtual environment was not found at:" -ForegroundColor Red
    Write-Host $Python -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Create it first from the backend folder with:" -ForegroundColor Yellow
    Write-Host "py -m venv .venv"
    exit 1
}

if ($WithTunnel -and -not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Host "cloudflared is not installed or is not on PATH." -ForegroundColor Red
    exit 1
}

Write-Host "Starting Headline Avenue local development..." -ForegroundColor Cyan

# Prevent stale local services from surviving between launches. Repeated launcher runs
# previously left multiple Uvicorn reloaders, HTTP servers, and ingestion workers alive,
# which could serve older code after a git pull.
$escapedRoot = [regex]::Escape($Root)
$staleProcesses = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessId -gt 0 -and
    $_.Name -match '^python(?:\.exe)?
$frontendCommand = @"
Set-Location '$Root'
Write-Host 'HEADLINE AVENUE - FRONTEND' -ForegroundColor Cyan
& '$Python' -m http.server 5500
"@

$backendCommand = @"
Set-Location '$Backend'
Write-Host 'HEADLINE AVENUE - BACKEND API' -ForegroundColor Green
& '$Python' -m uvicorn app.main:app --reload
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCommand
Start-Sleep -Milliseconds 600
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCommand

$backendReady = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $health = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 1
        if ($health.StatusCode -eq 200) {
            $backendReady = $true
            break
        }
    } catch {
        Start-Sleep -Milliseconds 500
    }
}

if (-not $backendReady) {
    Write-Host "Backend health check did not become ready. Worker was not started." -ForegroundColor Red
    exit 1
}

$workerCommand = @"
Set-Location '$Backend'
Write-Host 'HEADLINE AVENUE - INGESTION WORKER' -ForegroundColor Yellow
& '$Python' -m app.ingestion_worker
"@
Start-Process powershell -ArgumentList "-NoExit", "-Command", $workerCommand

if ($WithTunnel) {
    $tunnelCommand = @"
Write-Host 'HEADLINE AVENUE - OPTIONAL CLOUDFLARE TUNNEL' -ForegroundColor Magenta
cloudflared tunnel --url http://127.0.0.1:8000
"@
    Start-Sleep -Milliseconds 800
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $tunnelCommand
}

Start-Sleep -Seconds 2
Start-Process "http://localhost:5500/app.html"

Write-Host ""
Write-Host "Local services opened:" -ForegroundColor Green
Write-Host "  Frontend  -> http://localhost:5500/app.html"
Write-Host "  Backend   -> http://127.0.0.1:8000"
Write-Host "  Worker    -> queued media transcription"
if ($WithTunnel) {
    Write-Host "  Tunnel    -> optional temporary HTTPS URL"
}
Write-Host ""
Write-Host "The production API remains https://api.headlineavenue.com." -ForegroundColor DarkGray
Write-Host "Use -WithTunnel only when a provider callback specifically needs a temporary public local URL." -ForegroundColor DarkGray
 -and
    $_.CommandLine -match $escapedRoot -and
    $_.CommandLine -match '(uvicorn\s+app\.main:app|http\.server\s+5500|app\.ingestion_worker)'
}

if ($staleProcesses) {
    Write-Host "Stopping stale Headline Avenue local services..." -ForegroundColor DarkYellow
    foreach ($process in $staleProcesses) {
        try {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
        } catch {
            Write-Host "Could not stop PID $($process.ProcessId): $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
    Start-Sleep -Milliseconds 700
}

$occupiedPorts = @()
foreach ($port in 5500, 8000) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) {
        $occupiedPorts += $port
    }
}

if ($occupiedPorts.Count -gt 0) {
    Write-Host "Cannot start cleanly because these ports are still in use: $($occupiedPorts -join ', ')" -ForegroundColor Red
    Write-Host "Close the process using those ports, then run this launcher again." -ForegroundColor Yellow
    exit 1
}

$frontendCommand = @"
Set-Location '$Root'
Write-Host 'HEADLINE AVENUE - FRONTEND' -ForegroundColor Cyan
& '$Python' -m http.server 5500
"@

$backendCommand = @"
Set-Location '$Backend'
Write-Host 'HEADLINE AVENUE - BACKEND API' -ForegroundColor Green
& '$Python' -m uvicorn app.main:app --reload
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCommand
Start-Sleep -Milliseconds 600
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCommand

$backendReady = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $health = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 1
        if ($health.StatusCode -eq 200) {
            $backendReady = $true
            break
        }
    } catch {
        Start-Sleep -Milliseconds 500
    }
}

if (-not $backendReady) {
    Write-Host "Backend health check did not become ready. Worker was not started." -ForegroundColor Red
    exit 1
}

$workerCommand = @"
Set-Location '$Backend'
Write-Host 'HEADLINE AVENUE - INGESTION WORKER' -ForegroundColor Yellow
& '$Python' -m app.ingestion_worker
"@
Start-Process powershell -ArgumentList "-NoExit", "-Command", $workerCommand

if ($WithTunnel) {
    $tunnelCommand = @"
Write-Host 'HEADLINE AVENUE - OPTIONAL CLOUDFLARE TUNNEL' -ForegroundColor Magenta
cloudflared tunnel --url http://127.0.0.1:8000
"@
    Start-Sleep -Milliseconds 800
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $tunnelCommand
}

Start-Sleep -Seconds 2
Start-Process "http://localhost:5500/app.html"

Write-Host ""
Write-Host "Local services opened:" -ForegroundColor Green
Write-Host "  Frontend  -> http://localhost:5500/app.html"
Write-Host "  Backend   -> http://127.0.0.1:8000"
Write-Host "  Worker    -> queued media transcription"
if ($WithTunnel) {
    Write-Host "  Tunnel    -> optional temporary HTTPS URL"
}
Write-Host ""
Write-Host "The production API remains https://api.headlineavenue.com." -ForegroundColor DarkGray
Write-Host "Use -WithTunnel only when a provider callback specifically needs a temporary public local URL." -ForegroundColor DarkGray
