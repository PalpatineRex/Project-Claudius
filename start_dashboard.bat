@echo off
title Claudius Dashboard
cd /d "%~dp0"
echo [%time%] Lancement Dashboard Claudius...
echo.

:: Attendre que le Bridge soit pret (5s)
timeout /t 5 /nobreak >nul

:: Lancer le Dashboard
start /min "" pythonw KinectDashboard.py

echo [%time%] Dashboard lance sur http://localhost:5005
echo.
timeout /t 3 /nobreak >nul
