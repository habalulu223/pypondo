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
echo PyPondo Mobile Android APK Builder
echo ============================================================
echo.

"%PYTHON_CMD%" %PYTHON_ARGS% -c "import sys; sys.exit(2 if sys.platform == 'win32' else 0)"
if errorlevel 2 (
  wsl -e sh -lc "echo WSL_READY" >nul 2>&1
  if errorlevel 1 (
    echo ERROR: Android APK build cannot run on native Windows.
    echo.
    echo WSL is required and not ready on this machine.
    echo Open PowerShell as Administrator and run:
    echo   wsl --install -d Ubuntu
    echo.
    echo Then do these steps in order:
    echo   1. Reboot Windows
    echo   2. Open the Ubuntu app once
    echo   3. Finish the Linux username/password setup
    echo   4. Run build_android_safe.bat in this project folder
    echo.
    pause
    exit /b 1
  )

  for /f "usebackq delims=" %%I in (`wsl.exe wslpath "%cd%"`) do set "WSL_PROJECT_DIR=%%I"
  if not defined WSL_PROJECT_DIR (
    echo ERROR: Could not resolve WSL project path.
    pause
    exit /b 1
  )

  echo [INFO] WSL detected. Starting Android build inside Ubuntu...
  wsl.exe -e bash -lc "cd '!WSL_PROJECT_DIR!' && chmod +x build_android_wsl.sh && ./build_android_wsl.sh"
  if errorlevel 1 (
    echo.
    echo ERROR: WSL Android build failed.
    pause
    exit /b 1
  )

  echo.
  echo [OK] WSL Android build finished.
  pause
  exit /b 0
)

REM Check if buildozer is installed
"%PYTHON_CMD%" %PYTHON_ARGS% -c "import buildozer" >nul 2>&1
if errorlevel 1 (
  echo [INFO] Installing buildozer...
  "%PYTHON_CMD%" %PYTHON_ARGS% -m pip install buildozer
  if errorlevel 1 (
    echo ERROR: Failed to install buildozer.
    echo Please install manually: "%PYTHON_CMD%" %PYTHON_ARGS% -m pip install buildozer
    pause
    exit /b 1
  )
)

echo [OK] Buildozer available

REM Check if Android SDK/NDK are set up (this is complex, buildozer will handle it)
echo.
echo [INFO] Building Android APK...
echo This may take a long time on first run as it downloads Android SDK/NDK.
echo.

"%PYTHON_CMD%" %PYTHON_ARGS% buildozer_shim.py android debug
if errorlevel 1 (
  echo.
  echo ERROR: Build failed.
  echo Check the output above for details.
  echo.
  echo Common issues:
  echo - Android SDK/NDK download issues
  echo - Java JDK not installed
  echo - Insufficient disk space
  echo.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo Build completed successfully!
echo ============================================================
echo.
echo APK location: bin/pypondo_mobile-1.0.0-debug.apk
echo.
echo To install on Android device:
echo 1. Enable "Unknown sources" in Android settings
echo 2. Transfer the APK to your device
echo 3. Open the APK file on your device to install
echo.
pause
