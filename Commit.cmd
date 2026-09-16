@echo off
setlocal

cd /d "%~dp0"

echo === Status ===
git status -s

echo.
set /p MSG=Commit message: 
if "%MSG%"=="" (
    echo No commit message given. Aborting.
    pause
    exit /b 1
)

echo.
echo === Staging ===
git add .
if errorlevel 1 (
    echo git add failed.
    pause
    exit /b 1
)

echo.
echo === Committing ===
git commit -m "%MSG%"
if errorlevel 1 (
    echo Nothing to commit or commit failed.
    pause
    exit /b 1
)

echo.
echo === Pushing ===
git push origin main
if errorlevel 1 (
    echo Push failed. You may need to pull/rebase first.
    pause
    exit /b 1
)

echo.
echo Done.
pause