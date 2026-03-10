@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ============================================================
echo PyPondo Mobile Android APK Builder
echo ============================================================
echo.

REM Check if buildozer is installed
python -c "import buildozer" >nul 2>&1
if errorlevel 1 (
  echo [INFO] Installing buildozer...
  pip install buildozer
  if errorlevel 1 (
    echo ERROR: Failed to install buildozer.
    echo Please install manually: pip install buildozer
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

buildozer android debug
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