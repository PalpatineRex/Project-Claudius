@echo off
title Claudius - START ALL
cd /d "%~dp0"

echo [%time%] ===== CLAUDIUS START ALL =====
echo.

:: Arret propre au cas ou
taskkill /f /im pythonw.exe >nul 2>nul
taskkill /f /im python.exe >nul 2>nul
taskkill /f /im KinectMotor.exe >nul 2>nul
timeout /t 2 /nobreak >nul

:: Nettoyer les lockfiles + stop flag
del /f /q cmd.txt motor_cmd.txt tts_speaking.lock claudius_sleep.lock 2>nul
del /f /q bridge.pid voice.pid 2>nul
del /f /q claudius_stop.flag 2>nul

echo [%time%] Lancement Bridge + Dashboard...
echo.

:: Lancer le Bridge (headless)
start /min "" pythonw KinectBridge.py

:: Attendre que le Bridge initialise
timeout /t 5 /nobreak >nul

:: Lancer le Dashboard (sans fenetre auto)
start /min "" pythonw KinectDashboard.py --no-window

echo [%time%] Claudius operationnel !
echo.
echo   Dashboard : http://localhost:5005
echo   Stop      : stop_claudius.bat
echo.
timeout /t 5 /nobreak >nul
