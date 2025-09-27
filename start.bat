@echo off
title MT5 Trading Bot Server
cd /d "%~dp0"

echo ========================================
echo    MT5 Trading Bot - Multi Account
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://python.org
    pause
    exit /b 1
)

REM Check if virtual environment exists
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
    echo Virtual environment activated
) else (
    echo No virtual environment found, using system Python
)

echo.
echo Checking configuration...

REM Check if .env file exists
if not exist ".env" (
    echo Error: Configuration file .env not found!
    echo Please run setup.py first to configure the bot.
    echo.
    echo Run: python setup.py
    pause
    exit /b 1
)

REM Check if required modules are installed
python -c "import flask, psutil, requests" >nul 2>&1
if errorlevel 1 (
    echo Error: Required modules not installed
    echo Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo Failed to install dependencies
        pause
        exit /b 1
    )
)

echo Configuration OK
echo.
echo Starting MT5 Trading Bot Server...
echo Press Ctrl+C to stop the server
echo.

REM Start the server
python server.py

REM If we get here, the server stopped
echo.
echo Server stopped.
pause