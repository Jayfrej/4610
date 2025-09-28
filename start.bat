@echo off
title MT5 Trading Bot Server
color 0A

REM Change to script directory
cd /d "%~dp0"

echo ==========================================
echo   MT5 Trading Bot Server Starting...
echo ==========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ and try again
    echo.
    pause
    exit /b 1
)

REM Check if .env file exists
if not exist ".env" (
    echo ERROR: Configuration file .env not found
    echo Please run setup.py first to configure the bot
    echo.
    pause
    exit /b 1
)

REM Check if virtual environment exists and activate it
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
    echo Virtual environment activated
    echo.
)

REM Install/update dependencies if requirements.txt exists
if exist "requirements.txt" (
    echo Checking dependencies...
    pip install -r requirements.txt --quiet --disable-pip-version-check
    if errorlevel 1 (
        echo WARNING: Some dependencies may not be installed correctly
        echo.
    ) else (
        echo Dependencies are up to date
        echo.
    )
)

REM Check if server.py exists
if not exist "server.py" (
    echo ERROR: server.py not found
    echo Make sure you're running this from the correct directory
    echo.
    pause
    exit /b 1
)

echo Starting MT5 Trading Bot Server...
echo.
echo Web Interface: http://localhost:5000
echo Press Ctrl+C to stop the server
echo.
echo ==========================================

REM Start the server with automatic restart on crash
:restart
python server.py
set exit_code=%errorlevel%

if %exit_code% neq 0 (
    echo.
    echo ==========================================
    echo Server stopped unexpectedly (Exit Code: %exit_code%)
    echo ==========================================
    echo.
    
    choice /c YN /t 10 /d Y /m "Restart server? (Y/N, auto-restart in 10 seconds): "
    
    if errorlevel 2 (
        echo Server will not be restarted
        goto :end
    )
    
    echo Restarting server in 3 seconds...
    timeout /t 3 /nobreak >nul
    goto :restart
)

:end
echo.
echo ==========================================
echo   MT5 Trading Bot Server Stopped
echo ==========================================
echo.
pause
