@echo off
setlocal enabledelayedexpansion
title Internal QR Management System - Launcher

echo =======================================================
echo       INTERNAL QR MANAGEMENT SYSTEM - LAUNCHER
echo =======================================================
echo.

cd /d "%~dp0"

:: 1. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not found in PATH!
    echo Please install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [+] Found %%v

:: 2. Check Node / npm
npm --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] npm is not found in PATH!
    echo Please install Node.js and add it to PATH.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('node --version 2^>^&1') do echo [+] Found Node %%v

:: 3. Python Virtualenv / Command detection
if exist "backend\venv\Scripts\activate.bat" (
    echo [+] Activating backend venv...
    set "PY_CMD=call "%~dp0backend\venv\Scripts\activate.bat" && python"
) else if exist "venv\Scripts\activate.bat" (
    echo [+] Activating root venv...
    set "PY_CMD=call "%~dp0venv\Scripts\activate.bat" && python"
) else (
    set "PY_CMD=python"
)

:: 4. Frontend node_modules check
if not exist "frontend\node_modules\" (
    echo [!] Frontend dependencies not found. Installing via npm install...
    cd /d "%~dp0frontend"
    call npm install
    if %errorlevel% neq 0 (
        echo [ERROR] npm install failed!
        pause
        exit /b 1
    )
    cd /d "%~dp0"
)

echo.
echo =======================================================
echo   Launching Services:
echo     Frontend App : http://localhost:5173
echo     Backend API  : http://localhost:8000
echo     Swagger Docs : http://localhost:8000/api/docs
echo =======================================================
echo.

:: 5. Launch Backend in separate window
start "QR Backend (FastAPI)" cmd /k "title QR Backend (FastAPI :8000) ^& cd /d "%~dp0backend" ^& %PY_CMD% -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

:: 6. Launch Frontend in separate window
start "QR Frontend (Vite)" cmd /k "title QR Frontend (Vite :5173) ^& cd /d "%~dp0frontend" ^& npm run dev"

:: 7. Wait briefly and open browser
echo [+] Waiting for services to initialize...
timeout /t 3 /nobreak >nul
start http://localhost:5173

echo.
echo [+] Internal QR Management System is running!
echo [+] Backend and Frontend are running in separate terminal windows.
echo [+] Run stop.bat or close the windows to stop the servers.
echo.
pause
