@echo off
REM Quick Start Batch File for PyPondo
REM This script tests and runs PyPondo apps independently

setlocal enabledelayedexpansion

echo.
echo ============================================================
echo PyPondo - Independent App Quick Start
echo ============================================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    echo Please install Python 3.8+ and add it to PATH
    pause
    exit /b 1
)

echo [OK] Python found
python --version

REM Check required packages
echo.
echo Checking required packages...
python -c "import flask; import flask_sqlalchemy; import flask_login; import werkzeug" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [INFO] Installing missing packages...
    pip install flask flask-sqlalchemy flask-login werkzeug
    if errorlevel 1 (
        echo ERROR: Failed to install packages
        pause
        exit /b 1
    )
)

echo [OK] All required packages available

REM Run tests
echo.
echo ============================================================
echo Running verification tests...
echo ============================================================
python test_independence.py
if errorlevel 1 (
    echo WARNING: Some tests failed
    echo Continue anyway? [Y/N]
    set /p choice=
    if /i not "!choice!"=="Y" exit /b 1
)

REM Menu
:menu
echo.
echo ============================================================
echo What would you like to do?
echo ============================================================
echo.
echo  1. Run Admin App (python app.py)
echo  2. Run Client App (python desktop_app.py)
echo  3. Run Both (in separate windows)
echo  4. View Documentation
echo  5. Test Gateway Discovery Only
echo  6. Exit
echo.
set /p choice=Enter choice [1-6]: 

if "!choice!"=="1" goto run_admin
if "!choice!"=="2" goto run_client
if "!choice!"=="3" goto run_both
if "!choice!"=="4" goto docs
if "!choice!"=="5" goto test_gateway
if "!choice!"=="6" exit /b 0
echo Invalid choice, please try again.
goto menu

:run_admin
echo.
echo Starting Admin App on http://127.0.0.1:5000
echo.
python app.py
goto menu

:run_client
echo.
echo Starting Client App...
echo Client will auto-discover admin app via gateway
echo.
set PYPONDO_VERBOSE=1
python desktop_app.py
goto menu

:run_both
echo.
echo Starting Admin App in new window...
start cmd /k "python app.py"
timeout /t 2
echo.
echo Starting Client App...
set PYPONDO_VERBOSE=1
python desktop_app.py
goto menu

:docs
echo.
echo Available Documentation:
echo.
echo  1. README_GATEWAY.md      - Complete reference guide
echo  2. INDEPENDENT_SETUP.md   - Step-by-step setup
echo  3. GATEWAY_DISCOVERY.md   - Technical details
echo  4. IMPLEMENTATION_SUMMARY.md - What changed
echo.
set /p doc_choice=Enter number [1-4] or press Enter to skip: 
if "!doc_choice!"=="1" type README_GATEWAY.md | more
if "!doc_choice!"=="2" type INDEPENDENT_SETUP.md | more
if "!doc_choice!"=="3" type GATEWAY_DISCOVERY.md | more
if "!doc_choice!"=="4" type IMPLEMENTATION_SUMMARY.md | more
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
