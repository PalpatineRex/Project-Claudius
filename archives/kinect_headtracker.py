"""
kinect_headtracker.py - Head tracking par centroide de zone tete
Pas de detection de visage - suit le centre de masse de la zone haute gauche
"""
import ctypes, ctypes.wintypes, cv2, numpy as np, time
from PIL import ImageGrab

USER32      = ctypes.WinDLL("user32")
SIGNAL_FILE = "C:\\\\Kinect\\\\head_signal.txt"
COOLDOWN    = 2.0
HIST_LEN    = 20

def find_colorbasics():
    result = [None]
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)
    def cb(hwnd, lp):
        buf = ctypes.create_unicode_buffer(256)
        USER32.GetWindowTextW(hwnd, buf, 256)
        if "Color Basics" in buf.value:
            result[0] = hwnd
        return True
    USER32.EnumWindows(CB(cb), 0)
    return result[0]

def get_bbox(hwnd):
    rect = ctypes.wintypes.RECT()
    USER32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (rect.left+5, rect.top+70, rect.right-5, rect.bottom-80)

def write_signal(sig):
    with open(SIGNAL_FILE, "w") as f:
        f.write(sig)
    print(f"[HeadTracker] SIGNAL: {sig}", flush=True)

def get_skin_centroid(frame):
    """Detecte la zone de peau et retourne le centroide Y"""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # Masque couleur peau (large pour couvrir eclairages varies)
    mask = cv2.inRange(hsv, np.array([0, 20, 50]), np.array([25, 180, 255]))
    # Focus sur la moitie gauche + haut de l image (la ou est la tete)
    h, w = mask.shape
    roi  = mask[:int(h*0.75), :int(w*0.65)]
    # Erosion pour enlever bruit
    kernel = np.ones((5,5), np.uint8)
    roi    = cv2.erode(roi, kernel, iterations=1)
    roi    = cv2.dilate(roi, kernel, iterations=2)
    M = cv2.moments(roi)
    if M["m00"] > 300:
        cy = M["m01"] / M["m00"]
        cx = M["m10"] / M["m00"]
        return cy, cx, M["m00"]
    return None, None, 0

def run():
    print("[HeadTracker] Demarrage...", flush=True)
    hwnd = None
    for _ in range(20):
        hwnd = find_colorbasics()
        if hwnd: break
        time.sleep(0.5)
    if not hwnd:
        print("[HeadTracker] ColorBasics introuvable!", flush=True)
        return
    print(f"[HeadTracker] OK hwnd={hwnd} - calibration 2s...", flush=True)
    time.sleep(2)

    cy_history  = []
    last_signal = 0
    frame_count = 0

    while True:
        try:
            hwnd = find_colorbasics()
            if not hwnd:
                time.sleep(0.5)
                continue

            bbox  = get_bbox(hwnd)
            img   = ImageGrab.grab(bbox=bbox)
            frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

            cy, cx, area = get_skin_centroid(frame)

            if cy is not None:
                cy_history.append(cy)
                frame_count += 1
                if frame_count % 60 == 0:
                    print(f"[HeadTracker] cy={cy:.0f} cx={cx:.0f} area={area:.0f}", flush=True)
            else:
                cy_history.append(None)

            while cy_history and cy_history[0] is None:
                cy_history.pop(0)
            if len(cy_history) > HIST_LEN:
                cy_history.pop(0)

            now   = time.time()
            valid = [v for v in cy_history if v is not None]

            if len(valid) >= HIST_LEN and (now - last_signal) > COOLDOWN:
                arr  = np.array(valid[-HIST_LEN:], dtype=float)
                rng  = arr.max() - arr.min()

                # OUI : cy descend (augmente) puis remonte - forme en U
                first4 = arr[:4].mean()
                mid4   = arr[HIST_LEN//2-2:HIST_LEN//2+2].mean()
                last4  = arr[-4:].mean()
                nod    = (mid4 - first4) > 15 and (mid4 - last4) > 10

                # NON : oscillations rapides
                diffs  = np.diff(arr)
                alts   = int(np.sum(diffs[:-1] * diffs[1:] < 0))
                shake  = alts >= 5 and rng > 18

                if nod:
                    write_signal("user_oui")
                    last_signal = now
                    cy_history.clear()
                elif shake:
                    write_signal("user_non")
                    last_signal = now
                    cy_history.clear()

        except Exception as e:
            print(f"[HeadTracker] Erreur: {e}", flush=True)

        time.sleep(0.033)

if __name__ == "__main__":
    run()
