@echo off
title Knowledge Vault Setup
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo.
    echo Python was not found on this PC.
    echo.
    echo 1. Download Python 3.12 from https://www.python.org/downloads/
    echo 2. During install, tick "Add python.exe to PATH"
    echo 3. Run this file again after installing.
    echo.
    start https://www.python.org/downloads/
    pause
    exit /b 1
)

py -3.12 --version >nul 2>nul
if errorlevel 1 (
    echo.
    echo Python is installed, but not version 3.12 specifically.
    echo Download Python 3.12 from https://www.python.org/downloads/, install it,
    echo then run this file again.
    echo.
    start https://www.python.org/downloads/
    pause
    exit /b 1
)

py -3.12 setup_vault.py
pause
