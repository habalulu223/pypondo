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
echo PyPondo Standalone Executable Builder
echo ============================================================
echo.

echo [1/3] Installing build tools...
"%PYTHON_CMD%" %PYTHON_ARGS% -m pip install --upgrade pyinstaller >nul 2>&1
if errorlevel 1 (
  echo ERROR: Failed to install PyInstaller
  pause
  exit /b 1
)
echo [OK] PyInstaller installed

echo.
echo [2/3] Installing optional UI runtime dependencies...
"%PYTHON_CMD%" %PYTHON_ARGS% -m pip install --pre pythonnet >nul 2>&1
if errorlevel 1 (
  echo [WARNING] pythonnet installation failed, continuing...
)
"%PYTHON_CMD%" %PYTHON_ARGS% -m pip install pywebview >nul 2>&1
if errorlevel 1 (
  echo [WARNING] pywebview installation failed, app will use browser mode
) else (
  echo [OK] Desktop UI dependencies installed
)

echo.
echo [3/3] Packaging application (this may take 1-2 minutes)...
"%PYTHON_CMD%" %PYTHON_ARGS% -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name PyPondo ^
  --icon "assets\pypondo.ico" ^
  --collect-all webview ^
  --hidden-import lan_agent ^
  --add-data "templates;templates" ^
  desktop_app.py

if errorlevel 1 (
  echo ERROR: Build failed
  pause
  exit /b 1
)

echo.
echo ============================================================
echo BUILD COMPLETE!
echo ============================================================
echo.
echo Executable Location: dist\PyPondo.exe
echo.
echo NEXT STEPS FOR CLIENT PC:
echo 1. Copy dist\PyPondo.exe to client computer
echo 2. On client PC, create server_host.txt with admin server hostname/IP
echo 3. Double-click PyPondo.exe to start
echo.
echo Example server_host.txt:
echo   MY-ADMIN-PC
echo   or
echo   192.168.1.100
echo.
echo For more details, see CLIENT_SETUP.md
echo.
endlocal
