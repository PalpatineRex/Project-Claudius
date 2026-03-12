"""
kinect_motor32.py - DOIT tourner en Python 32bit ou via SysWOW64
Reçoit commandes via stdin: "oui", "non", "reset", "angle:N"
"""
import ctypes, sys, time

try:
    K = ctypes.WinDLL(r"C:\Windows\SysWOW64\Kinect10.dll")
except:
    K = ctypes.WinDLL(r"C:\Windows\System32\Kinect10.dll")

K.NuiInitialize(0x00000001)

def tilt(deg):
    deg = max(-27, min(27, deg))
    K.NuiCameraElevationSetAngle(ctypes.c_long(deg))
    time.sleep(1.2)

def oui():
    tilt(15); tilt(-15); tilt(15); tilt(0)

def non():
    for _ in range(3):
        tilt(8); time.sleep(0.4)
        tilt(-8); time.sleep(0.4)
    tilt(0)

print("READY", flush=True)
for line in sys.stdin:
    cmd = line.strip()
    if cmd == "oui": oui(); print("OK:oui", flush=True)
    elif cmd == "non": non(); print("OK:non", flush=True)
    elif cmd == "reset": tilt(0); print("OK:reset", flush=True)
    elif cmd.startswith("angle:"): tilt(int(cmd.split(":")[1])); print("OK:angle", flush=True)
    elif cmd == "quit": break
