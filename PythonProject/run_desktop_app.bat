@echo off
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
echo PyPondo Client Application
echo ============================================================
echo.

REM Check if server_host.txt exists for client mode
if exist "server_host.txt" (
  echo [INFO] Found server_host.txt - Running in CLIENT mode
  echo.
  for /f "tokens=*" %%A in (server_host.txt) do (
    if not "%%A"=="" if not "%%A:~0,1%"=="#" (
      echo [INFO] Server host configured: %%A
      set "PYPONDO_SERVER_HOST=%%A"
      goto :server_found
    )
  )
  :server_found
)

echo Checking required packages...
"%PYTHON_CMD%" %PYTHON_ARGS% -c "import flask, flask_sqlalchemy, flask_login" >nul 2>&1
if errorlevel 1 (
  echo [INFO] Installing core dependencies...
  "%PYTHON_CMD%" %PYTHON_ARGS% -m pip install flask flask-sqlalchemy flask-login werkzeug
  if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
  )
)

echo [OK] Core packages available

"%PYTHON_CMD%" %PYTHON_ARGS% -c "import keyboard" >nul 2>&1
if errorlevel 1 (
  echo.
  echo [INFO] Installing keyboard hook library for Windows key blocking...
  "%PYTHON_CMD%" %PYTHON_ARGS% -m pip install keyboard
  if errorlevel 1 (
    echo [WARNING] Failed to install keyboard library. Windows key blocking may be limited.
  ) else (
    echo [OK] Keyboard hook library available
  )
) else (
  echo [OK] Keyboard hook library available
)

"%PYTHON_CMD%" %PYTHON_ARGS% -c "import webview" >nul 2>&1
if errorlevel 1 (
  echo.
  echo [INFO] Installing optional UI dependencies (pywebview)...
  "%PYTHON_CMD%" %PYTHON_ARGS% -m pip install --pre pythonnet
  if not errorlevel 1 (
    "%PYTHON_CMD%" %PYTHON_ARGS% -m pip install pywebview
  )
  "%PYTHON_CMD%" %PYTHON_ARGS% -c "import webview" >nul 2>&1
  if errorlevel 1 (
    echo [WARNING] pywebview not available. App will use browser mode.
  ) else (
    echo [OK] Desktop UI available
  )
) else (
  echo [OK] Desktop UI available
)

echo.
echo Starting application...
echo.
"%PYTHON_CMD%" %PYTHON_ARGS% desktop_app.py
endlocal
