import time, wave, os
from piper import PiperVoice

MODEL      = r"C:\Kinect\piper\fr_FR-upmc-medium.onnx"
MODEL_JSON = r"C:\Kinect\piper\fr_FR-upmc-medium.onnx.json"
OUT        = r"C:\Kinect\piper\test_gpu.wav"
TEXT       = "Bonjour David, voici un test de vitesse avec le GPU activé."

print("Chargement modele...")
t = time.time()
voice = PiperVoice.load(MODEL, config_path=MODEL_JSON, use_cuda=True)
print(f"Load: {time.time()-t:.2f}s")

# 3 syntheses pour mesurer chaud
for i in range(3):
    t = time.time()
    with wave.open(OUT, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(voice.config.sample_rate)
        voice.synthesize_wav(TEXT, wf)
    sz = os.path.getsize(OUT) // 1024
    print(f"Synth #{i+1}: {time.time()-t:.2f}s ({sz}KB)")
