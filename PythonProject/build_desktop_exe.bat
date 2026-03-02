@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD=python"
if exist "..\.venv\Scripts\python.exe" (
  set "PYTHON_CMD=..\.venv\Scripts\python.exe"
)

echo Building standalone PyPondo.exe...
echo Installing build tools...
"%PYTHON_CMD%" -m pip install --upgrade pyinstaller
if errorlevel 1 exit /b 1

echo Installing desktop UI runtime dependencies...
"%PYTHON_CMD%" -m pip install --pre pythonnet
if not errorlevel 1 (
  "%PYTHON_CMD%" -m pip install pywebview
)

echo Packaging app (Python runtime will be bundled)...
"%PYTHON_CMD%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name PyPondo ^
  --icon "assets\pypondo.ico" ^
  --collect-all webview ^
  --add-data "templates;templates" ^
  desktop_app.py

if errorlevel 1 exit /b 1

echo Build complete: dist\PyPondo.exe
echo This EXE is the downloadable app and runs without Python installed.
endlocal
