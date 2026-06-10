@echo off
title Claudius - Restart
cd /d "%~dp0"
echo [%time%] Redemarrage Claudius...
echo.

:: Arret propre
call stop_claudius.bat

echo.
echo [%time%] Relance...
echo.

:: Supprimer le stop flag
del /f /q claudius_stop.flag 2>nul

:: Redemarrer le Bridge en pythonw (silencieux)
start /min "" pythonw KinectBridge.py

:: Lancer le Dashboard aussi
timeout /t 3 /nobreak >nul
start /min "" pythonw KinectDashboard.py --no-window

echo [%time%] Claudius relance.
echo.
echo Pour verifier : http://localhost:5005
timeout /t 5 /nobreak >nul
