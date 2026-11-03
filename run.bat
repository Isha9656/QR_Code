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
    echo Please install Python 3.10+ and ensure "Add Python to PATH" is checked.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [+] Found %%v

:: 2. Check Node / npm
npm --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js / npm is not found in PATH!
    echo Please install Node.js (v18+) from https://nodejs.org/ and add to PATH.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('node --version 2^>^&1') do echo [+] Found Node %%v
for /f "tokens=*" %%v in ('npm --version 2^>^&1') do echo [+] Found npm v%%v

:: 3. Python executable detection
if exist "%~dp0backend\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0backend\venv\Scripts\python.exe"
    echo [+] Using backend virtual environment
) else if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
    echo [+] Using root virtual environment
) else (
    set "PYTHON_EXE=python"
)

:: 4. Verify / install backend dependencies
echo [+] Checking backend dependencies...
"%PYTHON_EXE%" -c "import fastapi, uvicorn, slowapi, sqlalchemy, qrcode, pydantic_settings, jose, passlib" >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Backend dependencies missing or incomplete.
    echo [+] Installing dependencies from backend\requirements.txt...
    "%PYTHON_EXE%" -m pip install -r "%~dp0backend\requirements.txt"
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install backend dependencies!
        pause
        exit /b 1
    )
    echo [+] Backend dependencies installed successfully.
) else (
    echo [+] Backend dependencies verified.
)

:: 5. Verify / install frontend dependencies
if not exist "%~dp0frontend\node_modules\" (
    echo [!] Frontend dependencies not found.
    echo [+] Running npm install in frontend directory...
    cd /d "%~dp0frontend"
    call npm install
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install frontend dependencies!
        pause
        exit /b 1
    )
    cd /d "%~dp0"
    echo [+] Frontend dependencies installed successfully.
) else (
    echo [+] Frontend dependencies verified.
)

:: 6. Clean up any stale processes on port 8000 or 5173 to avoid port collisions
echo [+] Checking for conflicting ports...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :8000 ^| findstr LISTENING') do (
    echo [!] Freeing busy port 8000 (PID: %%a)...
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :5173 ^| findstr LISTENING') do (
    echo [!] Freeing busy port 5173 (PID: %%a)...
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

:: 7. Launch Backend in separate window using dedicated script
start "QR Backend (FastAPI)" cmd /c ""%~dp0backend\start_backend.bat""

:: 8. Launch Frontend in separate window using dedicated script
start "QR Frontend (Vite)" cmd /c ""%~dp0frontend\start_frontend.bat""

:: 9. Wait briefly and open browser
echo [+] Waiting for services to initialize...
timeout /t 4 /nobreak >nul
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
