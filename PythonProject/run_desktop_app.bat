@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD=python"
if exist "..\.venv\Scripts\python.exe" (
  set "PYTHON_CMD=..\.venv\Scripts\python.exe"
)

echo Starting PyPondo desktop app...
"%PYTHON_CMD%" -c "import flask, flask_sqlalchemy, flask_login" >nul 2>&1
if errorlevel 1 (
  echo Missing core dependencies. Installing...
  "%PYTHON_CMD%" -m pip install flask flask-sqlalchemy flask-login
  if errorlevel 1 (
    echo Failed to install dependencies.
    exit /b 1
  )
)

"%PYTHON_CMD%" -c "import webview" >nul 2>&1
if errorlevel 1 (
  echo pywebview not found. Installing desktop UI dependencies...
  "%PYTHON_CMD%" -m pip install --pre pythonnet
  if not errorlevel 1 (
    "%PYTHON_CMD%" -m pip install pywebview
  )
  "%PYTHON_CMD%" -c "import webview" >nul 2>&1
  if errorlevel 1 (
    echo pywebview install failed.
    echo App will run in browser mode with a desktop control window.
  )
)

"%PYTHON_CMD%" desktop_app.py
endlocal
