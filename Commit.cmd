@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

REM ============================================================
REM Commit.cmd — LP-PC Suite
REM
REM Usage:
REM   Commit.cmd                  -> interactive prompt (1 line)
REM   Commit.cmd msg.txt          -> read message from file (multiline)
REM   Commit.cmd -m "one liner"   -> inline message
REM   Commit.cmd --no-push        -> commit only, skip push
REM ============================================================

set "MSG_FLAG="
set "MSG_VALUE="
set "DO_PUSH=1"

REM ---- Parse args ----
:parse_args
if "%~1"=="" goto parse_done
if /i "%~1"=="--no-push" (
    set "DO_PUSH=0"
    shift
    goto parse_args
)
if /i "%~1"=="-m" (
    set "MSG_FLAG=-m"
    set "MSG_VALUE=%~2"
    shift
    shift
    goto parse_args
)
REM Positional arg = file path
if exist "%~1" (
    set "MSG_FLAG=-F"
    set "MSG_VALUE=%~1"
    shift
    goto parse_args
)
echo [!] Unknown arg or file not found: %~1
pause
exit /b 1

:parse_done

REM ============================================================
REM Pre-flight: untrack junk files (safe, idempotent)
REM ============================================================
echo === Pre-flight: untrack junk ===

for /f "delims=" %%f in ('git ls-files "*.pyc"') do (
    git rm --cached "%%f" >nul 2>&1
)
echo [OK] Untracked .pyc

git rm -r --cached src/workspace >nul 2>&1
echo [OK] Untracked src/workspace

for /f "delims=" %%f in ('git ls-files "*_log.txt" "e2e*.txt" "e2e*.log"') do (
    git rm --cached "%%f" >nul 2>&1
)
echo [OK] Untracked logs

echo.
echo === Status ===
git status -s

REM ============================================================
REM Interactive message if no flag provided
REM ============================================================
if not "%MSG_FLAG%"=="" goto have_message

echo.
set /p MSG=Commit message: 
if "%MSG%"=="" (
    echo [!] No commit message given. Aborting.
    pause
    exit /b 1
)
set "MSG_FLAG=-m"
set "MSG_VALUE=%MSG%"

:have_message

echo.
echo === Staging ===
git add -A
if errorlevel 1 (
    echo [!] git add failed.
    pause
    exit /b 1
)

echo.
echo === Staged summary ===
git diff --cached --stat | findstr /R "changed"
if errorlevel 1 (
    echo [!] Nothing staged. Aborting.
    pause
    exit /b 1
)

echo.
echo === Committing ===
git commit %MSG_FLAG% "%MSG_VALUE%"
if errorlevel 1 (
    echo [!] Commit failed.
    pause
    exit /b 1
)

REM ============================================================
REM Push (unless --no-push)
REM ============================================================
if "%DO_PUSH%"=="0" (
    echo.
    echo [OK] Commit done. Push skipped (--no-push^).
    pause
    exit /b 0
)

echo.
echo === Pushing ===
git push origin main
if errorlevel 1 (
    echo.
    echo [!] Push rejected. Run:
    echo     git pull --rebase origin main
    echo     Commit.cmd --no-push
    echo     git push origin main
    pause
    exit /b 1
)

echo.
echo [OK] Done.
pause
endlocal