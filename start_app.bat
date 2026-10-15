@echo off

cd /d "C:\Users\vaccum loop3\Desktop\Pirani Guage Application\WRL-Pirani-Gauge-Dashboard\client"
call npm run build

cd /d "C:\Users\vaccum loop3\Desktop\Pirani Guage Application\WRL-Pirani-Gauge-Dashboard"
python app.py
