@echo off
REM PyPondo Client Standalone Setup
REM This script prepares a minimal client installation

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PYTHON_CMD=python"
set "PYTHON_ARGS="
if exist ".\.venv\Scripts\python.exe" (
    set "PYTHON_CMD=.\.venv\Scripts\python.exe"
) else if exist "..\.venv\Scripts\python.exe" (
  set "PYTHON_CMD=..\.venv\Scripts\python.exe"
)

if "%PYTHON_CMD%"=="python" (
    python --version >nul 2>&1
    if errorlevel 1 (
        py -3 --version >nul 2>&1
        if not errorlevel 1 (
            set "PYTHON_CMD=py"
            set "PYTHON_ARGS=-3"
        )
    )
)

echo.
echo ============================================================
echo PyPondo Client - Standalone Setup
echo ============================================================
echo.

REM Check Python
echo Checking Python installation...
"%PYTHON_CMD%" %PYTHON_ARGS% --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    echo Please install Python 3.8+ and add it to PATH
    pause
    exit /b 1
)
"%PYTHON_CMD%" %PYTHON_ARGS% --version
echo [OK]
echo.

REM Install core dependencies
echo Installing PyPondo client dependencies...
"%PYTHON_CMD%" %PYTHON_ARGS% -m pip install --quiet flask flask-sqlalchemy flask-login werkzeug
if errorlevel 1 (
    echo ERROR: Failed to install core packages
    pause
    exit /b 1
)
echo [OK] Core packages installed
echo.

REM Try to install optional UI dependencies
echo Installing optional UI runtime...
"%PYTHON_CMD%" %PYTHON_ARGS% -m pip install --quiet --pre pythonnet >nul 2>&1
"%PYTHON_CMD%" %PYTHON_ARGS% -m pip install --quiet pywebview >nul 2>&1
"%PYTHON_CMD%" %PYTHON_ARGS% -c "import webview" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Desktop UI not available (optional)
    echo          App will use browser mode
) else (
    echo [OK] Desktop UI available
)
echo.

REM Create server_host.txt if it doesn't exist
if not exist "server_host.txt" (
    echo.
    echo ============================================================
    echo SERVER CONFIGURATION REQUIRED
    echo ============================================================
    echo.
    echo Creating server_host.txt template...
    (
        echo # PyPondo Admin Server Hostname/IP
        echo # Replace ADMIN-SERVER below with your admin PC hostname or IP
        echo # Example: MY-ADMIN-PC
        echo # Example: 192.168.1.100
        echo.
        echo ADMIN-SERVER
    ) > server_host.txt
    echo [OK] Created server_host.txt
    echo.
    echo NEXT STEP: Edit server_host.txt and replace 'ADMIN-SERVER'
    echo with your admin PC's hostname or IP address.
    echo.
    pause
)

REM Register client app for current-user Windows startup
echo Registering client startup entry...
set "PYTHONW_CMD=%PYTHON_CMD%"
if /i "%PYTHON_CMD:~-10%"=="python.exe" (
    if exist "%PYTHON_CMD:~0,-10%pythonw.exe" (
        set "PYTHONW_CMD=%PYTHON_CMD:~0,-10%pythonw.exe"
    )
)

set "STARTUP_CMD=\"%PYTHONW_CMD%\" \"%CD%\desktop_app.py\""
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "CyberCoreClient" /t REG_SZ /d "%STARTUP_CMD%" /f >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Could not register startup automatically
    echo          You can still run the client manually
) else (
    echo [OK] Startup enabled: client will launch when this user signs in
)
echo.

REM Run the app
echo.
echo Starting PyPondo Client...
echo.
"%PYTHON_CMD%" %PYTHON_ARGS% desktop_app.py

endlocal
