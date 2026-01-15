@echo off
REM Quick start script for Kia-Ai on Windows

echo ========================================
echo    Starting Kia-Ai WhatsApp Interface
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.9+ from https://www.python.org/
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
python -m pip install -r requirements.txt

echo.
echo [2/3] Starting FastAPI server...
echo.
echo Kia-Ai will be available at: http://localhost:8000
echo Press Ctrl+C to stop the server
echo.

python -m app.main

pause

