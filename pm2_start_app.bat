@echo off
setlocal

set "ROOT=C:\Users\vaccum loop3\Desktop\Pirani Guage Application\WRL-Pirani-Gauge-Dashboard"
set "CLIENT=%ROOT%\client"

cd /d "%ROOT%" || exit /b 1

REM Build the frontend
cd /d "%CLIENT%" || exit /b 1
call npm run build
if errorlevel 1 exit /b 1

cd /d "%ROOT%" || exit /b 1

REM Check that PM2 is installed
where pm2 >nul 2>&1
if errorlevel 1 (
    call npm install -g pm2
    if errorlevel 1 exit /b 1
)

REM Start Python app under PM2 if not already registered
call pm2 describe pirani-dashboard >nul 2>&1
if errorlevel 1 (
    call pm2 start "%ROOT%\app.py" --name pirani-dashboard --interpreter python --restart-delay 5000
) else (
    call pm2 restart pirani-dashboard
)

REM Save process list for future restoration
call pm2 save

echo.
echo Pirani Gauge Dashboard is running in the background.
echo Check status with: pm2 list
echo View logs with: pm2 logs pirani-dashboard
echo.
exit /b 0
