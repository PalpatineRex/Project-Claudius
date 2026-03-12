@echo off
start "" /MIN "C:\Python314\pythonw.exe" "C:\Kinect\KinectBridge.py"
timeout /t 3 /nobreak >nul
start "" /MIN "C:\Python314\pythonw.exe" "C:\Kinect\KinectVoice.py"
timeout /t 1 /nobreak >nul
start "" /MIN "C:\Python314\pythonw.exe" "C:\Kinect\KinectTranscript.py"
