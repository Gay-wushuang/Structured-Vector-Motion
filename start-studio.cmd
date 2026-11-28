@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    python -B -m svm.studio --open %*
) else (
    py -3 -B -m svm.studio --open %*
)
if errorlevel 1 pause
