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
if ($WithTunnel) {
    Write-Host "  Tunnel    -> optional temporary HTTPS URL"
}
Write-Host ""
Write-Host "The production API remains https://api.headlineavenue.com." -ForegroundColor DarkGray
Write-Host "Use -WithTunnel only when a provider callback specifically needs a temporary public local URL." -ForegroundColor DarkGray
