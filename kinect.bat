@echo off
if "%1"=="blink" goto nocolorbasics
if "%1"=="think" goto nocolorbasics
taskkill /F /IM ColorBasics-WPF.exe >nul 2>&1
ping -n 2 127.0.0.1 >nul
C:\Kinect\KinectMotor.exe %1
goto end
:nocolorbasics
C:\Kinect\KinectMotor.exe %1
:end
