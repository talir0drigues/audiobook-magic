@echo off
cd /d "%~dp0"

echo.
echo === Audiobook Downloader ===
echo.

:: --- uv ---
where uv >nul 2>&1
if errorlevel 1 (
    echo Installing uv (Python manager)...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
)

where uv >nul 2>&1
if errorlevel 1 (
    echo Could not install uv. Please install it manually: https://docs.astral.sh/uv/
    pause
    exit /b 1
)

:: --- FFmpeg ---
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo FFmpeg not found. Installing via winget...
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo Could not install FFmpeg. Please install it manually: https://ffmpeg.org/
    pause
    exit /b 1
)

:: --- Run ---
uv run main.py

pause
