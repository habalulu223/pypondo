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
    echo Install and reboot first:
    echo   wsl --install -d Ubuntu
    echo.
    echo After reboot, run this inside Ubuntu from your project folder:
    echo   sudo apt update ^&^& sudo apt install -y python3 python3-venv python3-pip openjdk-17-jdk git zip unzip
    echo   python3 -m venv .venv-android
    echo   source .venv-android/bin/activate
    echo   pip install --upgrade pip
    echo   pip install buildozer cython
    echo   buildozer android debug
    echo.
    pause
    exit /b 1
  )

  echo ERROR: Native Windows Android build is not supported by buildozer.
  echo.
  echo WSL is available. Run the build in your Ubuntu distro:
  echo   cd /mnt/c/Users/USER4/PycharmProjects/pypondo/PythonProject
  echo   sudo apt update ^&^& sudo apt install -y python3 python3-venv python3-pip openjdk-17-jdk git zip unzip
  echo   python3 -m venv .venv-android
  echo   source .venv-android/bin/activate
  echo   pip install --upgrade pip
  echo   pip install buildozer cython
  echo   buildozer android debug
  echo.
  pause
  exit /b 1
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
