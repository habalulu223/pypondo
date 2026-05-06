@REM PyPondo public route helper for phone access
@REM This exposes the local backend over a Cloudflare quick tunnel.

@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "LOCAL_PORT=%APP_PORT%"
if "%LOCAL_PORT%"=="" set "LOCAL_PORT=5000"
set "LOCAL_URL=http://127.0.0.1:%LOCAL_PORT%"
set "CLOUDFLARED_BIN="

echo ============================================
echo PyPondo Phone Public Route
echo ============================================
echo.

if exist "%SCRIPT_DIR%bin\cloudflared.exe" (
    set "CLOUDFLARED_BIN=%SCRIPT_DIR%bin\cloudflared.exe"
) else (
    for /f "delims=" %%I in ('where cloudflared 2^>nul') do (
        if not defined CLOUDFLARED_BIN set "CLOUDFLARED_BIN=%%I"
    )
)

powershell -Command "try { $response = Invoke-WebRequest -Uri '%LOCAL_URL%/api/server-info' -TimeoutSec 2 -ErrorAction Stop; Write-Host '[OK] Flask app is running on %LOCAL_URL%' } catch { Write-Host '[ERROR] Flask app not running on %LOCAL_URL%'; exit 1 }"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Please start the backend first:
    echo   cd PythonProject
    echo   python app.py
    echo.
    pause
    exit /b 1
)

if not defined CLOUDFLARED_BIN (
    echo [INFO] cloudflared was not found. Downloading it into PythonProject\bin...
    if not exist "%SCRIPT_DIR%bin" mkdir "%SCRIPT_DIR%bin"
    powershell -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile '%SCRIPT_DIR%bin\cloudflared.exe'"
    if exist "%SCRIPT_DIR%bin\cloudflared.exe" (
        set "CLOUDFLARED_BIN=%SCRIPT_DIR%bin\cloudflared.exe"
    )
)

if not defined CLOUDFLARED_BIN (
    echo [ERROR] cloudflared could not be found or downloaded.
    echo Download it manually from:
    echo   https://github.com/cloudflare/cloudflared/releases
    echo.
    pause
    exit /b 1
)

echo [OK] cloudflared ready: %CLOUDFLARED_BIN%
echo.
echo Starting public route to %LOCAL_URL% ...
echo.
echo When the tunnel prints an https://...trycloudflare.com URL:
echo 1. Copy that URL
echo 2. Paste it into the phone app server address field
echo 3. Or use the dashboard pairing QR after the public route is active
echo.
echo Keep this window open while the phone is connected.
echo Close this window to stop the public route.
echo.
pause

"%CLOUDFLARED_BIN%" tunnel --url %LOCAL_URL% --no-autoupdate

pause
