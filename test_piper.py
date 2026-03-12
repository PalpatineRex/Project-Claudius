"""Test Piper TTS Jessica - API correcte"""
import time, os, subprocess, wave

MODEL      = r"C:\Kinect\piper\fr_FR-upmc-medium.onnx"
MODEL_JSON = r"C:\Kinect\piper\fr_FR-upmc-medium.onnx.json"
OUT        = r"C:\Kinect\piper\test.wav"
TEXT       = "Bonjour David, je suis Claudius. Ma nouvelle voix est bien meilleure, non ?"

t = time.time()
try:
    from piper import PiperVoice
    voice = PiperVoice.load(MODEL, config_path=MODEL_JSON)

    with wave.open(OUT, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(voice.config.sample_rate)
        voice.synthesize_wav(TEXT, wf)

    size = os.path.getsize(OUT)
    print(f"Generation: {time.time()-t:.2f}s, WAV: {size//1024}KB")

    subprocess.call([
        "powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
        "-c", f"(New-Object Media.SoundPlayer '{OUT}').PlaySync()"
    ])
    print("PLAY OK")
except Exception as e:
    import traceback; traceback.print_exc()
