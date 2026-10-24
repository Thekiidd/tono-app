@echo off
title SpotyStream Backend
cd /d "D:\SpotyStream\backend"
echo Starting SpotyStream Python Engine on http://127.0.0.1:8000...
venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
