# Starts the Sea Safe backend on this laptop so phones on the same Wi-Fi can reach it.
# Usage (from the NOVO folder):   powershell -ExecutionPolicy Bypass -File .\start-demo.ps1
# Options:  -Port 8001   -Seed   (load the demo fishers, reports, event and chat after start)
param([int]$Port = 8001, [switch]$Seed)

$ErrorActionPreference = "Stop"
$backend = Join-Path $PSScriptRoot "backend"
$python = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "Setting up the Python environment (first run only)..." -ForegroundColor Cyan
    Push-Location $backend
    python -m venv .venv
    & .venv\Scripts\pip.exe install -r requirements.txt
    Pop-Location
}
if (-not (Test-Path (Join-Path $backend ".env"))) {
    Copy-Item (Join-Path $backend ".env.example") (Join-Path $backend ".env")
    Write-Host "Created backend\.env from .env.example (add your API keys there)." -ForegroundColor Yellow
}

# The laptop's Wi-Fi / LAN address (skips loopback, link-local and virtual adapters).
$ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' -and $_.InterfaceAlias -notmatch 'vEthernet|VirtualBox|VMware|Loopback|WSL' } |
    Sort-Object { if ($_.InterfaceAlias -match 'Wi-?Fi|Wireless') { 0 } else { 1 } } |
    Select-Object -ExpandProperty IPAddress
$ip = $ips | Select-Object -First 1

# Allow phones to connect (needs an admin PowerShell the first time; harmless if it already exists).
$rule = "Sea Safe backend $Port"
if (-not (Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue)) {
    try {
        New-NetFirewallRule -DisplayName $rule -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow -Profile Private,Domain | Out-Null
        Write-Host "Firewall: opened port $Port for private networks." -ForegroundColor Green
    } catch {
        Write-Host "Firewall: could not open port $Port (run this once as Administrator if phones cannot connect)." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "  Sea Safe server address for both phones:" -ForegroundColor Cyan
if ($ip) { Write-Host "      http://${ip}:$Port" -ForegroundColor White } else { Write-Host "      (no Wi-Fi address found: connect to Wi-Fi)" -ForegroundColor Red }
foreach ($other in ($ips | Select-Object -Skip 1)) { Write-Host "      (also http://${other}:$Port)" -ForegroundColor DarkGray }
Write-Host "  Set it in the app: first screen -> Server settings, or long-press the title -> Simulation -> Server settings." -ForegroundColor DarkGray
Write-Host "  Dashboard:  http://localhost:$Port/dashboard     API docs: http://localhost:$Port/docs" -ForegroundColor DarkGray
Write-Host ""

if ($Seed) {
    Start-Job -ScriptBlock {
        param($p)
        for ($i = 0; $i -lt 40; $i++) {
            try { Invoke-RestMethod "http://127.0.0.1:$p/health" | Out-Null; break } catch { Start-Sleep -Milliseconds 500 }
        }
        Invoke-RestMethod -Method Post "http://127.0.0.1:$p/demo/seed" | Out-Null
    } -ArgumentList $Port | Out-Null
    Write-Host "  Demo data will be loaded as soon as the server is up." -ForegroundColor DarkGray
}

Push-Location $backend
try {
    & $python -m uvicorn app.main:app --host 0.0.0.0 --port $Port
} finally {
    Pop-Location
}
