@echo off
chcp 65001 >nul
cd /d "%~dp0napcat\versions\9.9.33-52230\resources\app"
set "PYTHONIOENCODING=utf-8"
echo. >> "%~dp0logs\napcat-out.log"
echo ===== [%date% %time%] starting ===== >> "%~dp0logs\napcat-out.log"
node.exe index.js -q <BOT_QQ> >> "%~dp0logs\napcat-out.log" 2>&1
echo ===== [%date% %time%] exited, code=%errorlevel% >> "%~dp0logs\napcat-out.log"
