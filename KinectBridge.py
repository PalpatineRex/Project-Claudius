"""
KinectBridge.py - Pont Kinect, demarre avec Windows
LLM: Ollama local (llama3.2:3b) - gratuit, hors ligne
TTS: Piper Jessica charge en memoire au boot (~1s par synthese)
Commandes: oui/non/blink/hello/think/reset/snap + VOICE:texte
"""
import subprocess, os, time, threading, random, json, wave
import urllib.request

MOTOR_EXE        = r"C:\Kinect\KinectMotor.exe"
TTS_PY           = r"C:\Kinect\KinectTTS.py"
CMD_FILE         = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\cmd.txt"
LOG_FILE         = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\kinect.log"
PYTHON           = r"C:\Python314\python.exe"
OLLAMA_URL       = "http://localhost:11434/api/chat"
OLLAMA_MDL       = "llama3.2:3b"
PIPER_MODEL      = r"C:\Kinect\piper\fr_FR-upmc-medium.onnx"
PIPER_MODEL_JSON = r"C:\Kinect\piper\fr_FR-upmc-medium.onnx.json"
PIPER_WAV        = r"C:\Kinect\tts_tmp.wav"

_piper_voice = None
_piper_lock  = threading.Lock()

def _log(msg):
    line = "[" + time.strftime("%H:%M:%S") + "] " + msg
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

_motor_lock   = threading.Lock()
_priority_evt = threading.Event()

def _run(cmd):
    with _motor_lock:
        try:
            subprocess.call([MOTOR_EXE, cmd], creationflags=subprocess.CREATE_NO_WINDOW)
            _log("OK:" + cmd)
        except Exception as e:
            _log("ERR _run " + cmd + ": " + str(e))

def _run_snap():
    _log("snap: debut")
    with _motor_lock:
        for attempt in range(3):
            try:
                _log("snap: tentative " + str(attempt + 1))
                result = subprocess.check_output(
                    [MOTOR_EXE, "snap"], creationflags=subprocess.CREATE_NO_WINDOW,
                    stderr=subprocess.DEVNULL, timeout=30
                ).decode(errors="replace").strip()
                _log("snap: resultat='" + result + "'")
                if (result.startswith("ERROR:") or result == "") and attempt < 2:
                    time.sleep(2); continue
                return result if result else None
            except subprocess.TimeoutExpired:
                _log("ERR snap: timeout"); return None
            except Exception as e:
                _log("ERR snap: " + str(e)); return None
        _log("snap: echec apres 3 tentatives")
        return None

# --- TTS Piper in-process ---

def _load_piper():
    global _piper_voice
    try:
        from piper import PiperVoice
        _log("Chargement Piper Jessica...")
        t = time.time()
        _piper_voice = PiperVoice.load(PIPER_MODEL, config_path=PIPER_MODEL_JSON, use_cuda=True)
        _log("Piper pret en " + f"{time.time()-t:.1f}s")
    except Exception as e:
        _log("ERR Piper load: " + str(e) + " — fallback pyttsx3")

def _play_wav(path):
    p = path.replace("\\", "/")
    script = (
        "Add-Type -AssemblyName presentationCore; "
        "$m=New-Object System.Windows.Media.MediaPlayer; "
        "$m.Open([uri]::new('" + p + "')); $m.Play(); "
        "Start-Sleep -Milliseconds 500; "
        "while ($m.NaturalDuration.HasTimeSpan -eq $false){Start-Sleep -Milliseconds 50}; "
        "$dur=[int]($m.NaturalDuration.TimeSpan.TotalMilliseconds)+300; "
        "Start-Sleep -Milliseconds $dur; $m.Stop(); $m.Close()"
    )
    subprocess.call(
        ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-c", script],
        creationflags=subprocess.CREATE_NO_WINDOW
    )

def _tts_wait(text, neural=False):
    global _piper_voice
    if not neural and _piper_voice is not None:
        with _piper_lock:
            try:
                t = time.time()
                with wave.open(PIPER_WAV, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(_piper_voice.config.sample_rate)
                    _piper_voice.synthesize_wav(text, wf)
                _log("Piper synth: " + f"{time.time()-t:.2f}s")
                _play_wav(PIPER_WAV)
            except Exception as e:
                _log("ERR tts piper: " + str(e))
            finally:
                try: os.remove(PIPER_WAV)
                except: pass
    else:
        try:
            args = [PYTHON, TTS_PY, text] + (["--neural"] if neural else ["--local"])
            subprocess.call(args, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            _log("ERR tts subprocess: " + str(e))

# --- LLM Ollama ---

def _ask_ollama(text):
    try:
        payload = json.dumps({
            "model": OLLAMA_MDL, "stream": False,
            "options": {"num_predict": 80, "temperature": 0.7},
            "messages": [
                {"role": "system", "content": (
                    "Tu es Claudius, un assistant IA incarne dans une tete animatronique Kinect Xbox 360. "
                    "Reponds de facon tres concise (1-2 phrases max), naturelle et conversationnelle en francais. "
                    "Pas de markdown, pas de listes, juste du texte parle."
                )},
                {"role": "user", "content": text}
            ]
        }).encode("utf-8")
        req = urllib.request.Request(OLLAMA_URL, data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))["message"]["content"].strip()
    except Exception as e:
        _log("ERR ollama: " + str(e))
        return None

def _warmup_ollama():
    _log("Warm-up Ollama...")
    reply = _ask_ollama("Bonjour")
    _log("Ollama pret: " + reply[:50] if reply else "Ollama warm-up echec")

# --- Gestes ---

def _gesture_for(text):
    t = text.lower()
    if any(w in t for w in ["oui","absolument","exactement","bien sur","correct","tout a fait","effectivement"]):
        return "oui"
    if any(w in t for w in ["non","pas vraiment","pas du tout","jamais","nenni"]):
        return "non"
    if any(w in t for w in ["bonjour","salut","hello","bonsoir","re!"]):
        return "hello"
    if any(w in t for w in ["hmm","interessant","voyons","je pense","question","complexe","curieux"]):
        return "think"
    return None

def _handle_voice(text):
    _run("think")
    _log("VOICE -> Ollama: " + text[:60])
    reply = _ask_ollama(text) or "Je suis hors ligne pour l instant."
    _log("VOICE reply: " + reply[:80])
    gesture = _gesture_for(reply)
    if gesture:
        threading.Thread(target=_run, args=(gesture,), daemon=True).start()
    _tts_wait(reply)

# --- Auto-blink ---

def _auto_blink():
    while True:
        interval = random.uniform(4.0, 8.0)
        if _priority_evt.wait(timeout=interval):
            while _priority_evt.is_set():
                time.sleep(0.1)
            continue
        if not _priority_evt.is_set():
            _run("blink")

def start_auto_blink():
    threading.Thread(target=_auto_blink, daemon=True).start()
    _log("Auto-blink demarre (4-8s)")

# --- Watcher cmd.txt ---

VALID_CMDS = {"oui","non","blink","hello","think","reset","snap"}

def watch_cmd():
    while True:
        try:
            if not _motor_lock.locked() and os.path.exists(CMD_FILE):
                try:
                    with open(CMD_FILE, "r", encoding="utf-8") as f:
                        raw = f.read().strip()
                except Exception as e:
                    _log("watch ERR lecture: " + str(e))
                    try: os.remove(CMD_FILE)
                    except: pass
                    time.sleep(0.5); continue
                try: os.remove(CMD_FILE)
                except OSError: pass
                cmd = raw.lower()
                if cmd.startswith("voice:"):
                    text = raw[6:].strip()
                    if text:
                        _log("VOICE recu: " + text)
                        _priority_evt.set()
                        try: _handle_voice(text)
                        finally: _priority_evt.clear()
                elif cmd in VALID_CMDS:
                    _priority_evt.set()
                    try: _run_snap() if cmd == "snap" else _run(cmd)
                    finally: _priority_evt.clear()
                else:
                    _log("commande inconnue: " + repr(cmd))
        except Exception as e:
            _log("watch ERR: " + str(e))
            _priority_evt.clear()
        time.sleep(0.5)

# --- Entrypoint ---

if __name__ == "__main__":
    _log("KinectBridge demarrage...")
    threading.Thread(target=watch_cmd, daemon=True).start()
    start_auto_blink()
    threading.Thread(target=_warmup_ollama, daemon=True).start()
    threading.Thread(target=_load_piper, daemon=True).start()
    _log("KinectBridge pret.")
    while True:
        time.sleep(60)
