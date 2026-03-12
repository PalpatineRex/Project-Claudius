"""
KinectBridge.py - Pont Kinect, demarre avec Windows
LLM  : Claude Haiku via API Anthropic
TTS  : Piper Jessica in-process, lazy load
Audio: winsound natif
Commandes: oui/non/blink/hello/think/reset/snap/sleep/wake + VOICE:texte
"""
import subprocess, os, time, threading, random, json, wave, winsound
import urllib.request

MOTOR_EXE        = r"C:\Kinect\KinectMotor.exe"
TTS_PY           = r"C:\Kinect\KinectTTS.py"
CMD_FILE         = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\cmd.txt"
LOG_FILE         = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\kinect.log"
TTS_LOCK_FILE    = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\tts_speaking.lock"
TRANSCRIPT_FILE  = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\transcript.txt"
SLEEP_FILE       = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\claudius_sleep.lock"
PYTHON           = r"C:\Python314\python.exe"
PIPER_MODEL      = r"C:\Kinect\piper\fr_FR-upmc-medium.onnx"
PIPER_MODEL_JSON = r"C:\Kinect\piper\fr_FR-upmc-medium.onnx.json"
PIPER_WAV        = r"C:\Kinect\tts_tmp.wav"
LOG_MAX_LINES    = 2000
_log_count       = 0

ANTHROPIC_URL     = "https://api.anthropic.com/v1/messages"
# Cle API dans api_key.txt (non versionne)
try:
    with open(r"C:\Kinect\api_key.txt", "r") as _f:
        ANTHROPIC_API_KEY = _f.read().strip()
except Exception:
    ANTHROPIC_API_KEY = ""
ANTHROPIC_MODEL   = "claude-haiku-4-5-20251001"

# Nettoyage fichiers residuels au boot
for _f in (SLEEP_FILE, TTS_LOCK_FILE, CMD_FILE):
    try:
        if os.path.exists(_f): os.remove(_f)
    except Exception: pass

# --- Etat global ---
_piper_voice  = None
_piper_lock   = threading.Lock()
_piper_ready  = threading.Event()
_speaking     = threading.Event()
_sleeping     = threading.Event()
_motor_lock   = threading.Lock()
_priority_evt = threading.Event()

# --- Log avec rotation ---

def _log(msg):
    global _log_count
    line = "[" + time.strftime("%H:%M:%S") + "] " + msg
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        _log_count += 1
        if _log_count >= 100:  # rotation toutes les 100 lignes seulement
            _log_count = 0
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
                _log("snap: " + result)
                if (result.startswith("ERROR:") or result == "") and attempt < 2:
                    time.sleep(2); continue
                return result if result else None
            except subprocess.TimeoutExpired:
                _log("ERR snap: timeout"); return None
            except Exception as e:
                _log("ERR snap: " + str(e)); return None
        return None

# --- TTS Piper in-process ---

def _load_piper_bg():
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
            _log("ERR Piper: " + str(e))
        finally:
            _piper_ready.set()

def _tts_wait(text):
    _speaking.set()
    try: open(TTS_LOCK_FILE, "w").close()
    except: pass
    try:
        _piper_ready.wait(timeout=5)  # attendre max 5s, sinon fallback local
        if _piper_voice is not None:
            with _piper_lock:
                try:
                    t = time.time()
                    with wave.open(PIPER_WAV, "wb") as wf:
                        wf.setnchannels(1); wf.setsampwidth(2)
                        wf.setframerate(_piper_voice.config.sample_rate)
                        _piper_voice.synthesize_wav(text, wf)
                    _log("Piper synth: " + f"{time.time()-t:.2f}s")
                    winsound.PlaySound(PIPER_WAV, winsound.SND_FILENAME)
                except Exception as e:
                    _log("ERR tts: " + str(e))
                finally:
                    try: os.remove(PIPER_WAV)
                    except: pass
        else:
            subprocess.call([PYTHON, TTS_PY, text, "--local"],
                            creationflags=subprocess.CREATE_NO_WINDOW)
    finally:
        _speaking.clear()
        try: os.remove(TTS_LOCK_FILE)
        except: pass

# --- LLM Claude Haiku via API ---

SYSTEM_PROMPT = (
    "Tu es Claudius. Je suis David. "
    "Tu es une tete animatronique Kinect Xbox 360 que j'ai construite, posee sur mon bureau. "
    "Reponds-moi directement en francais, en 1 ou 2 phrases max. "
    "Parle naturellement, comme a voix haute. Jamais de markdown ni listes. "
    "Si tu ne comprends pas, demande de repeter. Ne te presente pas a chaque fois."
)

def _ask_claude(text):
    try:
        payload = json.dumps({
            "model": ANTHROPIC_MODEL,
            "max_tokens": 80,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": text}]
        }).encode("utf-8")
        req = urllib.request.Request(ANTHROPIC_URL, data=payload, method="POST", headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())["content"][0]["text"].strip()
    except Exception as e:
        _log("ERR claude: " + str(e))
        return None

# --- Gestes ---

def _gesture_for(text):
    t = text.lower()
    if any(w in t for w in ["oui","absolument","exactement","bien sur","correct","effectivement"]):
        return "oui"
    if any(w in t for w in ["non","pas vraiment","pas du tout","jamais"]):
        return "non"
    if any(w in t for w in ["bonjour","salut","hello","bonsoir"]):
        return "hello"
    if any(w in t for w in ["hmm","interessant","voyons","je pense","curieux"]):
        return "think"
    return None

def _handle_voice(text):
    _log("VOICE -> Claude: " + text[:60])
    result_box = [None]
    def _query():
        result_box[0] = _ask_claude(text) or "Desole, je suis hors ligne."
    t = threading.Thread(target=_query, daemon=True)
    t.start()
    _run("think")
    t.join()
    reply = result_box[0]
    _log("VOICE reply: " + reply[:80])
    # Transcript temps reel
    try:
        ts = time.strftime("%H:%M:%S")
        with open(TRANSCRIPT_FILE, "a", encoding="utf-8") as _tf:
            _tf.write(f"[{ts}] Claudius: {reply}\n")
    except Exception:
        pass
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
    while True:
        try:
            if os.path.exists(CMD_FILE):
                try:
                    with open(CMD_FILE, "r", encoding="utf-8") as f:
                        raw = f.read().strip()
                    os.remove(CMD_FILE)
                except Exception as e:
                    _log("watch ERR: " + str(e))
                    try: os.remove(CMD_FILE)
                    except: pass
                    time.sleep(0.3); continue
                if not raw:
                    time.sleep(0.3); continue
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
                    _log("inconnu: " + repr(cmd))
        except Exception as e:
            _log("watch ERR: " + str(e))
            _priority_evt.clear()
        time.sleep(0.3)

# --- Entrypoint ---

if __name__ == "__main__":
    _log("=== KinectBridge demarrage (Claude Haiku) ===")
    threading.Thread(target=watch_cmd, daemon=True).start()
    threading.Thread(target=_auto_blink, daemon=True).start()
    threading.Thread(target=_load_piper_bg, daemon=True).start()
    _log("KinectBridge pret.")
    while True:
        time.sleep(60)
