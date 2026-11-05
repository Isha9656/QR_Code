@echo off
setlocal enabledelayedexpansion
set "BACKEND_DIR=%~dp0"
if "%BACKEND_DIR:~-1%"=="\" set "BACKEND_DIR=%BACKEND_DIR:~0,-1%"
cd /d "%BACKEND_DIR%"
title QR Backend (FastAPI :8000)

echo =======================================================
echo          STARTING QR SYSTEM BACKEND (PORT 8000)
echo =======================================================
echo.

:: Detect Python executable
set "PYTHON_EXE="
if exist "%BACKEND_DIR%\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%BACKEND_DIR%\venv\Scripts\python.exe"
) else if exist "%BACKEND_DIR%\..\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%BACKEND_DIR%\..\venv\Scripts\python.exe"
) else (
    python --version >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=python"
    ) else (
        py --version >nul 2>&1
        if !errorlevel! equ 0 (
            set "PYTHON_EXE=py"
        ) else (
            set "PYTHON_EXE=python"
        )
    )
)

echo [+] Using Python: %PYTHON_EXE%
echo [+] Working Directory: %CD%
echo.

"%PYTHON_EXE%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

if !errorlevel! neq 0 (
    echo.
    echo [ERROR] Backend server stopped unexpectedly with exit code !errorlevel!.
    pause
)
