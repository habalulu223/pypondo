@REM PyPondo Backend Tunneling Setup Script
@REM This script helps expose your local PyPondo backend to the internet using ngrok

@echo off
setlocal enabledelayedexpansion

echo ============================================
echo PyPondo Backend Tunneling Setup
echo ============================================
echo.

REM Check if ngrok is installed
where ngrok >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] ngrok is not installed or not in PATH
    echo.
    echo To install ngrok:
    echo 1. Download from https://ngrok.com/download
    echo 2. Extract the executable
    echo 3. Add to your PATH or place in this directory
    echo.
    pause
    exit /b 1
)

echo [OK] ngrok found
echo.

REM Check if Flask is running
powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://localhost:5000' -TimeoutSec 2 -ErrorAction Stop; Write-Host '[OK] Flask app is running on localhost:5000' } catch { Write-Host '[ERROR] Flask app not running on localhost:5000'; exit 1 }"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Please start the Flask app first:
    echo   cd PythonProject
    echo   python app.py
    echo.
    pause
    exit /b 1
)

echo.
echo Starting ngrok tunnel to http://localhost:5000...
echo.
echo When ngrok starts:
echo 1. Look for the "Forwarding" line
echo 2. Copy the public URL (e.g., https://abc123.ngrok.io)
echo 3. Use this URL in your Netlify deployment
echo.
echo To keep ngrok running in background, minimize this window.
echo Close this window to stop the tunnel.
echo.
pause

REM Start ngrok
ngrok http 5000

pause
