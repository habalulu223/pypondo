@echo off
setlocal enabledelayedexpansion
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%"

echo [1/6] Resolving Java toolchain...
call :resolve_java
if errorlevel 1 (
  popd
  exit /b 1
)

echo [2/6] Resolving Android SDK...
call :resolve_android_sdk
if errorlevel 1 (
  popd
  exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
  echo ERROR: npm not found. Install Node.js and ensure npm is on PATH.
  popd
  exit /b 1
)

if not exist "%SCRIPT_DIR%node_modules" (
  echo [3/6] Installing npm dependencies...
  call npm install
  if errorlevel 1 (
    echo ERROR: npm install failed.
    popd
    exit /b 1
  )
) else (
  echo [3/6] npm dependencies already installed.
)

echo [4/6] Building bundled web assets...
call npm run build
if errorlevel 1 (
  echo ERROR: Web build failed.
  popd
  exit /b 1
)

echo [5/6] Syncing Capacitor Android project...
call npx cap sync android
if errorlevel 1 (
  echo ERROR: Capacitor Android sync failed.
  popd
  exit /b 1
)

echo Adjusting generated Gradle Java compatibility for the local JDK...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$files = @(" ^
  "  '%SCRIPT_DIR%android\app\capacitor.build.gradle'," ^
  "  '%SCRIPT_DIR%android\capacitor-cordova-android-plugins\build.gradle'," ^
  "  '%SCRIPT_DIR%node_modules\@capacitor\android\capacitor\build.gradle'" ^
  ");" ^
  "foreach ($file in $files) {" ^
  "  if (-not (Test-Path $file)) { continue }" ^
  "  $content = Get-Content $file -Raw;" ^
  "  $content = $content.Replace('JavaVersion.VERSION_21', 'JavaVersion.VERSION_17');" ^
  "  Set-Content -Path $file -Value $content;" ^
  "}"

if not exist "%SCRIPT_DIR%android\gradlew.bat" (
  echo ERROR: Android Gradle wrapper not found at "%SCRIPT_DIR%android\gradlew.bat".
  popd
  exit /b 1
)

echo [6/6] Building Android APK...
pushd "%SCRIPT_DIR%android"
call gradlew.bat assembleDebug
if errorlevel 1 (
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

echo [DONE] APK generated and copied to "%DEST%\pypondo_mobile-1.0.0-debug.apk"
echo The APK bundles its own UI and connects directly to the PyPondo mobile API.
popd
endlocal
exit /b 0

:resolve_java
set "JAVA_READY="
set "JAVA_SOURCE="

if defined JAVA_HOME if exist "%JAVA_HOME%\bin\java.exe" (
  call :check_java "%JAVA_HOME%"
)

if not defined JAVA_READY (
  for /f "delims=" %%I in ('
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "$roots = @(" ^
      "  'C:\Program Files\Android\Android Studio\jbr'," ^
      "  'C:\Program Files\Android\Android Studio\jre'" ^
      ");" ^
      "$roots += Get-ChildItem 'C:\Program Files\Java' -Directory -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName;" ^
      "$roots += Get-ChildItem 'C:\Program Files\ojdkbuild' -Directory -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName;" ^
      "$roots += Get-ChildItem 'C:\Program Files\Eclipse Adoptium' -Directory -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName;" ^
      "$roots += Get-ChildItem 'C:\Program Files\Microsoft' -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'jdk*' } | Select-Object -ExpandProperty FullName;" ^
      "$roots = $roots | Where-Object { $_ } | Select-Object -Unique;" ^
      "foreach ($root in $roots) {" ^
      "  $java = Join-Path $root 'bin\java.exe';" ^
      "  if (-not (Test-Path $java)) { continue }" ^
      "  $line = (& $java -version 2>&1 | Select-Object -First 1);" ^
      "  if ($line -and $line -notmatch 'version ""1\.') { Write-Output $root; break }" ^
      "}"'
  ) do (
    if not defined JAVA_READY call :check_java "%%~I"
  )
)

if not defined JAVA_READY (
  echo ERROR: JDK 11 or newer was not found.
  echo Install JDK 17+ or Android Studio, then set JAVA_HOME to that JDK.
  echo Current PATH java:
  java -version 2>&1
  exit /b 1
)

set "JAVA_HOME=%JAVA_READY%"
set "PATH=%JAVA_HOME%\bin;%PATH%"
echo Using Java from %JAVA_SOURCE%
java -version
exit /b 0

:check_java
set "JAVA_CANDIDATE=%~1"
if not exist "%JAVA_CANDIDATE%\bin\java.exe" exit /b 0

"%JAVA_CANDIDATE%\bin\java.exe" -version 2>"%TEMP%\pypondo_java_version.txt"
findstr /i /c:"version \"1." "%TEMP%\pypondo_java_version.txt" >nul 2>nul
if errorlevel 1 (
  set "JAVA_READY=%JAVA_CANDIDATE%"
  set "JAVA_SOURCE=%JAVA_CANDIDATE%"
)
del /q "%TEMP%\pypondo_java_version.txt" >nul 2>nul
exit /b 0

:resolve_android_sdk
set "ANDROID_SDK_READY="

if defined ANDROID_HOME if exist "%ANDROID_HOME%\platform-tools" (
  set "ANDROID_SDK_READY=%ANDROID_HOME%"
)

if not defined ANDROID_SDK_READY if defined ANDROID_SDK_ROOT if exist "%ANDROID_SDK_ROOT%\platform-tools" (
  set "ANDROID_SDK_READY=%ANDROID_SDK_ROOT%"
)

if not defined ANDROID_SDK_READY if exist "%LOCALAPPDATA%\Android\Sdk\platform-tools" (
  set "ANDROID_SDK_READY=%LOCALAPPDATA%\Android\Sdk"
)

if not defined ANDROID_SDK_READY (
  echo ERROR: Android SDK not found.
  echo Install the Android SDK command-line tools or Android Studio, then make sure "%LOCALAPPDATA%\Android\Sdk" exists.
  exit /b 1
)

set "ANDROID_HOME=%ANDROID_SDK_READY%"
set "ANDROID_SDK_ROOT=%ANDROID_SDK_READY%"
> "%SCRIPT_DIR%android\local.properties" echo sdk.dir=%ANDROID_HOME:\=/%
echo Using Android SDK at %ANDROID_HOME%
exit /b 0
