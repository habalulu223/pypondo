@echo off
setlocal
cd /d "%~dp0"

if exist "dist\PyPondoOnline.exe" (
  echo Starting the server-connected PyPondo desktop app...
  start "PyPondo Online" "dist\PyPondoOnline.exe"
  exit /b 0
)

if exist "..\.venv\Scripts\python.exe" (
  echo Starting PyPondo Online from source...
  "..\.venv\Scripts\python.exe" desktop_online_app.py
  exit /b %errorlevel%
)

where py >nul 2>&1
if not errorlevel 1 (
  echo Starting PyPondo Online with Python 3...
  py -3 desktop_online_app.py
  exit /b %errorlevel%
)

where python >nul 2>&1
if not errorlevel 1 (
  echo Starting PyPondo Online with Python...
  python desktop_online_app.py
  exit /b %errorlevel%
)

echo PyPondoOnline.exe was not found and Python is not installed.
echo Build both desktop apps with build_desktop_app.bat, or install Python 3.
pause
exit /b 1
