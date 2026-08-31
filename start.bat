@echo off
setlocal
title AI Test Platform - Launcher
rem Prefer PowerShell 7 (pwsh) when installed; fallback to Windows PowerShell 5.1
where pwsh >nul 2>nul
if %errorlevel%==0 (
    pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
)
endlocal