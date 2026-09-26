@echo off
setlocal
cd /d "%~dp0"

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python not found. Please ensure Python is installed and added to PATH.
    pause
    exit /b 1
)

python GUI\app.py
if %errorlevel% neq 0 (
    echo.
    echo GUI exited with an error.
    pause
)
