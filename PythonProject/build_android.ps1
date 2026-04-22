$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Set-Location -LiteralPath $PSScriptRoot

Write-Host ""
Write-Host "============================================================"
Write-Host "PyPondo Mobile Android APK Builder (PowerShell)"
Write-Host "============================================================"
Write-Host ""

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: WSL is not installed or not available in PATH." -ForegroundColor Red
    Write-Host ""
    Write-Host "Open PowerShell as Administrator and run:" -ForegroundColor Yellow
    Write-Host "  wsl --install -d Ubuntu"
    Write-Host "Then reboot Windows, launch Ubuntu once, finish the Linux username/password setup,"
    Write-Host "and rerun build_android_safe.bat."
    exit 1
}

try {
    & wsl.exe -e sh -lc "echo WSL_READY" *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "WSL is installed but not ready."
    }
} catch {
    Write-Host "ERROR: WSL is not ready on this machine." -ForegroundColor Red
    Write-Host ""
    Write-Host "Open PowerShell as Administrator and run:" -ForegroundColor Yellow
    Write-Host "  wsl --install -d Ubuntu"
    Write-Host ""
    Write-Host "Then do these steps in order:" -ForegroundColor Yellow
    Write-Host "  1. Reboot Windows"
    Write-Host "  2. Open the Ubuntu app once"
    Write-Host "  3. Finish the Linux username/password setup"
    Write-Host "  4. Return to this project and run build_android_safe.bat"
    exit 1
}

$windowsPath = (Get-Location).Path
$wslProjectDir = (& wsl.exe wslpath -- $windowsPath).Trim()
if (-not $wslProjectDir) {
    Write-Host "ERROR: Could not resolve the project path for WSL." -ForegroundColor Red
    exit 1
}

$bashCommand = 'cd "$1" && chmod +x build_android_wsl.sh && ./build_android_wsl.sh'

Write-Host "[INFO] Starting Android build inside WSL..." -ForegroundColor Cyan
& wsl.exe -e bash -lc $bashCommand bash $wslProjectDir
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Android build failed inside WSL." -ForegroundColor Red
    exit $exitCode
}

Write-Host ""
Write-Host "[OK] Android build finished." -ForegroundColor Green
exit 0
