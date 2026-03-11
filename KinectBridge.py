"""
KinectBridge.py - Pont Kinect, demarre avec Windows
LLM  : Ollama local llama3.2:3b (num_ctx=2048, keep_alive=5m)
TTS  : Piper Jessica in-process, lazy load apres Ollama warm
Audio: winsound natif (zero subprocess pour la lecture WAV)
Commandes: oui/non/blink/hello/think/reset/snap/sleep/wake + VOICE:texte
"""
import subprocess, os, time, threading, random, json, wave, winsound
import urllib.request

MOTOR_EXE        = r"C:\Kinect\KinectMotor.exe"
TTS_PY           = r"C:\Kinect\KinectTTS.py"
CMD_FILE         = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\cmd.txt"
LOG_FILE         = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\kinect.log"
TTS_LOCK_FILE    = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\tts_speaking.lock"
SLEEP_FILE       = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\claudius_sleep.lock"
PYTHON           = r"C:\Python314\python.exe"
OLLAMA_URL       = "http://localhost:11434/api/chat"
OLLAMA_MDL       = "llama3.2:3b"
PIPER_MODEL      = r"C:\Kinect\piper\fr_FR-upmc-medium.onnx"
PIPER_MODEL_JSON = r"C:\Kinect\piper\fr_FR-upmc-medium.onnx.json"
PIPER_WAV        = r"C:\Kinect\tts_tmp.wav"
LOG_MAX_LINES    = 2000   # Rotation log au-dela de cette limite

# Nettoyage fichiers residuels au boot
for _f in (SLEEP_FILE, TTS_LOCK_FILE, CMD_FILE):
    try:
        if os.path.exists(_f): os.remove(_f)
    except Exception: pass

# --- Etat global ---
_piper_voice  = None
_piper_lock   = threading.Lock()
_piper_ready  = threading.Event()   # set quand Piper est charge
_speaking     = threading.Event()   # set pendant toute la duree TTS
_sleeping     = threading.Event()   # set en mode veille
_motor_lock   = threading.Lock()
_priority_evt = threading.Event()

# --- Log avec rotation ---

def _log(msg):
    line = "[" + time.strftime("%H:%M:%S") + "] " + msg
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        # Rotation : tronquer si trop gros
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if len(lines) > LOG_MAX_LINES:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.writelines(lines[-LOG_MAX_LINES:])
    except Exception:
        pass

# --- Moteur Kinect ---

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

def _load_piper_bg():
    """Charge Piper en arriere-plan APRES le warm-up Ollama (sequentiel pour eviter OOM)."""
    global _piper_voice
    with _piper_lock:
        if _piper_voice is not None:
            _piper_ready.set(); return
        try:
            from piper import PiperVoice
            _log("Chargement Piper Jessica...")
            t = time.time()
            _piper_voice = PiperVoice.load(PIPER_MODEL, config_path=PIPER_MODEL_JSON, use_cuda=True)
            _log("Piper pret en " + f"{time.time()-t:.1f}s")
        except Exception as e:
            _log("ERR Piper load: " + str(e) + " — fallback pyttsx3")
        finally:
            _piper_ready.set()

def _tts_wait(text, neural=False):
    """TTS bloquant. Attend Piper si en cours de chargement. Lock fichier pendant lecture."""
    _speaking.set()
    try:
        open(TTS_LOCK_FILE, "w").close()
    except Exception:
        pass
    try:
        if not neural:
            _piper_ready.wait(timeout=30)   # Attendre max 30s si Piper charge encore
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
                    winsound.PlaySound(PIPER_WAV, winsound.SND_FILENAME)  # Natif, zero subprocess
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
    "installee sur le bureau de David, un developpeur independant. "
    "Tu es son assistant physique et compagnon de travail. "
    "REGLES ABSOLUES : "
    "1. Reponds TOUJOURS en francais. "
    "2. Maximum 1 ou 2 phrases courtes. Jamais plus. "
    "3. Parle naturellement, sans markdown ni listes. "
    "4. Reste dans le sujet de ce que David dit. "
    "5. Si tu ne sais pas, dis-le en une phrase. "
    "6. Tu t appelles Claudius."
)

def _ask_ollama(text):
    try:
        payload = json.dumps({
            "model": OLLAMA_MDL,
            "stream": False,
            "options": {"num_predict": 60, "temperature": 0.7, "num_ctx": 2048},
            "keep_alive": "5m",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": text}
            ]
        }).encode("utf-8")
        req = urllib.request.Request(OLLAMA_URL, data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())["message"]["content"].strip()
    except Exception as e:
        _log("ERR ollama: " + str(e))
        return None

def _warmup_ollama():
    """Warm-up avec retry. Lance Piper en sequentiel apres succes pour eviter OOM."""
    for attempt in range(6):
        _log("Warm-up Ollama (" + str(attempt+1) + "/6)...")
        reply = _ask_ollama("ok")
        if reply:
            _log("Ollama pret: " + reply[:50])
            # Lancer Piper APRES Ollama (sequentiel = pas de spike RAM simultane)
            threading.Thread(target=_load_piper_bg, daemon=True).start()
            return
        wait = 10 if attempt < 3 else 20
        _log("Ollama pas pret, retry dans " + str(wait) + "s...")
        time.sleep(wait)
    _log("Ollama warm-up echec — Piper charge quand meme")
    threading.Thread(target=_load_piper_bg, daemon=True).start()

# --- Gestes ---

def _gesture_for(text):
    t = text.lower()
    if any(w in t for w in ["oui","absolument","exactement","bien sur","correct","tout a fait","effectivement"]):
        return "oui"
    if any(w in t for w in ["non","pas vraiment","pas du tout","jamais","nenni"]):
        return "non"
    if any(w in t for w in ["bonjour","salut","hello","bonsoir"]):
        return "hello"
    if any(w in t for w in ["hmm","interessant","voyons","je pense","question","curieux"]):
        return "think"
    return None

def _handle_voice(text):
    """Pipeline: think + Ollama en parallele -> geste + TTS."""
    _log("VOICE -> Ollama: " + text[:60])
    result_box = [None]
    def _query():
        result_box[0] = _ask_ollama(text) or "Je suis hors ligne pour l instant."
    t = threading.Thread(target=_query, daemon=True)
    t.start()
    _run("think")
    t.join()
    reply = result_box[0]
    _log("VOICE reply: " + reply[:80])
    gesture = _gesture_for(reply)
    if gesture:
        threading.Thread(target=_run, args=(gesture,), daemon=True).start()
    _tts_wait(reply)

# --- Auto-blink ---

def _auto_blink():
    while True:
        if _sleeping.is_set():
            time.sleep(1.0); continue
        interval = random.uniform(4.0, 8.0)
        if _priority_evt.wait(timeout=interval):
            while _priority_evt.is_set():
                time.sleep(0.05)
            continue
        if not _speaking.is_set() and not _priority_evt.is_set() and not _sleeping.is_set():
            _run("blink")

# --- Sleep / Wake ---

def _do_sleep():
    _sleeping.set()
    try: open(SLEEP_FILE, "w").close()
    except: pass
    _run("reset")
    _log("Claudius en veille")

def _do_wake():
    _sleeping.clear()
    try: os.remove(SLEEP_FILE)
    except: pass
    _run("hello")
    _log("Claudius reveille")

# --- Watcher cmd.txt ---

VALID_CMDS = {"oui","non","blink","hello","think","reset","snap","sleep","wake"}

def watch_cmd():
    _cmd_mtime = 0.0
    while True:
        try:
            try:
                mtime = os.path.getmtime(CMD_FILE)
            except OSError:
                time.sleep(0.3); continue

            if mtime <= _cmd_mtime:
                time.sleep(0.3); continue

            _cmd_mtime = mtime
            try:
                with open(CMD_FILE, "r", encoding="utf-8") as f:
                    raw = f.read().strip()
                os.remove(CMD_FILE)
            except Exception as e:
                _log("watch ERR: " + str(e))
                try: os.remove(CMD_FILE)
                except: pass
                time.sleep(0.3); continue

            if not raw: continue
            cmd = raw.lower()

            if cmd.startswith("voice:"):
                if _sleeping.is_set():
                    _log("VOICE ignore (veille)")
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
                    if   cmd == "snap":  _run_snap()
                    elif cmd == "sleep": _do_sleep()
                    elif cmd == "wake":  _do_wake()
                    else:                _run(cmd)
                finally: _priority_evt.clear()
            else:
                _log("commande inconnue: " + repr(cmd))

        except Exception as e:
            _log("watch ERR: " + str(e))
            _priority_evt.clear()
        time.sleep(0.3)

# --- Entrypoint ---

if __name__ == "__main__":
    _log("=== KinectBridge demarrage ===")
    threading.Thread(target=watch_cmd, daemon=True).start()
    threading.Thread(target=_auto_blink, daemon=True).start()
    _log("Auto-blink demarre")
    threading.Thread(target=_warmup_ollama, daemon=True).start()
    _log("KinectBridge pret.")
    while True:
        time.sleep(60)
