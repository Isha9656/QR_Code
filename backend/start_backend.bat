@echo off
setlocal
cd /d "%~dp0"
title QR Backend (FastAPI :8000)

echo =======================================================
echo          STARTING QR SYSTEM BACKEND (PORT 8000)
echo =======================================================
echo.

:: Detect Python executable / virtual environment
if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else if exist "..\venv\Scripts\python.exe" (
    set "PYTHON_EXE=..\venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [+] Using Python: %PYTHON_EXE%
echo [+] Working Directory: %CD%
echo.

:: Run backend server with auto-reload
%PYTHON_EXE% -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Backend server stopped unexpectedly with exit code %errorlevel%.
    pause
)
