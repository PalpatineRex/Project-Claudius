"""
KinectTTS.py - Synthese vocale pour Claudius
Mode piper: voix Jessica (fr_FR-upmc-medium) locale, chargee une fois
Mode local: pyttsx3 Hortense (fallback si piper absent)
Mode neural: edge-tts Henri Neural (fallback internet)
Usage: python KinectTTS.py "texte" [--local|--neural]
"""
import sys, time, os, subprocess, wave

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_KINECT_DIR = os.environ.get("CLAUDIUS_KINECT_DIR", _SCRIPT_DIR)
_DATA_DIR   = os.environ.get("CLAUDIUS_DATA_DIR", _SCRIPT_DIR)

LOG_FILE         = os.path.join(_DATA_DIR, "kinect.log")
PIPER_MODEL      = os.path.join(_KINECT_DIR, "piper", "fr_FR-upmc-medium.onnx")
PIPER_MODEL_JSON = os.path.join(_KINECT_DIR, "piper", "fr_FR-upmc-medium.onnx.json")
PIPER_WAV        = os.path.join(_DATA_DIR, "tts_tmp.wav")
PIPER_MP3        = os.path.join(_DATA_DIR, "tts_tmp.mp3")
VOICE_INDEX      = 0  # pyttsx3: 0=Hortense FR

def _log(msg):
    line = "[TTS " + time.strftime("%H:%M:%S") + "] " + msg
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def speak_piper(text):
    """Piper TTS local - voix Jessica. Charge le modele a chaque appel (subprocess)."""
    try:
        from piper import PiperVoice
        voice = PiperVoice.load(PIPER_MODEL, config_path=PIPER_MODEL_JSON)
        with wave.open(PIPER_WAV, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(voice.config.sample_rate)
            voice.synthesize_wav(text, wf)
        subprocess.call([
            "powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
            "-c", f"(New-Object Media.SoundPlayer '{PIPER_WAV}').PlaySync()"
        ])
        try: os.remove(PIPER_WAV)
        except: pass
    except Exception as e:
        _log("ERR piper: " + str(e) + " -> fallback local")
        speak_local(text)

def speak_local(text):
    """pyttsx3 SAPI Windows - Hortense FR, instantane, hors ligne."""
    import pyttsx3
    engine = pyttsx3.init()
    voices = engine.getProperty("voices")
    if VOICE_INDEX < len(voices):
        engine.setProperty("voice", voices[VOICE_INDEX].id)
    engine.setProperty("rate", 165)
    engine.setProperty("volume", 1.0)
    engine.say(text)
    engine.runAndWait()

def speak_neural(text):
    """edge-tts Neural Henri - meilleure qualite, necessite internet."""
    import asyncio, edge_tts
    VOICE = "fr-FR-HenriNeural"
    async def _gen():
        await edge_tts.Communicate(text, VOICE).save(PIPER_MP3)
    asyncio.run(_gen())
    mp3 = PIPER_MP3.replace("\\", "/")
    script = (
        "Add-Type -AssemblyName presentationCore; "
        "$m = New-Object System.Windows.Media.MediaPlayer; "
        "$m.Open([uri]::new('" + mp3 + "')); $m.Play(); "
        "Start-Sleep -Milliseconds 500; "
        "while ($m.NaturalDuration.HasTimeSpan -eq $false) { Start-Sleep -Milliseconds 50 }; "
        "$dur = [int]($m.NaturalDuration.TimeSpan.TotalMilliseconds) + 300; "
        "Start-Sleep -Milliseconds $dur; $m.Stop(); $m.Close()"
    )
    subprocess.call(
        ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-c", script],
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    try: os.remove(PIPER_MP3)
    except: pass

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: KinectTTS.py <texte> [--local|--neural]")
        sys.exit(1)
    flags = {"--local", "--neural"}
    mode_args = [a for a in sys.argv[1:] if a in flags]
    text_args = [a for a in sys.argv[1:] if a not in flags]
    text = " ".join(text_args)
    mode = mode_args[0] if mode_args else "--piper"

    _log(f"{mode}: {text[:60]}")
    t = time.time()
    if mode == "--neural":
        speak_neural(text)
    elif mode == "--local":
        speak_local(text)
    else:
        speak_piper(text)  # defaut = Jessica
    _log(f"TTS done en {time.time()-t:.1f}s")
