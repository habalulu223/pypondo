@echo off
setlocal
set "JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-17.0.20.8-hotspot"
set "PATH=%JAVA_HOME%\bin;C:\Program Files\nodejs;%PATH%"
pushd "%~dp0..\PyPondoMobile\pypondo-web"

powershell -NoProfile -ExecutionPolicy Bypass -File ".\build_android.ps1"
set "EXIT_CODE=%errorlevel%"
popd
exit /b %EXIT_CODE%
