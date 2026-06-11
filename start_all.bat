@echo off
title Claudius - START ALL
cd /d "%~dp0"

echo [%time%] ===== CLAUDIUS START ALL =====
echo.

:: Arret CIBLE — ne tue QUE les process Claudius, par PID puis par ligne de
:: commande (l'ancien taskkill /im pythonw.exe massacrait TOUS les Python de
:: la machine : serveurs MCP, scripts en cours...)
for %%F in (bridge.pid voice.pid) do (
  if exist %%F (
    for /f "tokens=*" %%p in (%%F) do taskkill /f /pid %%p >nul 2>nul
  )
)
wmic process where "name='pythonw.exe' and commandline like '%%Kinect%%'" call terminate >nul 2>nul
wmic process where "name='python.exe' and commandline like '%%Kinect%%'" call terminate >nul 2>nul
taskkill /f /im KinectMotor.exe >nul 2>nul
ping -n 3 127.0.0.1 >nul

:: Nettoyer les lockfiles + stop flag
del /f /q cmd.txt motor_cmd.txt tts_speaking.lock claudius_sleep.lock 2>nul
del /f /q bridge.pid voice.pid 2>nul
del /f /q claudius_stop.flag 2>nul

echo [%time%] Lancement Bridge + Dashboard...
echo.

:: Lancer le Bridge (headless)
start /min "" pythonw KinectBridge.py

:: Attendre que le Bridge initialise
ping -n 6 127.0.0.1 >nul

:: Lancer le Dashboard (sans fenetre auto)
start /min "" pythonw KinectDashboard.py --no-window

echo [%time%] Claudius operationnel !
echo.
echo   Dashboard : http://localhost:5005
echo   Stop      : stop_claudius.bat
echo.
ping -n 6 127.0.0.1 >nul
