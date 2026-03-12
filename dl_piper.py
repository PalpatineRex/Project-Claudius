"""Telecharge la voix Piper fr_FR-upmc-medium (Jessica)"""
import urllib.request
import json
import os

VOICE = "fr_FR-upmc-medium"
BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
OUT_DIR = r"C:\Kinect\piper"

files = [
    f"{VOICE}.onnx",
    f"{VOICE}.onnx.json",
]

for fname in files:
    url = f"{BASE_URL}/fr/fr_FR/upmc/medium/{fname}"
    dest = os.path.join(OUT_DIR, fname)
    if os.path.exists(dest):
        print(f"Deja present: {fname}")
        continue
    print(f"Telechargement: {fname}...")
    urllib.request.urlretrieve(url, dest)
    size = os.path.getsize(dest)
    print(f"OK: {fname} ({size//1024}KB)")

print("DONE")
