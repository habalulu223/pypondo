@echo off
REM Quick Start Batch File for PyPondo
REM This script verifies the environment and runs the PyPondo apps independently

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
echo PyPondo - Independent App Quick Start
echo ============================================================
echo.

REM Check Python
"%PYTHON_CMD%" %PYTHON_ARGS% --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    echo Please install Python 3.8+ and add it to PATH
    pause
    exit /b 1
)

echo [OK] Python found
"%PYTHON_CMD%" %PYTHON_ARGS% --version

REM Check required packages.
REM Install from requirements.txt so the versions match what the app is tested
REM against. Installing individual package names here would resolve to whatever
REM is newest on PyPI and silently override the pins.
echo.
echo Checking required packages...
"%PYTHON_CMD%" %PYTHON_ARGS% -c "import flask; import flask_sqlalchemy; import flask_login; import flask_cors; import werkzeug; import qrcode; import PIL" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [INFO] Installing dependencies from requirements.txt...
    "%PYTHON_CMD%" %PYTHON_ARGS% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
)

echo [OK] All required packages available

REM Fail fast on a missing QR stack: the equipment and PC label endpoints
REM cannot work without qrcode and Pillow, and neither can mobile pairing.
"%PYTHON_CMD%" %PYTHON_ARGS% -c "import qrcode, PIL" >nul 2>&1
if errorlevel 1 (
    echo.
    echo WARNING: The QR code stack ^(qrcode + Pillow^) is not importable.
    echo WARNING: Equipment labels, PC labels, and mobile pairing QR codes will not work.
    echo Fix: "%PYTHON_CMD%" %PYTHON_ARGS% -m pip install -r requirements.txt
)

REM Smoke test: confirm the app module and its templates load before launching.
echo.
echo ============================================================
echo Running verification checks...
echo ============================================================
"%PYTHON_CMD%" %PYTHON_ARGS% -c "import app; from app import app as _a; _a.jinja_env.get_template('equipment_qr.html'); _a.jinja_env.get_template('error.html')" >nul 2>&1
if errorlevel 1 goto verify_failed
echo [OK] Application module imports and templates compile

REM Regression suite for the equipment/PC QR labels. pytest is a dev-only
REM dependency, so skip the suite (with a hint) instead of failing when absent.
"%PYTHON_CMD%" %PYTHON_ARGS% -c "import pytest" >nul 2>&1
if errorlevel 1 goto verify_skiptests
if not exist "test_equipment_qr.py" goto verify_skiptests
"%PYTHON_CMD%" %PYTHON_ARGS% test_equipment_qr.py
if errorlevel 1 goto verify_failed
echo [OK] Equipment and PC QR label regression checks passed
goto verify_done

:verify_skiptests
echo [INFO] Skipping QR regression checks (pytest or test_equipment_qr.py missing).
echo [INFO] To enable them: "%PYTHON_CMD%" %PYTHON_ARGS% -m pip install pytest
goto verify_done

:verify_failed
echo.
echo WARNING: PyPondo verification failed. Review the output above.
echo Re-run this script from the PythonProject folder, or run app.py directly
echo to see the full error.
echo Continue anyway? [Y/N]
set /p choice=
if /i "!choice!"=="Y" goto verify_done
exit /b 1

:verify_done

REM Menu
:menu
echo.
echo ============================================================
echo What would you like to do?
echo ============================================================
echo.
echo  1. Run Admin App (python app.py)
echo  2. Run Client App (python desktop_app.py)
echo  3. Configure Admin IP (independence mode)
echo  4. Run Both (in separate windows)
echo  5. Test Gateway Discovery Only
echo  6. Exit
echo.
set /p choice=Enter choice [1-6]:

if "!choice!"=="1" goto run_admin
if "!choice!"=="2" goto run_client
if "!choice!"=="3" goto configure_ip
if "!choice!"=="4" goto run_both
if "!choice!"=="5" goto test_gateway
if "!choice!"=="6" exit /b 0
echo Invalid choice, please try again.
goto menu

:run_admin
echo.
echo Starting Admin App on http://127.0.0.1:5000
echo.
"%PYTHON_CMD%" %PYTHON_ARGS% app.py
goto menu

:run_client
echo.
echo Starting Client App...
echo Client will auto-discover admin app via gateway
echo.
set PYPONDO_VERBOSE=1
"%PYTHON_CMD%" %PYTHON_ARGS% desktop_app.py
goto menu

:configure_ip
echo.
echo Configuring Admin Server IP (Independence Mode)...
echo This allows you to set the admin IP without the server running.
echo.
"%PYTHON_CMD%" %PYTHON_ARGS% desktop_app.py --independence
goto menu

:run_both
echo.
echo Starting Admin App in new window...
start cmd /k "\"%PYTHON_CMD%\" %PYTHON_ARGS% app.py"
timeout /t 2
echo.
echo Starting Client App...
set PYPONDO_VERBOSE=1
"%PYTHON_CMD%" %PYTHON_ARGS% desktop_app.py
goto menu

:test_gateway
echo.
echo Testing gateway discovery...
echo.
ipconfig | findstr /i "gateway"
echo.
if not errorlevel 1 (
    echo [SUCCESS] Gateway detected
) else (
    echo [WARNING] No gateway found or error reading ipconfig
)
echo.
pause
goto menu
