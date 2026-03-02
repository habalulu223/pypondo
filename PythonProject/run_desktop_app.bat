@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD=python"
if exist "..\.venv\Scripts\python.exe" (
  set "PYTHON_CMD=..\.venv\Scripts\python.exe"
)

echo Starting PyPondo desktop app...
"%PYTHON_CMD%" -c "import webview" >nul 2>&1
if errorlevel 1 (
  echo pywebview not found. Installing...
  "%PYTHON_CMD%" -m pip install pywebview
  if errorlevel 1 (
    echo Failed to install pywebview.
    exit /b 1
  )
)

"%PYTHON_CMD%" desktop_app.py
endlocal
