@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0open-webui.ps1"
timeout /t 2 >nul
