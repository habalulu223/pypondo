@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD=python"
if exist "..\.venv\Scripts\python.exe" (
  set "PYTHON_CMD=..\.venv\Scripts\python.exe"
)

echo Installing desktop build tools...
"%PYTHON_CMD%" -m pip install pyinstaller pywebview
if errorlevel 1 exit /b 1

echo Building PyPondo.exe...
"%PYTHON_CMD%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --name PyPondo ^
  --add-data "templates;templates" ^
  desktop_app.py

if errorlevel 1 exit /b 1
echo Build complete: dist\PyPondo.exe
endlocal
