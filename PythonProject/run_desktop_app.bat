@echo off
setlocal
cd /d "%~dp0"

if exist "dist\PyPondo.exe" (
  echo Starting the standalone PyPondo desktop app...
  start "PyPondo" "dist\PyPondo.exe"
  exit /b 0
)

if exist "..\.venv\Scripts\python.exe" (
  echo Starting PyPondo with the project Python environment...
  "..\.venv\Scripts\python.exe" desktop_app.py
  exit /b %errorlevel%
)

where py >nul 2>&1
if not errorlevel 1 (
  echo Starting PyPondo with Python 3...
  py -3 desktop_app.py
  exit /b %errorlevel%
)

where python >nul 2>&1
if not errorlevel 1 (
  echo Starting PyPondo with Python...
  python desktop_app.py
  exit /b %errorlevel%
)

echo PyPondo.exe was not found and Python is not installed.
echo Build the standalone app with build_desktop_app.bat, or install Python 3.
pause
exit /b 1
