@echo off
:: Lance le Bridge SEUL (sans dashboard) — chemins relatifs au dossier courant
:: (l'ancienne version pointait C:\Kinect\, mort depuis le demenagement)
cd /d "%~dp0"
start "" /MIN pythonw KinectBridge.py
