"""
KinectBridge.py - Pont Kinect, demarre avec Windows
LLM  : Claude Haiku via API Anthropic
TTS  : Piper Jessica in-process, lazy load
Audio: sounddevice (cross-platform, non-bloquant)
Commandes: oui/non/blink/hello/think/reset/snap/sleep/wake + VOICE:texte
"""
import subprocess, os, time, threading, random, json, wave, sys
import urllib.request
import numpy as np
import sounddevice as sd

# --- Chemins : relatifs au script, overridables par env ---
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_KINECT_DIR = os.environ.get("CLAUDIUS_KINECT_DIR", _SCRIPT_DIR)
_DATA_DIR   = os.environ.get("CLAUDIUS_DATA_DIR", _SCRIPT_DIR)

MOTOR_EXE        = os.path.join(_KINECT_DIR, "KinectMotor.exe")
TTS_PY           = os.path.join(_KINECT_DIR, "KinectTTS.py")
CMD_FILE         = os.path.join(_DATA_DIR, "cmd.txt")
LOG_FILE         = os.path.join(_DATA_DIR, "kinect.log")
TTS_LOCK_FILE    = os.path.join(_DATA_DIR, "tts_speaking.lock")
TRANSCRIPT_FILE  = os.path.join(_DATA_DIR, "transcript.txt")
SLEEP_FILE       = os.path.join(_DATA_DIR, "claudius_sleep.lock")
PYTHON           = os.environ.get("CLAUDIUS_PYTHON", sys.executable)
PIPER_MODEL      = os.path.join(_KINECT_DIR, "piper", "fr_FR-upmc-medium.onnx")
PIPER_MODEL_JSON = os.path.join(_KINECT_DIR, "piper", "fr_FR-upmc-medium.onnx.json")
PIPER_MODEL2     = os.path.join(_KINECT_DIR, "piper", "siwis", "fr_FR-siwis-medium.onnx")
PIPER_MODEL2_JSON= os.path.join(_KINECT_DIR, "piper", "siwis", "fr_FR-siwis-medium.onnx.json")
BLEND_RATIO      = 0.5  # 0.0=Jessica pure, 1.0=SIWIS pure
CONTEXT_FILE     = os.path.join(_DATA_DIR, "claudius_context.txt")
LOG_MAX_LINES    = 2000
_log_count       = 0

ANTHROPIC_URL     = "https://api.anthropic.com/v1/messages"
# Cle API : fichier local (prioritaire) > env var (fallback)
ANTHROPIC_API_KEY = ""
for _p in [os.path.join(_KINECT_DIR, "api_key.txt"), os.path.join(_DATA_DIR, "api_key.txt")]:
    try:
        _k = open(_p, "r").read().strip().strip('"').strip("'")
        if _k:
            ANTHROPIC_API_KEY = _k
            break
    except Exception:
        pass
if not ANTHROPIC_API_KEY:
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip().strip('"').strip("'")
ANTHROPIC_MODEL   = "claude-haiku-4-5-20251001"
BRIDGE_PID_FILE   = os.path.join(_DATA_DIR, "bridge.pid")

# --- Singleton Bridge ---
def _enforce_singleton():
    my_pid = os.getpid()
    if os.path.exists(BRIDGE_PID_FILE):
        try:
            old_pid = int(open(BRIDGE_PID_FILE).read().strip())
            if old_pid != my_pid:
                try:
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    handle = kernel32.OpenProcess(1, False, old_pid)
                    if handle:
                        kernel32.TerminateProcess(handle, 0)
                        kernel32.CloseHandle(handle)
                except Exception:
                    pass
                time.sleep(0.5)
        except (ValueError, OSError):
            pass
    with open(BRIDGE_PID_FILE, "w") as f:
        f.write(str(my_pid))

# Nettoyage fichiers residuels au boot — appele dans __main__ apres singleton
def _cleanup_boot():
    for _f in (SLEEP_FILE, TTS_LOCK_FILE, CMD_FILE):
        try:
            if os.path.exists(_f): os.remove(_f)
        except Exception: pass

# --- Etat global ---
_piper_voice  = None
_piper_voice2 = None
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
        if _log_count >= 500:  # rotation moins frequente
            _log_count = 0
            try:
                with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                if len(lines) > LOG_MAX_LINES:
                    with open(LOG_FILE, "w", encoding="utf-8") as f:
                        f.writelines(lines[-LOG_MAX_LINES:])
            except Exception:
                pass
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
    global _piper_voice, _piper_voice2
    with _piper_lock:
        if _piper_voice is not None:
            _piper_ready.set(); return
        try:
            from piper import PiperVoice
            t = time.time()
            _log("Chargement Piper Jessica...")
            _piper_voice = PiperVoice.load(PIPER_MODEL, config_path=PIPER_MODEL_JSON, use_cuda=True)
            _log(f"Jessica prete en {time.time()-t:.1f}s")
            if os.path.exists(PIPER_MODEL2) and BLEND_RATIO > 0:
                t2 = time.time()
                _log("Chargement Piper SIWIS (blend)...")
                _piper_voice2 = PiperVoice.load(PIPER_MODEL2, config_path=PIPER_MODEL2_JSON, use_cuda=True)
                _log(f"SIWIS prete en {time.time()-t2:.1f}s (blend {BLEND_RATIO:.0%})")
        except Exception as e:
            _log("ERR Piper: " + str(e))
        finally:
            _piper_ready.set()

def _blend_voices(j_audio, s_audio, ratio=0.5):
    """Blend Jessica+SIWIS — scipy.resample + spectral subtraction (v2_50_50_clean)."""
    from scipy.signal import resample, stft, istft
    j = j_audio.astype(np.float64)
    s = resample(s_audio.astype(np.float64), len(j))
    blend = j * (1.0 - ratio) + s * ratio
    # Spectral subtraction
    n_fft, hop = 2048, 512
    f, t, Zxx = stft(blend, fs=22050, nperseg=n_fft, noverlap=n_fft - hop)
    mag = np.abs(Zxx)
    phase = np.angle(Zxx)
    noise_est = np.mean(mag[:, :5], axis=1, keepdims=True)
    mag_clean = np.maximum(mag - 1.5 * noise_est, 0.03 * mag)
    _, out = istft(mag_clean * np.exp(1j * phase), fs=22050, nperseg=n_fft, noverlap=n_fft - hop)
    if len(out) < len(j):
        out = np.pad(out, (0, len(j) - len(out)))
    out = out[:len(j)]
    peak = np.max(np.abs(out))
    if peak > 0:
        out *= 28000.0 / peak
    return out.astype(np.float32)

def _tts_wait(text):
    _speaking.set()
    try: open(TTS_LOCK_FILE, "w").close()
    except: pass
    try:
        _piper_ready.wait(timeout=5)
        if _piper_voice is not None:
            audio_data = None
            sample_rate = _piper_voice.config.sample_rate
            with _piper_lock:
                try:
                    t = time.time()
                    if _piper_voice2 is not None:
                        # Synth parallele : Jessica + SIWIS en meme temps
                        j_box, s_box = [None], [None]
                        def _sj(): j_box[0] = np.concatenate([c.audio_int16_array for c in _piper_voice.synthesize(text)])
                        def _ss(): s_box[0] = np.concatenate([c.audio_int16_array for c in _piper_voice2.synthesize(text)])
                        tj = threading.Thread(target=_sj); ts = threading.Thread(target=_ss)
                        tj.start(); ts.start()
                        tj.join(timeout=15); ts.join(timeout=15)
                        if j_box[0] is not None and s_box[0] is not None:
                            audio_data = _blend_voices(j_box[0], s_box[0], BLEND_RATIO)
                        elif j_box[0] is not None:
                            audio_data = j_box[0].astype(np.float32)
                    else:
                        frames = [c.audio_int16_array for c in _piper_voice.synthesize(text)]
                        if frames: audio_data = np.concatenate(frames).astype(np.float32)
                    dt = time.time() - t
                    if audio_data is not None:
                        _log(f"Piper {'blend' if _piper_voice2 else 'solo'}: {dt:.2f}s ({len(audio_data)/sample_rate:.1f}s audio)")
                except Exception as e:
                    _log("ERR tts synth: " + str(e))
            if audio_data is not None:
                try:
                    sd.play(audio_data / 32768.0 if np.max(np.abs(audio_data)) > 1.0 else audio_data, samplerate=sample_rate)
                    sd.wait()
                except Exception as e:
                    _log("ERR tts play: " + str(e))
        else:
            subprocess.call([PYTHON, TTS_PY, text, "--local"],
                            creationflags=subprocess.CREATE_NO_WINDOW)
    finally:
        _speaking.clear()
        time.sleep(0.3)
        try: os.remove(TTS_LOCK_FILE)
        except: pass

# --- LLM Claude Haiku via API ---

_SYSTEM_FALLBACK = (
    "Tu es Claudius, une tete animatronique Kinect Xbox 360 sur le bureau de David. "
    "Reponds en francais, 1-2 phrases max, naturellement. Pas de markdown."
)

_cached_system_prompt = None
_cached_system_mtime = 0

def _load_system_prompt():
    """Charge le contexte depuis claudius_context.txt, cache par mtime."""
    global _cached_system_prompt, _cached_system_mtime
    for path in [CONTEXT_FILE, r"C:\Kinect\claudius_context.txt"]:
        try:
            mt = os.path.getmtime(path)
            if _cached_system_prompt and mt == _cached_system_mtime:
                return _cached_system_prompt
            with open(path, "r", encoding="utf-8") as f:
                ctx = f.read().strip()
            if ctx:
                _cached_system_prompt = ctx
                _cached_system_mtime = mt
                return ctx
        except Exception:
            continue
    return _SYSTEM_FALLBACK

_conversation_history = []
_history_lock = threading.Lock()
MAX_HISTORY = 6  # nb d'echanges (user+assistant) gardes en memoire

def _ask_claude(text):
    global _conversation_history
    with _history_lock:
        _conversation_history.append({"role": "user", "content": text})
        messages = list(_conversation_history)
    try:
        payload = json.dumps({
            "model": ANTHROPIC_MODEL,
            "max_tokens": 80,
            "system": _load_system_prompt(),
            "messages": messages
        }).encode("utf-8")
        req = urllib.request.Request(ANTHROPIC_URL, data=payload, method="POST", headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            reply = json.loads(resp.read().decode())["content"][0]["text"].strip()
        with _history_lock:
            _conversation_history.append({"role": "assistant", "content": reply})
            # Garder seulement les MAX_HISTORY derniers echanges (paires user/assistant)
            if len(_conversation_history) > MAX_HISTORY * 2:
                _conversation_history = _conversation_history[-(MAX_HISTORY * 2):]
        return reply
    except Exception as e:
        _log("ERR claude: " + str(e))
        with _history_lock:
            # Retirer le message user si la requete a echoue
            if _conversation_history and _conversation_history[-1]["role"] == "user":
                _conversation_history.pop()
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
        try:
            result_box[0] = _ask_claude(text)
        except Exception as e:
            _log("ERR _query: " + str(e))
    t = threading.Thread(target=_query, daemon=True)
    t.start()
    # Think en parallele (non bloquant pour le thread principal)
    threading.Thread(target=_run, args=("think",), daemon=True).start()
    t.join(timeout=20)
    reply = result_box[0] or "Desole, je suis hors ligne."
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
    _enforce_singleton()
    _cleanup_boot()
    # CUDA DLLs pour Piper (onnxruntime GPU)
    import site
    for sp in site.getsitepackages():
        for sub in ["nvidia/cublas/bin", "nvidia/cudnn/bin", "nvidia/cufft/bin",
                     "nvidia/cusolver/bin", "nvidia/cusparse/bin", "nvidia/nvjitlink/bin",
                     "nvidia/cuda_runtime/bin"]:
            p = os.path.join(sp, sub)
            if os.path.isdir(p):
                os.environ["PATH"] = p + ";" + os.environ.get("PATH", "")
    if not ANTHROPIC_API_KEY:
        _log("ERREUR: cle API absente (C:\\Kinect\\api_key.txt)")
    _log("=== KinectBridge demarrage (Claude Haiku) ===")
    threading.Thread(target=watch_cmd, daemon=True).start()
    threading.Thread(target=_auto_blink, daemon=True).start()
    threading.Thread(target=_load_piper_bg, daemon=True).start()
    _log("KinectBridge pret.")
    while True:
        time.sleep(60)
