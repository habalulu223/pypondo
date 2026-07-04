@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD=py"
set "PYTHON_ARGS=-3"

where py >nul 2>&1
if errorlevel 1 (
  set "PYTHON_CMD=python"
  set "PYTHON_ARGS="
  where python >nul 2>&1
  if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" (
      set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
      set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
      set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
      set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    ) else if exist "%PROGRAMFILES%\Python314\python.exe" (
      set "PYTHON_CMD=%PROGRAMFILES%\Python314\python.exe"
    ) else if exist "%PROGRAMFILES%\Python313\python.exe" (
      set "PYTHON_CMD=%PROGRAMFILES%\Python313\python.exe"
    ) else if exist "%PROGRAMFILES%\Python312\python.exe" (
      set "PYTHON_CMD=%PROGRAMFILES%\Python312\python.exe"
    ) else if exist "%PROGRAMFILES%\Python311\python.exe" (
      set "PYTHON_CMD=%PROGRAMFILES%\Python311\python.exe"
    ) else (
      echo Python was not found. Please install Python 3 and try again.
      pause >nul
      exit /b 1
    )
  )
)

echo.
echo ============================================================
echo PyPondo Client Application
echo ============================================================
echo.

echo Running client auto-discovery and launching desktop app...
echo.
if /I "%PYTHON_CMD%"=="py" (
  py -3 configure_client.py --launch
) else if /I "%PYTHON_CMD%"=="python" (
  python configure_client.py --launch
) else (
  "%PYTHON_CMD%" configure_client.py --launch
)

if errorlevel 1 (
  echo.
  echo The desktop app exited with a non-zero status.
  echo Press any key to close this window.
  pause >nul
)

endlocal
