# PyPondo Client Setup & Launch Script (PowerShell)
# Usage: .\setup_client.ps1

Write-Host "`n" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  PyPondo Client - Setup & Launch" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "`n"

# Check Python
Write-Host "Checking Python installation..." -ForegroundColor Cyan
$pythonCmd = "python"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python not found" -ForegroundColor Red
    Write-Host "Please install Python 3.8+ and add it to PATH"
    Read-Host "Press Enter to exit"
    exit 1
}

python --version
Write-Host "[OK]`n"

# Install core packages
Write-Host "Installing required packages..." -ForegroundColor Cyan
python -m pip install --quiet flask flask-sqlalchemy flask-login werkzeug
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to install packages" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "[OK]`n"

# Try optional UI packages
Write-Host "Installing optional UI runtime..." -ForegroundColor Cyan
python -m pip install --quiet --pre pythonnet 2>$null
python -m pip install --quiet pywebview 2>$null
$canUI = python -c "import webview" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Desktop UI available`n"
} else {
    Write-Host "[WARNING] Desktop UI not available (optional)" -ForegroundColor Yellow
    Write-Host "App will use browser mode`n"
}

# Create server_host.txt if needed
if (-not (Test-Path "server_host.txt")) {
    Write-Host "============================================================" -ForegroundColor Yellow
    Write-Host "  SERVER CONFIGURATION REQUIRED" -ForegroundColor Yellow
    Write-Host "============================================================`n" -ForegroundColor Yellow
    
    Write-Host "Creating server_host.txt template..."
    @"
# PyPondo Admin Server Hostname/IP
# Replace ADMIN-SERVER below with your admin PC's hostname or IP

ADMIN-SERVER
"@ | Set-Content "server_host.txt"
    
    Write-Host "[OK] Created server_host.txt`n"
    Write-Host "NEXT STEP: Edit server_host.txt with your admin server's:" -ForegroundColor Yellow
    Write-Host "  - Computer name (preferred): MY-ADMIN-PC"
    Write-Host "  - IP address: 192.168.1.100"
    Write-Host ""
    Read-Host "Press Enter when ready"
}

# Start the app
Write-Host "`nStarting PyPondo Client..." -ForegroundColor Cyan
Write-Host ""
python desktop_app.py
