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

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Host "cloudflared is not installed or is not on PATH." -ForegroundColor Red
    exit 1
}

Write-Host "Starting Headline Avenue..." -ForegroundColor Cyan

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

$tunnelCommand = @"
Write-Host 'HEADLINE AVENUE - CLOUDFLARE TUNNEL' -ForegroundColor Magenta
Write-Host 'Copy the https://....trycloudflare.com URL shown below.' -ForegroundColor Yellow
cloudflared tunnel --url http://127.0.0.1:8000
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCommand
Start-Sleep -Milliseconds 600
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCommand
Start-Sleep -Milliseconds 1000
Start-Process powershell -ArgumentList "-NoExit", "-Command", $tunnelCommand

Start-Sleep -Seconds 2
Start-Process "http://localhost:5500/app.html"

Write-Host ""
Write-Host "Three PowerShell windows were opened:" -ForegroundColor Green
Write-Host "  Frontend  -> http://localhost:5500/app.html"
Write-Host "  Backend   -> http://127.0.0.1:8000"
Write-Host "  Tunnel    -> copy its new HTTPS URL"
Write-Host ""
Write-Host "Reminder: a Quick Tunnel gets a new hostname after restart." -ForegroundColor Yellow
Write-Host "Update TIKTOK_REDIRECT_URI and the TikTok Sandbox redirect URI before OAuth testing." -ForegroundColor Yellow
