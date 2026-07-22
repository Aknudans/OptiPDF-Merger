@echo off
setlocal

cd /d "%~dp0"

:: Este script necesita permisos de Administrador (instala Python para todos
:: los usuarios y GhostScript/qpdf en Archivos de Programa). Si no los tiene,
:: se vuelve a lanzar a si mismo elevado, para pedir permisos una sola vez
:: en vez de uno por cada instalador.
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Este instalador necesita permisos de Administrador.
    echo Se va a volver a abrir pidiendo permisos elevados...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

set "INSTALLS=%~dp0installs"

if not exist "%INSTALLS%" (
    echo No se encontro la carpeta "installs" junto a este script.
    echo Coloca ahi los instaladores de Python, GhostScript y qpdf.
    echo.
    pause
    exit /b 1
)

echo ============================================
echo  Instalando Python
echo ============================================
set "PYTHON_INSTALLER="
for %%F in ("%INSTALLS%\python-*.exe") do set "PYTHON_INSTALLER=%%F"
if not defined PYTHON_INSTALLER (
    echo No se encontro un instalador de Python en "%INSTALLS%".
    echo Se espera un archivo tipo python-3.x.x-amd64.exe ^(el instalador oficial de python.org^).
) else (
    echo Usando: "%PYTHON_INSTALLER%"
    "%PYTHON_INSTALLER%" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
    if errorlevel 1 (
        echo AVISO: la instalacion de Python devolvio un error. Puede que ya este instalado,
        echo o intenta ejecutar el instalador manualmente haciendo doble clic en el.
    ) else (
        echo Python instalado correctamente.
    )
)

echo.
echo ============================================
echo  Instalando GhostScript
echo ============================================
set "GS_INSTALLER="
for %%F in ("%INSTALLS%\gs*.exe") do set "GS_INSTALLER=%%F"
if not defined GS_INSTALLER (
    echo No se encontro un instalador de GhostScript en "%INSTALLS%" ^(se espera un archivo tipo gs*.exe^).
) else (
    echo Usando: "%GS_INSTALLER%"
    "%GS_INSTALLER%" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
    if errorlevel 1 (
        echo AVISO: la instalacion de GhostScript devolvio un error.
        echo Intenta ejecutar el instalador manualmente haciendo doble clic en el.
    ) else (
        echo GhostScript instalado correctamente.
    )
)

echo.
echo ============================================
echo  Instalando qpdf
echo ============================================
set "QPDF_INSTALLER="
for %%F in ("%INSTALLS%\qpdf*.exe") do set "QPDF_INSTALLER=%%F"
if not defined QPDF_INSTALLER (
    echo No se encontro un instalador de qpdf en "%INSTALLS%" ^(se espera un archivo tipo qpdf*.exe^).
) else (
    echo Usando: "%QPDF_INSTALLER%"
    "%QPDF_INSTALLER%" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
    if errorlevel 1 (
        echo AVISO: la instalacion de qpdf devolvio un error.
        echo Intenta ejecutar el instalador manualmente haciendo doble clic en el.
    ) else (
        echo qpdf instalado correctamente.
    )
)

echo.
echo ============================================
echo  Instalacion terminada
echo ============================================
echo IMPORTANTE: cerra esta ventana y abri una nueva antes de usar run.bat o
echo run_gui.bat, para que Windows reconozca los programas recien instalados.
echo.
pause

endlocal
