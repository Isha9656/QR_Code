@echo off
title Stop Internal QR Management System

echo =======================================================
echo    STOPPING INTERNAL QR MANAGEMENT SYSTEM SERVERS
echo =======================================================
echo.

set FOUND=0

:: Stop Backend on port 8000
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :8000 ^| findstr LISTENING') do (
    echo [+] Stopping Backend process (PID: %%a)...
    taskkill /F /PID %%a >nul 2>&1
    set FOUND=1
)

:: Stop Frontend on port 5173
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :5173 ^| findstr LISTENING') do (
    echo [+] Stopping Frontend process (PID: %%a)...
    taskkill /F /PID %%a >nul 2>&1
    set FOUND=1
)

if "%FOUND%"=="0" (
    echo [i] No active servers found on ports 8000 or 5173.
) else (
    echo.
    echo [+] Successfully stopped all QR Management System servers.
)

echo.
pause
