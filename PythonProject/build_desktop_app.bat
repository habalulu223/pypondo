@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=..\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo The project virtual environment was not found at %PYTHON%.
  echo Create it, install requirements.txt, then run this script again.
  exit /b 1
)

"%PYTHON%" -c "import webview" >nul 2>&1
if errorlevel 1 (
  echo Installing the built-in desktop webview...
  "%PYTHON%" -m pip install pywebview
  if errorlevel 1 exit /b 1
)

"%PYTHON%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
  echo Installing PyInstaller...
  "%PYTHON%" -m pip install pyinstaller
  if errorlevel 1 exit /b 1
)

echo Building the independent Windows desktop application...
if not defined PYPONDO_MAIN_DB_SEED if exist "pccafe.db" set "PYPONDO_MAIN_DB_SEED=pccafe.db"
if not defined PYPONDO_COMMUNITY_DB_SEED (
  if exist "community_equipment.db" (
    set "PYPONDO_COMMUNITY_DB_SEED=community_equipment.db"
  ) else if exist "instance\community_equipment.db" (
    set "PYPONDO_COMMUNITY_DB_SEED=instance\community_equipment.db"
  )
)
"%PYTHON%" -m PyInstaller --noconfirm --clean PyPondo.spec
if errorlevel 1 (
  echo Desktop app build failed.
  exit /b 1
)

echo Building the server-connected desktop application...
set "PYPONDO_BUILD_ONLINE=1"
"%PYTHON%" -m PyInstaller --noconfirm --clean PyPondo.spec
if errorlevel 1 (
  set "PYPONDO_BUILD_ONLINE="
  echo Online desktop app build failed.
  exit /b 1
)
set "PYPONDO_BUILD_ONLINE="

echo Copying the system database files beside the standalone app...
if defined PYPONDO_MAIN_DB_SEED (
  copy /y "%PYPONDO_MAIN_DB_SEED%" "dist\pccafe.db" >nul
  if errorlevel 1 exit /b 1
)
if defined PYPONDO_COMMUNITY_DB_SEED (
  copy /y "%PYPONDO_COMMUNITY_DB_SEED%" "dist\community_equipment.db" >nul
  if errorlevel 1 exit /b 1
)
if exist "server_host.txt" copy /y "server_host.txt" "dist\server_host.txt" >nul

echo Creating a portable distribution archive with the database files...
if exist "dist\community_equipment.db" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -LiteralPath @('%~dp0dist\PyPondo.exe', '%~dp0dist\pccafe.db', '%~dp0dist\community_equipment.db') -DestinationPath '%~dp0dist\PyPondo-windows.zip' -Force"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -LiteralPath @('%~dp0dist\PyPondo.exe', '%~dp0dist\pccafe.db') -DestinationPath '%~dp0dist\PyPondo-windows.zip' -Force"
)
if errorlevel 1 exit /b 1
if exist "dist\server_host.txt" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -LiteralPath @('%~dp0dist\PyPondoOnline.exe', '%~dp0dist\server_host.txt') -DestinationPath '%~dp0dist\PyPondoOnline-windows.zip' -Force"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -LiteralPath '%~dp0dist\PyPondoOnline.exe' -DestinationPath '%~dp0dist\PyPondoOnline-windows.zip' -Force"
)
if errorlevel 1 exit /b 1

echo.
echo The standalone app is ready:
echo   %~dp0dist\PyPondo.exe
echo   %~dp0dist\PyPondo-windows.zip
echo The portable archive includes the current system database files.
echo The app runs a local PyPondo server when no shared server is reachable.
echo   %~dp0dist\PyPondoOnline.exe
echo   %~dp0dist\PyPondoOnline-windows.zip
echo The online app requires a reachable PyPondo server and never starts a local one.
endlocal
exit /b 0
