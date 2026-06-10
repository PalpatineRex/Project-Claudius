@echo off
title Claudius - Stop
cd /d "%~dp0"
echo [%time%] Arret Claudius...
echo.

:: Creer le stop flag pour empecher l'auto-restart du dashboard
echo stopped > claudius_stop.flag

:: Tuer Bridge, Voice, Motor (mais PAS le dashboard)
taskkill /f /im KinectMotor.exe >nul 2>nul

:: Tuer les pythonw (Bridge + Voice) par PID pour ne pas tuer le dashboard Python
for /f "tokens=*" %%p in (bridge.pid) do taskkill /f /pid %%p >nul 2>nul
for /f "tokens=*" %%p in (voice.pid) do taskkill /f /pid %%p >nul 2>nul

:: Nettoyer les lockfiles
del /f /q cmd.txt motor_cmd.txt tts_speaking.lock claudius_sleep.lock 2>nul
del /f /q bridge.pid voice.pid 2>nul
del /f /q presence.txt 2>nul

echo [%time%] Claudius arrete (dashboard toujours actif).
timeout /t 3 /nobreak >nul
