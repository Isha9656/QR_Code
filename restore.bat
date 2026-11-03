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

cd /d "%~dp0backend"
if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else if exist "..\venv\Scripts\python.exe" (
    set "PYTHON_EXE=..\venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

%PYTHON_EXE% restore_database.py %1

echo.
pause
