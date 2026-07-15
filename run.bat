@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo No se encontro el entorno virtual en .venv
    echo Creelo con: python -m venv .venv
    echo Luego instale las dependencias con: .venv\Scripts\pip install -r requeriments.txt
    echo.
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m src.main %*

echo.
echo Codigo de salida: %errorlevel%
echo.
pause

endlocal
