@echo off
REM ============================================================
REM run.bat — Launch LP-PC Suite GUI with .venv
REM ============================================================
REM Usage:
REM   run.bat           → chạy GUI
REM   run.bat test      → chạy pytest
REM   run.bat cli ...   → chạy CLI với args
REM ============================================================

setlocal

REM --- Chuyển về thư mục chứa script ---
cd /d "%~dp0"

REM --- Kiểm tra .venv tồn tại ---
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Khong tim thay .venv
    echo [INFO]  Tao venv bang lenh sau:
    echo         uv venv --python 3.11 --seed
    echo         uv pip install -r requirements.txt
    pause
    exit /b 1
)

REM --- Activate venv ---
call ".venv\Scripts\activate.bat"

REM --- Route theo tham số ---
if "%~1"=="" goto :run_gui
if /i "%~1"=="gui"  goto :run_gui
if /i "%~1"=="test" goto :run_test
if /i "%~1"=="cli"  goto :run_cli
if /i "%~1"=="e2e"  goto :run_e2e

REM Unknown command → show help
echo Usage:
echo   run.bat           Launch GUI
echo   run.bat test      Run pytest
echo   run.bat cli ...   Run CLI with args
echo   run.bat e2e ...   Run E2E test
exit /b 1

REM ============================================================
REM :run_gui — Launch GUI
REM ============================================================
:run_gui
echo [*] Launching LP-PC Suite GUI...
python src\run_gui.py
set EXIT_CODE=%ERRORLEVEL%
echo.
echo [i] GUI exited with code %EXIT_CODE%
pause
exit /b %EXIT_CODE%

REM ============================================================
REM :run_test — Run pytest
REM ============================================================
:run_test
echo [*] Running tests...
pytest --cov=src --cov-report=term-missing
set EXIT_CODE=%ERRORLEVEL%
pause
exit /b %EXIT_CODE%

REM ============================================================
REM :run_cli — Run CLI with shifted args
REM ============================================================
:run_cli
shift
echo [*] Running CLI: python src\main.py %*
python src\main.py %*
set EXIT_CODE=%ERRORLEVEL%
pause
exit /b %EXIT_CODE%

REM ============================================================
REM :run_e2e — Run E2E test
REM ============================================================
:run_e2e
shift
echo [*] Running E2E: python scripts\e2e_test.py %*
python scripts\e2e_test.py %*
set EXIT_CODE=%ERRORLEVEL%
pause
exit /b %EXIT_CODE%