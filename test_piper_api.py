from piper.voice import PiperVoice
print([m for m in dir(PiperVoice) if not m.startswith("_")])
