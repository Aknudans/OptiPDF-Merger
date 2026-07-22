@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo No se encontro el entorno virtual en .venv, creandolo ahora...

    where python >nul 2>&1
    if errorlevel 1 (
        echo No se encontro Python instalado en este equipo.
        echo Ejecuta install_dependencies.bat primero, o instala Python manualmente.
        echo.
        pause
        exit /b 1
    )

    python -m venv .venv
    if errorlevel 1 (
        echo No se pudo crear el entorno virtual en .venv.
        echo.
        pause
        exit /b 1
    )

    echo Entorno virtual creado. Instalando dependencias de requeriments.txt...
    ".venv\Scripts\pip.exe" install -r requeriments.txt
    if errorlevel 1 (
        echo No se pudieron instalar las dependencias.
        echo.
        pause
        exit /b 1
    )

    echo Dependencias instaladas correctamente.
    echo.
)

.venv\Scripts\python.exe -m src.webapp

echo.
echo Codigo de salida: %errorlevel%
echo.
pause

endlocal
