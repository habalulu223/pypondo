@echo off
setlocal enabledelayedexpansion
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%"

echo [1/5] Checking toolchain...
where npm >nul 2>&1
if errorlevel 1 (
  echo ERROR: npm not found. Install Node.js and ensure npm is on PATH.
  popd
  exit /b 1
)
where java >nul 2>&1
if errorlevel 1 (
  echo ERROR: java not found. Install JDK 11 or newer and ensure java is on PATH.
  popd
  exit /b 1
)

java -version 2>"%TEMP%\java_version.txt"
findstr /c:"version 1.8" "%TEMP%\java_version.txt" >nul 2>nul
if %errorlevel%==0 (
  echo ERROR: Java 8 detected. JDK 11 or newer is required.
  del /q "%TEMP%\java_version.txt" >nul 2>nul
  popd
  exit /b 1
)
del /q "%TEMP%\java_version.txt" >nul 2>nul

if not exist "%SCRIPT_DIR%node_modules" (
  echo [2/5] Installing npm dependencies...
  npm install || (
    echo ERROR: npm install failed.
    popd
    exit /b 1
  )
)

echo [3/5] Building web assets...
npm run build || (
  echo ERROR: Web build failed.
  popd
  exit /b 1
)

if not exist "%SCRIPT_DIR%android\gradlew.bat" (
  echo ERROR: Android Gradle wrapper not found at "%SCRIPT_DIR%android\gradlew.bat".
  popd
  exit /b 1
)

echo [4/5] Building Android APK...
pushd "%SCRIPT_DIR%android"
call gradlew.bat assembleDebug || (
  popd
  popd
  exit /b 1
)
popd

set "APK_SOURCE=%SCRIPT_DIR%android\app\build\outputs\apk\debug\app-debug.apk"
if not exist "%APK_SOURCE%" (
  echo ERROR: APK not found at %APK_SOURCE%.
  popd
  exit /b 1
)

set "DEST=%SCRIPT_DIR%..\..\PythonProject\bin"
if not exist "%DEST%" mkdir "%DEST%"
copy /y "%APK_SOURCE%" "%DEST%\pypondo_mobile-1.0.0-debug.apk" >nul

echo [5/5] SUCCESS: APK generated and copied to "%DEST%\pypondo_mobile-1.0.0-debug.apk"
echo The APK uses the CyberCore icon and is configured for local network connections.
popd
endlocal
