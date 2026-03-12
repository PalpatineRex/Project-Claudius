from piper import PiperVoice
import inspect
print(inspect.signature(PiperVoice.synthesize))
# Verifier aussi les methodes disponibles
methods = [m for m in dir(PiperVoice) if not m.startswith('_')]
print("Methods:", methods)
