@echo off
setlocal
cd /d "%~dp0"
title QR Frontend (Vite :5173)

echo =======================================================
echo          STARTING QR SYSTEM FRONTEND (PORT 5173)
echo =======================================================
echo.

if not exist "node_modules\" (
    echo [!] node_modules not found. Installing dependencies via npm install...
    call npm install
    if %errorlevel% neq 0 (
        echo [ERROR] npm install failed!
        pause
        exit /b 1
    )
)

echo [+] Starting Vite development server...
call npm run dev

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Frontend dev server stopped unexpectedly with exit code %errorlevel%.
    pause
)
