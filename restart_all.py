import subprocess, time, os, ctypes

k = ctypes.windll.kernel32

# Kill all Motors
os.system("taskkill /f /im KinectMotor.exe 2>nul")
time.sleep(1)

# Kill Bridge + Voice via PID files
for pf in [r"C:\Kinect\bridge.pid", r"C:\Kinect\voice.pid"]:
    try:
        pid = int(open(pf).read().strip())
        h = k.OpenProcess(1, False, pid)
        if h:
            k.TerminateProcess(h, 0)
            k.CloseHandle(h)
            print(f"Killed PID {pid}")
    except:
        pass

# Clean all lock/state files
for f in ["tts_speaking.lock", "claudius_sleep.lock", "cmd.txt", "motor_cmd.txt",
           "voice.pid", "bridge.pid", "voice_heartbeat.txt"]:
    try: os.remove(os.path.join(r"C:\Kinect", f))
    except: pass
print("Cleaned")

time.sleep(2)

# Relaunch Bridge
subprocess.Popen(
    ["pythonw", r"C:\Kinect\KinectBridge.py"],
    creationflags=subprocess.CREATE_NO_WINDOW,
    cwd=r"C:\Kinect",
    close_fds=True
)
print("Bridge launched, waiting 25s...")
time.sleep(25)

# Check
lines = open(r"C:\Kinect\kinect.log", "r", encoding="utf-8", errors="replace").readlines()
recent = [l.rstrip() for l in lines if "MOTOR" in l or "daemon" in l or "legacy" in l or "demarrage" in l or "WATCHDOG" in l or "pret" in l.lower()]
print("--- Recent key lines ---")
for l in recent[-15:]:
    print(l)
