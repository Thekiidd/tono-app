@echo off
title Tono — Reproductor Universal de Música
color 09

echo ===================================================
echo               TONO - REPRODUCTOR UNIVERSAL
echo         Almacenamiento: Disco D (D:\SpotyStream)
echo ===================================================
echo.

cd /d "D:\SpotyStream\backend"

echo [1/2] Verificando motor de Tono en segundo plano...
netstat -ano | findstr :8000 >nul
if %errorlevel% neq 0 (
    echo [2/2] Iniciando Servidor Tono Core...
    start /min "Tono Core Engine" "D:\SpotyStream\backend\venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000
    timeout /t 3 /nobreak >nul
) else (
    echo [2/2] Servidor Tono ya activo en puerto 8000.
)

echo Abriendo Tono en tu navegador...
start http://127.0.0.1:8000/

echo.
echo ===================================================
echo   Tono esta activo en http://127.0.0.1:8000
echo   Presiona cualquier tecla para cerrar esta ventana.
echo ===================================================
pause >nul
