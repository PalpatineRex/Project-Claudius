import ctypes, time, sys

K = ctypes.WinDLL(r"C:\Windows\System32\Kinect10.dll")
K.NuiInitialize(0x00000001)

def tilt(deg):
    deg = max(-27, min(27, int(deg)))
    r = K.NuiCameraElevationSetAngle(ctypes.c_long(deg))
    print(f"tilt({deg}) code={r}", flush=True)
    time.sleep(1.8)

def get_angle():
    a = ctypes.c_long(0)
    K.NuiCameraElevationGetAngle(ctypes.byref(a))
    return a.value

mode = sys.argv[1] if len(sys.argv) > 1 else "oui"
print(f"Angle actuel: {get_angle()}", flush=True)

if mode == "oui":
    print("=== OUI (haut/bas max) ===", flush=True)
    tilt(27)
    tilt(-27)
    tilt(27)
    tilt(0)
elif mode == "non":
    print("=== NON (oscillation rapide) ===", flush=True)
    for _ in range(4):
        tilt(27)
        time.sleep(0.3)
        tilt(-27)
        time.sleep(0.3)
    tilt(0)
elif mode == "test_angle":
    deg = int(sys.argv[2])
    print(f"=== TEST angle {deg} ===", flush=True)
    tilt(deg)
    time.sleep(1)
    tilt(0)

print(f"Angle final: {get_angle()}", flush=True)
