
@echo off
title Pirani Gauge Dashboard

cd /d "C:\Users\vaccum loop3\Desktop\Pirani Guage Application\WRL-Pirani-Gauge-Dashboard\client"

call npm run build

if errorlevel 1 exit /b 1

cd /d "C:\Users\vaccum loop3\Desktop\Pirani Guage Application\WRL-Pirani-Gauge-Dashboard"

:RESTART
python app.py

echo Application stopped. Restarting in 5 seconds...
timeout /t 5 /nobreak >nul
goto RESTART
