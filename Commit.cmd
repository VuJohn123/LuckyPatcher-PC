@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

REM ============================================================
REM Pre-flight: untrack junk files (safe, idempotent)
REM ============================================================
echo === Pre-flight: untrack junk ===

REM Untrack all .pyc files
for /f "delims=" %%f in ('git ls-files "*.pyc"') do (
    git rm --cached "%%f" >nul 2>&1
)
echo [OK] Untracked .pyc

REM Untrack legacy src/workspace (bug path)
git rm -r --cached src/workspace >nul 2>&1
echo [OK] Untracked src/workspace

REM Untrack stray log files
for /f "delims=" %%f in ('git ls-files "*_log.txt" "e2e*.txt" "e2e*.log"') do (
    git rm --cached "%%f" >nul 2>&1
)
echo [OK] Untracked logs

echo.
echo === Status ===
git status -s

echo.
set /p MSG=Commit message: 
if "%MSG%"=="" (
    echo [!] No commit message given. Aborting.
    pause
    exit /b 1
)

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

echo.
echo === Committing ===
git commit -m "%MSG%"
if errorlevel 1 (
    echo [!] Nothing to commit or commit failed.
    pause
    exit /b 1
)

echo.
echo === Pushing ===
git push origin main
if errorlevel 1 (
    echo [!] Push failed. You may need to pull/rebase first.
    pause
    exit /b 1
)

echo.
echo [OK] Done.
pause