@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PYTHON_CMD=python"
if exist "..\.venv\Scripts\python.exe" (
  set "PYTHON_CMD=..\.venv\Scripts\python.exe"
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
"%PYTHON_CMD%" -c "import flask, flask_sqlalchemy, flask_login" >nul 2>&1
if errorlevel 1 (
  echo [INFO] Installing core dependencies...
  "%PYTHON_CMD%" -m pip install flask flask-sqlalchemy flask-login werkzeug
  if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
  )
)

echo [OK] Core packages available

"%PYTHON_CMD%" -c "import webview" >nul 2>&1
if errorlevel 1 (
  echo.
  echo [INFO] Installing optional UI dependencies (pywebview)...
  "%PYTHON_CMD%" -m pip install --pre pythonnet
  if not errorlevel 1 (
    "%PYTHON_CMD%" -m pip install pywebview
  )
  "%PYTHON_CMD%" -c "import webview" >nul 2>&1
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
"%PYTHON_CMD%" desktop_app.py
endlocal
