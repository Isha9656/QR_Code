@echo off
setlocal enabledelayedexpansion
title Internal QR Management System - Launcher

echo =======================================================
echo       INTERNAL QR MANAGEMENT SYSTEM - LAUNCHER
echo =======================================================
echo.

:: Get directory of this script and strip any trailing backslash
set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
cd /d "%ROOT_DIR%"

:: 1. Detect Python executable
set "PYTHON_EXE="
if exist "%ROOT_DIR%\backend\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT_DIR%\backend\venv\Scripts\python.exe"
    echo [+] Using backend virtual environment Python
) else if exist "%ROOT_DIR%\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT_DIR%\venv\Scripts\python.exe"
    echo [+] Using root virtual environment Python
) else (
    python --version >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=python"
    ) else (
        py --version >nul 2>&1
        if !errorlevel! equ 0 (
            set "PYTHON_EXE=py"
        )
    )
)

if "%PYTHON_EXE%"=="" (
    echo [ERROR] Python is not found in PATH or virtual environment!
    echo Please install Python 3.10+ from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('"%PYTHON_EXE%" --version 2^>^&1') do echo [+] Found %%v

:: 2. Check Node / npm (MUST use call npm to avoid exiting batch script)
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not found in PATH!
    echo Please install Node.js v18 or higher from https://nodejs.org/ and add to PATH.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('node --version 2^>^&1') do echo [+] Found Node %%v

call npm --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] npm is not found in PATH!
    echo Please install Node.js v18 or higher from https://nodejs.org/
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('call npm --version 2^>^&1') do echo [+] Found npm v%%v

:: 3. Verify / install backend dependencies
echo [+] Checking backend dependencies...
"%PYTHON_EXE%" -c "import fastapi, uvicorn, slowapi, sqlalchemy, qrcode, pydantic_settings, jose, passlib" >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Backend dependencies missing or incomplete.
    echo [+] Installing dependencies from backend\requirements.txt...
    "%PYTHON_EXE%" -m pip install -r "%ROOT_DIR%\backend\requirements.txt"
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install backend dependencies!
        pause
        exit /b 1
    )
    echo [+] Backend dependencies installed successfully.
) else (
    echo [+] Backend dependencies verified.
)

:: 4. Verify / install frontend dependencies
if not exist "%ROOT_DIR%\frontend\node_modules" (
    echo [!] Frontend dependencies not found.
    echo [+] Running npm install in frontend directory...
    cd /d "%ROOT_DIR%\frontend"
    call npm install
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install frontend dependencies!
        pause
        exit /b 1
    )
    cd /d "%ROOT_DIR%"
    echo [+] Frontend dependencies installed successfully.
) else (
    echo [+] Frontend dependencies verified.
)

:: 5. Clean up any stale processes on port 8000 or 5173 to avoid port collisions
echo [+] Checking for conflicting ports...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :8000 ^| findstr LISTENING') do (
    echo [!] Freeing busy port 8000 - PID %%a
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :5173 ^| findstr LISTENING') do (
    echo [!] Freeing busy port 5173 - PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo =======================================================
echo   Launching Services:
echo     Frontend App : http://localhost:5173
echo     Backend API  : http://localhost:8000
echo     Swagger Docs : http://localhost:8000/api/docs
echo =======================================================
echo.

:: 6. Launch Backend in separate window using dedicated script
start "QR Backend (FastAPI)" /d "%ROOT_DIR%\backend" cmd /k "start_backend.bat"

:: 7. Launch Frontend in separate window using dedicated script
start "QR Frontend (Vite)" /d "%ROOT_DIR%\frontend" cmd /k "start_frontend.bat"

:: 8. Wait briefly and open browser
echo [+] Waiting for services to initialize...
ping 127.0.0.1 -n 5 >nul
start http://localhost:5173

echo.
echo =======================================================
echo   QR Management System is now running!
echo   - Backend API  : http://localhost:8000
echo   - Frontend PWA : http://localhost:5173
echo.
echo   To STOP the system, run stop.bat or close
echo   the Backend and Frontend terminal windows.
echo =======================================================
echo.
pause
