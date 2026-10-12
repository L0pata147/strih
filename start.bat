@echo off
setlocal
cd /d "%~dp0"
title Strih - odstraneni pozadi

rem UTF-8 pro vystup Pythonu, bez odesilani statistik Gradia
set "PYTHONUTF8=1"
set "GRADIO_ANALYTICS_ENABLED=False"
rem Vetsi mezipamet pro CUDA jadra kompilovana ovladacem (jinak se kompiluji pri kazdem startu)
set "CUDA_CACHE_MAXSIZE=4294967296"

rem Prenosna verze: Python je pribaleny ve slozce python\
if exist "python\python.exe" goto portable

set "VENV=.venv"
set "PY=%VENV%\Scripts\python.exe"

rem Instalace uz probehla -> rovnou spustit
if exist "%VENV%\.strih_installed" goto run

echo ============================================================
echo  Prvni spusteni: vytvarim prostredi a instaluji zavislosti.
echo  Muze to trvat nekolik minut (u GPU verze i dele).
echo ============================================================

if exist "%PY%" goto install

rem Preferuj Python 3.11 pres launcher "py", jinak "python" z PATH
where py >nul 2>nul
if not errorlevel 1 py -3.11 -m venv "%VENV%"
if exist "%PY%" goto install

where python >nul 2>nul
if errorlevel 1 goto nopython
echo Python 3.11 pres "py -3.11" nenalezen, zkousim "python" z PATH...
python -m venv "%VENV%"
if not exist "%PY%" goto nopython

:install
"%PY%" -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 11) else 1)"
if errorlevel 1 echo Upozorneni: venv nepouziva Python 3.11, aplikace je odladena pro 3.11.

"%PY%" install_deps.py
if errorlevel 1 (
    echo.
    echo CHYBA: Instalace zavislosti selhala. Zkontroluj pripojeni k internetu
    echo a spust start.bat znovu.
    pause
    exit /b 1
)
goto run

:portable
set "PY=python\python.exe"
rem Modely se ukladaji vedle aplikace do models\ (vychozi isnet-anime je uz pribaleny)
set "U2NET_HOME="
set "REMBG_HOME=%~dp0"
if not exist "python\.strih_installed" "%PY%" install_deps.py --portable

:run
echo Spoustim aplikaci, otevre se v prohlizeci. Ukonceni: zavri toto okno nebo Ctrl+C.
"%PY%" app.py %*
if errorlevel 1 pause
exit /b

:nopython
echo.
echo CHYBA: Python nenalezen. Nainstaluj Python 3.11 z https://www.python.org/downloads/
echo (pri instalaci zaskrtni "Add python.exe to PATH") a spust start.bat znovu.
pause
exit /b 1
