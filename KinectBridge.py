"""
KinectBridge.py - Pont Kinect, demarre avec Windows
LLM: Ollama local (llama3.2:3b) - gratuit, hors ligne
TTS: Piper Jessica charge en memoire au boot (~1.2s chaud)
Commandes: oui/non/blink/hello/think/reset/snap + VOICE:texte
"""
import subprocess, os, time, threading, random, json, wave
import urllib.request

MOTOR_EXE        = r"C:\Kinect\KinectMotor.exe"
TTS_PY           = r"C:\Kinect\KinectTTS.py"
CMD_FILE         = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\cmd.txt"
LOG_FILE         = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\kinect.log"
TTS_LOCK_FILE    = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\tts_speaking.lock"
PYTHON           = r"C:\Python314\python.exe"
OLLAMA_URL       = "http://localhost:11434/api/chat"
OLLAMA_MDL       = "llama3.2:3b"
PIPER_MODEL      = r"C:\Kinect\piper\fr_FR-upmc-medium.onnx"
PIPER_MODEL_JSON = r"C:\Kinect\piper\fr_FR-upmc-medium.onnx.json"
PIPER_WAV        = r"C:\Kinect\tts_tmp.wav"

_piper_voice = None
_piper_lock  = threading.Lock()
_speaking    = threading.Event()   # True pendant toute la duree TTS
_sleeping    = threading.Event()   # True = mode veille (blink/ecoute suspendus)

SLEEP_FILE   = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\claudius_sleep.lock"

# Restaurer l etat veille si le fichier existait avant crash
if os.path.exists(SLEEP_FILE):
    os.remove(SLEEP_FILE)

def _log(msg):
    line = "[" + time.strftime("%H:%M:%S") + "] " + msg
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

# Lock moteur + event priorite
_motor_lock   = threading.Lock()
_priority_evt = threading.Event()

def _run(cmd):
    """Execute une commande moteur, thread-safe."""
    with _motor_lock:
        try:
            subprocess.call([MOTOR_EXE, cmd], creationflags=subprocess.CREATE_NO_WINDOW)
            _log("OK:" + cmd)
        except Exception as e:
            _log("ERR _run " + cmd + ": " + str(e))

def _run_snap():
    """Snap avec retry x3. Retourne path ou None."""
    _log("snap: debut")
    with _motor_lock:
        for attempt in range(3):
            try:
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
    """Charge Piper a la premiere demande TTS (lazy) pour ne pas concurrencer Ollama au boot."""
    global _piper_voice
    if _piper_voice is not None:
        return  # Deja charge
    try:
        from piper import PiperVoice
        _log("Chargement Piper Jessica (lazy)...")
        t = time.time()
        _piper_voice = PiperVoice.load(PIPER_MODEL, config_path=PIPER_MODEL_JSON, use_cuda=True)
        _log("Piper pret en " + f"{time.time()-t:.1f}s")
    except Exception as e:
        _log("ERR Piper load: " + str(e) + " — fallback pyttsx3")

def _play_wav(path):
    """Lecture WAV via SoundPlayer (plus rapide que MediaPlayer, pas de spawn lourd)."""
    p = path.replace("/", "\\")
    script = f"(New-Object Media.SoundPlayer '{p}').PlaySync()"
    subprocess.call(
        ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-c", script],
        creationflags=subprocess.CREATE_NO_WINDOW
    )

def _tts_wait(text, neural=False):
    """TTS bloquant. Charge Piper si pas encore fait (lazy). Pose lock pendant lecture."""
    global _piper_voice
    _load_piper()  # no-op si deja charge
    # Signaler a KinectVoice que Claudius parle
    _speaking.set()
    try:
        open(TTS_LOCK_FILE, "w").close()
    except Exception:
        pass
    try:
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
    finally:
        _speaking.clear()
        try: os.remove(TTS_LOCK_FILE)
        except: pass

# --- LLM Ollama ---

SYSTEM_PROMPT = (
    "Tu es Claudius, une tete animatronique Kinect Xbox 360 pilotee par IA, "
    "installee sur le bureau de David, un developpeur independant passionnant. "
    "Tu es son assistant physique et compagnon de travail. "
    "REGLES ABSOLUES : "
    "1. Reponds TOUJOURS en francais. "
    "2. Maximum 1 ou 2 phrases courtes. Jamais plus. "
    "3. Parle naturellement, comme a voix haute, sans markdown ni listes. "
    "4. Reste dans le sujet de ce que David vient de dire. Ne change pas de sujet. "
    "5. Si tu ne sais pas, dis-le simplement en une phrase. "
    "6. Tu t appelles Claudius, pas Claude, pas assistant."
)

def _ask_ollama(text):
    try:
        payload = json.dumps({
            "model": OLLAMA_MDL, "stream": False,
            "options": {
                "num_predict": 80,
                "temperature": 0.7,
                "num_ctx": 2048,       # FIX: 2048 au lieu de 131072 — économise ~14GB RAM
            },
            "keep_alive": "5m",        # Libere la VRAM apres 5min d inactivite
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
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
    """Warm-up Ollama avec retry — il peut etre lent a demarrer avec Windows."""
    for attempt in range(5):
        _log("Warm-up Ollama (tentative " + str(attempt+1) + ")...")
        reply = _ask_ollama("Bonjour")
        if reply:
            _log("Ollama pret: " + reply[:50])
            return
        _log("Ollama pas pret, retry dans 10s...")
        time.sleep(10)
    _log("Ollama warm-up echec apres 5 tentatives — pipeline voix operationnel quand meme")

# --- Gestes ---

def _gesture_for(text):
    t = text.lower()
    if any(w in t for w in ["oui","absolument","exactement","bien sur","correct","tout a fait","effectivement"]):
        return "oui"
    if any(w in t for w in ["non","pas vraiment","pas du tout","jamais","nenni"]):
        return "non"
    if any(w in t for w in ["bonjour","salut","hello","bonsoir"]):
        return "hello"
    if any(w in t for w in ["hmm","interessant","voyons","je pense","question","complexe","curieux"]):
        return "think"
    return None

def _handle_voice(text):
    """Pipeline voix: think + Ollama en parallele -> geste + TTS."""
    _log("VOICE -> Ollama: " + text[:60])

    # Lancer Ollama ET think en parallele (think ~1s, Ollama ~3.5s)
    result_box = [None]
    def _query():
        result_box[0] = _ask_ollama(text) or "Je suis hors ligne pour l instant."
    ollama_thread = threading.Thread(target=_query, daemon=True)
    ollama_thread.start()
    _run("think")           # bloquant ~1s, Ollama tourne en parallele
    ollama_thread.join()    # attendre la fin si pas encore finie

    reply = result_box[0]
    _log("VOICE reply: " + reply[:80])

    # Geste en thread separe + TTS bloquant
    gesture = _gesture_for(reply)
    if gesture:
        threading.Thread(target=_run, args=(gesture,), daemon=True).start()
    _tts_wait(reply)

# --- Auto-blink ---

def _auto_blink():
    """Cligne des yeux toutes les 4-8s, sauf si veille/commande/parole en cours."""
    while True:
        if _sleeping.is_set():
            time.sleep(1.0)
            continue
        interval = random.uniform(4.0, 8.0)
        if _priority_evt.wait(timeout=interval):
            while _priority_evt.is_set():
                time.sleep(0.05)
            continue
        if not _speaking.is_set() and not _priority_evt.is_set() and not _sleeping.is_set():
            _run("blink")

def start_auto_blink():
    threading.Thread(target=_auto_blink, daemon=True).start()
    _log("Auto-blink demarre (4-8s)")

# --- Watcher cmd.txt ---

VALID_CMDS = {"oui","non","blink","hello","think","reset","snap","sleep","wake"}

def _do_sleep():
    _sleeping.set()
    open(SLEEP_FILE, "w").close()
    _run("reset")
    _log("Claudius en veille — idle et ecoute suspendus")

def _do_wake():
    _sleeping.clear()
    try: os.remove(SLEEP_FILE)
    except: pass
    _run("hello")
    _log("Claudius reveille")

def watch_cmd():
    while True:
        try:
            if os.path.exists(CMD_FILE):
                # Lire + supprimer atomiquement
                try:
                    with open(CMD_FILE, "r", encoding="utf-8") as f:
                        raw = f.read().strip()
                    os.remove(CMD_FILE)
                except Exception as e:
                    _log("watch ERR lecture: " + str(e))
                    try: os.remove(CMD_FILE)
                    except: pass
                    time.sleep(0.5); continue

                if not raw:
                    time.sleep(0.5); continue

                cmd = raw.lower()
                if cmd.startswith("voice:"):
                    if _sleeping.is_set():
                        _log("VOICE ignore (veille): " + raw[6:50])
                    else:
                        text = raw[6:].strip()
                        if text:
                            _log("VOICE recu: " + text)
                            _priority_evt.set()
                            try: _handle_voice(text)
                            finally: _priority_evt.clear()
                elif cmd in VALID_CMDS:
                    _priority_evt.set()
                    try:
                        if cmd == "snap":   _run_snap()
                        elif cmd == "sleep": _do_sleep()
                        elif cmd == "wake":  _do_wake()
                        else:               _run(cmd)
                    finally: _priority_evt.clear()
                else:
                    _log("commande inconnue: " + repr(cmd))
        except Exception as e:
            _log("watch ERR: " + str(e))
            _priority_evt.clear()
        time.sleep(0.3)   # 300ms au lieu de 500ms, plus reactif

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
