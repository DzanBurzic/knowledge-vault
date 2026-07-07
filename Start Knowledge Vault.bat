@echo off
title Knowledge Vault
cd /d "%~dp0"

py -3.12 --version >nul 2>nul
if errorlevel 1 (
    echo.
    echo Python 3.12 was not found. Run "Setup Knowledge Vault.bat" first.
    echo.
    pause
    exit /b 1
)

py -3.12 run_app.py
if errorlevel 1 pause
