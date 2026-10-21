@echo off
chcp 65001 >nul
set "ROOT=%~dp0"
for /f "usebackq tokens=1,* delims==" %%a in ("%ROOT%.env") do set "%%a=%%b"
set "PYTHONIOENCODING=utf-8"
cd /d "%ROOT%astrbot"
echo. >> "%ROOT%logs\astrbot-out.log"
echo ===== [%date% %time%] starting ===== >> "%ROOT%logs\astrbot-out.log"
"%ROOT%venv\Scripts\astrbot.exe" run >> "%ROOT%logs\astrbot-out.log" 2>&1
echo ===== [%date% %time%] exited, code=%errorlevel% >> "%ROOT%logs\astrbot-out.log"
