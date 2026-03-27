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

if "%PYPONDO_FORCE_INSTALL%"=="" set "PYPONDO_FORCE_INSTALL=0"
if "%PYPONDO_CLEAN%"=="" set "PYPONDO_CLEAN=0"

echo.
echo ============================================================
echo PyPondo Standalone Executable Builder
echo ============================================================
if "%PYPONDO_FORCE_INSTALL%"=="1" (
  echo Mode: Full dependency refresh
) else (
  echo Mode: Fast build (skip reinstall if already present)
)
if "%PYPONDO_CLEAN%"=="1" (
  echo Clean build: ON
) else (
  echo Clean build: OFF
)
echo.

echo [1/3] Checking build tools...
set "NEED_PYI_INSTALL=0"
"%PYTHON_CMD%" %PYTHON_ARGS% -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('PyInstaller') else 1)" >nul 2>&1
if errorlevel 1 set "NEED_PYI_INSTALL=1"
if "%PYPONDO_FORCE_INSTALL%"=="1" set "NEED_PYI_INSTALL=1"

if "%NEED_PYI_INSTALL%"=="1" (
  if "%PYPONDO_FORCE_INSTALL%"=="1" (
    echo [INFO] Installing/upgrading PyInstaller...
    "%PYTHON_CMD%" %PYTHON_ARGS% -m pip install --upgrade pyinstaller >nul 2>&1
  ) else (
    echo [INFO] Installing PyInstaller...
    "%PYTHON_CMD%" %PYTHON_ARGS% -m pip install pyinstaller >nul 2>&1
  )
  if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller
    pause
    exit /b 1
  )
  echo [OK] PyInstaller ready
) else (
  echo [OK] PyInstaller already installed
)

echo.
echo [2/3] Checking desktop runtime dependencies...

set "NEED_PYWEBVIEW_INSTALL=0"
"%PYTHON_CMD%" %PYTHON_ARGS% -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('webview') else 1)" >nul 2>&1
if errorlevel 1 set "NEED_PYWEBVIEW_INSTALL=1"
if "%PYPONDO_FORCE_INSTALL%"=="1" set "NEED_PYWEBVIEW_INSTALL=1"

if "%NEED_PYWEBVIEW_INSTALL%"=="1" (
  echo [INFO] Installing pywebview...
  "%PYTHON_CMD%" %PYTHON_ARGS% -m pip install pywebview >nul 2>&1
  if errorlevel 1 (
    echo [WARNING] pywebview installation failed, app will use browser mode
  ) else (
    echo [OK] pywebview ready
  )
) else (
  echo [OK] pywebview already installed
)

set "NEED_KEYBOARD_INSTALL=0"
"%PYTHON_CMD%" %PYTHON_ARGS% -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('keyboard') else 1)" >nul 2>&1
if errorlevel 1 set "NEED_KEYBOARD_INSTALL=1"
if "%PYPONDO_FORCE_INSTALL%"=="1" set "NEED_KEYBOARD_INSTALL=1"

if "%NEED_KEYBOARD_INSTALL%"=="1" (
  echo [INFO] Installing keyboard...
  "%PYTHON_CMD%" %PYTHON_ARGS% -m pip install keyboard >nul 2>&1
  if errorlevel 1 (
    echo [WARNING] keyboard installation failed, app will rely on native fallback hook
  ) else (
    echo [OK] keyboard ready
  )
) else (
  echo [OK] keyboard already installed
)

if "%PYPONDO_FORCE_INSTALL%"=="1" (
  echo [INFO] Optional dependency refresh: pythonnet
  "%PYTHON_CMD%" %PYTHON_ARGS% -m pip install --pre pythonnet >nul 2>&1
  if errorlevel 1 (
    echo [WARNING] pythonnet installation failed, continuing...
  ) else (
    echo [OK] pythonnet ready
  )
)

echo.
echo [3/3] Packaging application...
if "%PYPONDO_CLEAN%"=="1" (
  echo [INFO] Running clean PyInstaller build...
  "%PYTHON_CMD%" %PYTHON_ARGS% -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name PyPondo ^
    --icon "assets\pypondo.ico" ^
    --collect-all webview ^
    --hidden-import lan_agent ^
    --hidden-import keyboard ^
    --add-data "templates;templates" ^
    --add-data "server_host.txt;." ^
    desktop_app.py
) else (
  echo [INFO] Running fast incremental PyInstaller build...
  "%PYTHON_CMD%" %PYTHON_ARGS% -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name PyPondo ^
    --icon "assets\pypondo.ico" ^
    --collect-all webview ^
    --hidden-import lan_agent ^
    --hidden-import keyboard ^
    --add-data "templates;templates" ^
    --add-data "server_host.txt;." ^
    desktop_app.py
)

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
echo Fast mode (default):
echo   build_desktop_exe.bat
echo.
echo Full refresh mode:
echo   set PYPONDO_FORCE_INSTALL=1 ^& set PYPONDO_CLEAN=1 ^& build_desktop_exe.bat
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
