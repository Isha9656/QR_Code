@echo off
title Database Restore Tool - Internal QR Management System
echo =======================================================
echo     INTERNAL QR MANAGEMENT SYSTEM - DATABASE RESTORE
echo =======================================================
echo.
echo [!] IMPORTANT: The backend server MUST be stopped before restoring!
echo     Run stop.bat first if the server is currently running.
echo.
pause

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
cd /d "%ROOT_DIR%\backend"
if exist "%ROOT_DIR%\backend\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT_DIR%\backend\venv\Scripts\python.exe"
) else if exist "%ROOT_DIR%\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT_DIR%\venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" restore_database.py %1

echo.
pause
