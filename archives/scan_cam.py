import cv2
for i in range(6):
    cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
    if cap.isOpened():
        ret, f = cap.read()
        mean = round(f.mean(), 1) if ret and f is not None else "no frame"
        print(f"index {i}: {mean}")
        cap.release()
    else:
        print(f"index {i}: closed")
