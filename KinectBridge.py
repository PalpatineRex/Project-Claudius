"""
KinectBridge.py v4 — Pont principal Project Claudius (optimisé)
LLM   : DeepSeek V4 Flash (texte) + Claude Haiku (vision)
TTS   : Piper Jessica+SIWIS blend spectral (CUDA)
Audio : sounddevice
Moteur: KinectMotor.exe (oui/non/blink/hello/think/reset/snap)

Utilise les modules :
  - claudius_sfx.py     → sons synthétiques pré-calculés
  - claudius_utils.py   → log, reaccentuation, commandes utiles
  - claudius_blend.py   → blend spectral DTW
"""
import os, sys, time, json, threading, re, base64, glob, subprocess
import urllib.request
import numpy as np
import sounddevice as sd

from claudius_sfx import preload_all as sfx_preload, play as sfx_play
from claudius_utils import log, reaccentuate, check_utility
from claudius_utils import start_timer as util_start_timer
from claudius_blend import synth_both

# ====================================================================
# CHEMINS
# ====================================================================
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.environ.get("CLAUDIUS_DATA_DIR", _SCRIPT_DIR)
_KINECT_DIR = os.environ.get("CLAUDIUS_KINECT_DIR", _SCRIPT_DIR)

MOTOR_EXE = os.path.join(_KINECT_DIR, "KinectMotor.exe")
CMD_FILE = os.path.join(_DATA_DIR, "cmd.txt")
LOG_FILE = os.path.join(_DATA_DIR, "kinect.log")
TRANSCRIPT_FILE = os.path.join(_DATA_DIR, "transcript.txt")
TTS_LOCK_FILE = os.path.join(_DATA_DIR, "tts_speaking.lock")
SLEEP_FILE = os.path.join(_DATA_DIR, "claudius_sleep.lock")
MOTOR_CMD_FILE = os.path.join(_DATA_DIR, "motor_cmd.txt")
PRESENCE_FILE = os.path.join(_DATA_DIR, "presence.txt")
MEMORY_FILE = os.path.join(_DATA_DIR, "memory.json")
CONTEXT_FILE = os.path.join(_DATA_DIR, "claudius_context.txt")
VOICE_PID_FILE = os.path.join(_DATA_DIR, "voice.pid")
VOICE_HEARTBEAT = os.path.join(_DATA_DIR, "voice_heartbeat.txt")
VOICE_SCRIPT = os.path.join(_KINECT_DIR, "KinectVoice.py")
BRIDGE_PID_FILE = os.path.join(_DATA_DIR, "bridge.pid")
MAX_MEMORIES = 15
LOG_MAX_LINES = 2000

PYTHON = os.environ.get("CLAUDIUS_PYTHON", sys.executable)
PIPER_MODEL = os.path.join(_KINECT_DIR, "piper", "fr_FR-upmc-medium.onnx")
PIPER_MODEL_JSON = os.path.join(_KINECT_DIR, "piper", "fr_FR-upmc-medium.onnx.json")
PIPER_MODEL2 = os.path.join(_KINECT_DIR, "piper", "siwis", "fr_FR-siwis-medium.onnx")
PIPER_MODEL2_JSON = os.path.join(_KINECT_DIR, "piper", "siwis", "fr_FR-siwis-medium.onnx.json")

# ====================================================================
# CLÉS API
# ====================================================================
def _load_key(filenames):
    for f in filenames:
        try:
            with open(f, "r") as fh:
                k = fh.read().strip().strip('"').strip("'")
            if k:
                return k
        except Exception:
            pass
    return ""

DEEPSEEK_API_KEY = _load_key([
    os.path.join(_KINECT_DIR, "deepseek_key.txt"),
    os.path.join(_DATA_DIR, "deepseek_key.txt"),
    os.environ.get("DEEPSEEK_API_KEY", "")
])
ANTHROPIC_API_KEY = _load_key([
    os.path.join(_KINECT_DIR, "api_key.txt"),
    os.path.join(_DATA_DIR, "api_key.txt"),
    os.environ.get("ANTHROPIC_API_KEY", "")
])

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

# ====================================================================
# SINGLETON
# ====================================================================
def _enforce_singleton():
    my_pid = os.getpid()
    if os.path.exists(BRIDGE_PID_FILE):
        try:
            old_pid = int(open(BRIDGE_PID_FILE).read().strip())
            if old_pid != my_pid:
                try:
                    import ctypes
                    h = ctypes.windll.kernel32.OpenProcess(1, False, old_pid)
                    if h:
                        ctypes.windll.kernel32.TerminateProcess(h, 0)
                        ctypes.windll.kernel32.CloseHandle(h)
                except Exception:
                    pass
                time.sleep(0.5)
        except (ValueError, OSError):
            pass
    with open(BRIDGE_PID_FILE, "w") as f:
        f.write(str(my_pid))

def _cleanup_boot():
    for f in (SLEEP_FILE, TTS_LOCK_FILE, CMD_FILE, MOTOR_CMD_FILE):
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception:
            pass
    os.system("taskkill /f /im KinectMotor.exe >nul 2>nul")
    time.sleep(1)

# ====================================================================
# ÉTAT GLOBAL
# ====================================================================
_piper_voice = None
_piper_voice2 = None
_piper_lock = threading.Lock()
_piper_ready = threading.Event()
_speaking = threading.Event()
_sleeping = threading.Event()
_motor_lock = threading.Lock()
_priority_evt = threading.Event()
_motor_daemon_mode = False
_motor_daemon_proc = None
_conversation_history = []
_history_lock = threading.Lock()
MAX_HISTORY = 6

# ====================================================================
# TTS — PIPER + BLEND
# ====================================================================
def _load_piper_bg():
    global _piper_voice, _piper_voice2
    with _piper_lock:
        if _piper_voice is not None:
            _piper_ready.set()
            return
        try:
            from piper import PiperVoice
            t = time.time()
            log("Chargement Piper Jessica...", LOG_FILE, "PIPER")
            _piper_voice = PiperVoice.load(PIPER_MODEL, config_path=PIPER_MODEL_JSON, use_cuda=True)
            log(f"Jessica prete en {time.time()-t:.1f}s", LOG_FILE, "PIPER")

            if os.path.exists(PIPER_MODEL2):
                t2 = time.time()
                log("Chargement Piper SIWIS (blend)...", LOG_FILE, "PIPER")
                _piper_voice2 = PiperVoice.load(PIPER_MODEL2, config_path=PIPER_MODEL2_JSON, use_cuda=True)
                log(f"SIWIS prete en {time.time()-t2:.1f}s", LOG_FILE, "PIPER")
        except Exception as e:
            log(f"ERR Piper: {e}", LOG_FILE, "PIPER")
        finally:
            _piper_ready.set()
            time.sleep(5)
            sfx_play("boot")

def _tts_wait(text):
    text = reaccentuate(text)
    _speaking.set()
    try:
        open(TTS_LOCK_FILE, "w").close()
    except Exception:
        pass
    try:
        _piper_ready.wait(timeout=20)
        if _piper_voice is not None:
            audio_data = None
            sample_rate = _piper_voice.config.sample_rate
            with _piper_lock:
                try:
                    t = time.time()
                    if _piper_voice2 is not None:
                        audio_data = synth_both(_piper_voice, _piper_voice2, text)
                    else:
                        frames = [c.audio_int16_array for c in _piper_voice.synthesize(text)]
                        if frames:
                            audio_data = np.concatenate(frames).astype(np.float32)
                    dt = time.time() - t
                    if audio_data is not None:
                        log(f"TTS {'blend' if _piper_voice2 else 'solo'}: {dt:.2f}s", LOG_FILE, "TTS")
                except Exception as e:
                    log(f"ERR tts synth: {e}", LOG_FILE, "TTS")
            if audio_data is not None:
                try:
                    sd.play(audio_data / 32768.0, samplerate=sample_rate)
                    sd.wait()
                except Exception as e:
                    log(f"ERR tts play: {e}", LOG_FILE, "TTS")
        else:
            subprocess.call([PYTHON, os.path.join(_KINECT_DIR, "KinectTTS.py"), text, "--local"],
                            creationflags=subprocess.CREATE_NO_WINDOW)
    finally:
        time.sleep(1.0)  # laisser le son se dissiper avant de rouvrir le micro
        _speaking.clear()
        try:
            os.remove(TTS_LOCK_FILE)
        except Exception:
            pass

# ====================================================================
# ALARM TIMER → TTS + SFX
# ====================================================================
def _on_timer_alarm(message):
    """Callback quand un timer sonne : SFX alarm + TTS."""
    _priority_evt.set()
    try:
        sfx_play("alarm", blocking=True)
        if message:
            _tts_wait(f"David ! Rappel : {message}")
        else:
            _tts_wait("David ! Le timer est termine !")
    finally:
        _priority_evt.clear()

# ====================================================================
# MOTEUR KINECT
# ====================================================================
def _run(cmd):
    with _motor_lock:
        if _motor_daemon_mode:
            try:
                with open(MOTOR_CMD_FILE, "w") as f:
                    f.write(cmd)
                log(f"CMD> {cmd}", LOG_FILE, "MOTOR")
            except Exception as e:
                log(f"ERR cmd write: {e}", LOG_FILE, "MOTOR")
        else:
            try:
                subprocess.call([MOTOR_EXE, cmd], creationflags=subprocess.CREATE_NO_WINDOW)
                log(f"OK: {cmd}", LOG_FILE, "MOTOR")
            except Exception as e:
                log(f"ERR _run {cmd}: {e}", LOG_FILE, "MOTOR")

def _run_snap():
    log("snap: debut", LOG_FILE, "SNAP")
    with _motor_lock:
        if _motor_daemon_mode:
            try:
                with open(MOTOR_CMD_FILE, "w") as f:
                    f.write("snap")
                log("snap: commande envoyee au daemon", LOG_FILE, "SNAP")
                time.sleep(5)
                return "OK:snap_via_daemon"
            except Exception as e:
                log(f"ERR snap cmd: {e}", LOG_FILE, "SNAP")
                return None
        for attempt in range(3):
            try:
                result = subprocess.check_output(
                    [MOTOR_EXE, "snap"], creationflags=subprocess.CREATE_NO_WINDOW,
                    stderr=subprocess.DEVNULL, timeout=30
                ).decode(errors="replace").strip()
                log(f"snap: {result}", LOG_FILE, "SNAP")
                if (result.startswith("ERROR:") or result == "") and attempt < 2:
                    time.sleep(2)
                    continue
                return result if result else None
            except subprocess.TimeoutExpired:
                log("ERR snap: timeout", LOG_FILE, "SNAP")
                return None
            except Exception as e:
                log(f"ERR snap: {e}", LOG_FILE, "SNAP")
                return None
    return None

def _launch_motor_daemon():
    global _motor_daemon_mode, _motor_daemon_proc
    if not os.path.exists(MOTOR_EXE):
        log("MOTOR: exe introuvable — mode legacy", LOG_FILE)
        return False
    os.system("taskkill /f /im KinectMotor.exe >nul 2>nul")
    time.sleep(1)
    try:
        proc = subprocess.Popen(
            [MOTOR_EXE, "presence", _KINECT_DIR],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            cwd=_KINECT_DIR
        )
        time.sleep(3)
        if proc.poll() is None:
            _motor_daemon_mode = True
            _motor_daemon_proc = proc
            log(f"MOTOR: daemon lance (PID {proc.pid})", LOG_FILE)
            return True
    except Exception as e:
        log(f"ERR motor daemon: {e}", LOG_FILE)
    return False

# ====================================================================
# VISON
# ====================================================================
_SNAP_MAX_AGE = 10
_VISION_KEYWORDS = [
    "regarde", "tu vois", "vois-tu", "c'est quoi", "qu'est-ce que tu vois",
    "montre", "observe", "devant toi", "camera", "snap",
]

def _find_recent_snap():
    pattern = os.path.join(_KINECT_DIR, "KinectSnap-*.png")
    snaps = glob.glob(pattern)
    if not snaps:
        return None
    snaps.sort(key=os.path.getmtime, reverse=True)
    newest = snaps[0]
    age = time.time() - os.path.getmtime(newest)
    if age <= _SNAP_MAX_AGE:
        log(f"VISION: snap frais ({os.path.basename(newest)}, {age:.1f}s)", LOG_FILE)
        return newest
    return None

def _encode_image_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def _is_vision_request(text):
    t = text.lower()
    return any(kw in t for kw in _VISION_KEYWORDS)

# ====================================================================
# MÉMOIRE LONGUE
# ====================================================================
def _load_memories():
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                memories = json.load(f)
            return memories[-MAX_MEMORIES:]
    except Exception as e:
        log(f"ERR load memories: {e}", LOG_FILE)
    return []

def _save_memory(summary, exchange_count):
    try:
        memories = _load_memories() if os.path.exists(MEMORY_FILE) else []
        entry = {"date": time.strftime("%Y-%m-%d %H:%M"), "summary": summary, "exchanges": exchange_count}
        memories.append(entry)
        if len(memories) > 50:
            memories = memories[-50:]
        tmp = MEMORY_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(memories, f, ensure_ascii=False, indent=2)
        if os.path.exists(MEMORY_FILE):
            os.remove(MEMORY_FILE)
        os.rename(tmp, MEMORY_FILE)
        log(f"MEMORY: souvenir sauve ({exchange_count} echanges)", LOG_FILE)
    except Exception as e:
        log(f"ERR save memory: {e}", LOG_FILE)

def _summarize_session(history):
    if len(history) < 2:
        return None
    try:
        text_history = []
        for msg in history:
            role = "David" if msg["role"] == "user" else "Claudius"
            content = msg["content"]
            if isinstance(content, list):
                content = " ".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
            text_history.append(f"{role}: {content}")
        convo = "\n".join(text_history)
        payload = json.dumps({
            "model": ANTHROPIC_MODEL, "max_tokens": 80,
            "system": "Resume cette conversation en 1-2 phrases courtes en francais.",
            "messages": [{"role": "user", "content": convo}]
        }).encode("utf-8")
        req = urllib.request.Request(ANTHROPIC_URL, data=payload, method="POST", headers={
            "Content-Type": "application/json", "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            summary = json.loads(resp.read().decode())["content"][0]["text"].strip()
        log(f"MEMORY: resume: {summary[:80]}", LOG_FILE)
        return summary
    except Exception as e:
        log(f"ERR summarize: {e}", LOG_FILE)
        return None

def _format_memories_for_prompt():
    memories = _load_memories()
    if not memories:
        return ""
    lines = ["\nSOUVENIRS DES SESSIONS PRECEDENTES:"]
    for m in memories:
        lines.append(f"- [{m['date']}] {m['summary']}")
    lines.append("Utilise ces souvenirs naturellement si pertinent.")
    return "\n".join(lines)

# ====================================================================
# LLM
# ====================================================================
_SYSTEM_FALLBACK = (
    "Tu es Claudius, une tete animatronique Kinect Xbox 360 sur le bureau de David. "
    "Reponds en francais, 1-2 phrases max, naturellement. Pas de markdown."
)
_cached_system_prompt = None
_cached_system_mtime = 0

def _load_system_prompt():
    global _cached_system_prompt, _cached_system_mtime
    for path in [CONTEXT_FILE, os.path.join(_KINECT_DIR, "claudius_context.txt")]:
        try:
            mt = os.path.getmtime(path)
            mem_mt = 0
            try:
                mem_mt = os.path.getmtime(MEMORY_FILE)
            except Exception:
                pass
            cache_key = (mt, mem_mt)
            if _cached_system_prompt and cache_key == _cached_system_mtime:
                return _cached_system_prompt
            with open(path, "r", encoding="utf-8") as f:
                ctx = f.read().strip()
            if ctx:
                memories_text = _format_memories_for_prompt()
                if memories_text:
                    ctx += "\n" + memories_text
                _cached_system_prompt = ctx
                _cached_system_mtime = cache_key
                return ctx
        except Exception:
            continue
    return _SYSTEM_FALLBACK

def _load_settings():
    """Charge les settings dynamiques depuis claudius_settings.json."""
    try:
        with open(os.path.join(_DATA_DIR, "claudius_settings.json"), "r") as f:
            return json.load(f)
    except Exception:
        return {}

# ── Cerveau (Brain) — base de connaissances partagée (optionnelle) ──────────
# Activez via claudius_settings.json : "brain_path": "<dossier de votre Brain>"
# (vide ou absent = désactivé). Le Brain = un dossier de fiches .md avec
# INDEX.md à la racine et projects/<nom>/STATE.md par projet.
_BRAIN_ALIASES = {
    "eldritch_front": ("eldritch",),
    "odysseus": ("odysseus", "dashboard"),
    "aether": ("aether",),
    "gtt": ("gtt", "gamepad", "manette"),
    "hardware_pads": ("capcom", "nes advantage", "pad bluetooth", "manette bluetooth"),
}
_BRAIN_GENERIC = ("cerveau", "brain", "mes projets", "les projets",
                  "ou j'en suis", "où j'en suis", "quoi de neuf")

def _brain_read_capped(path, cap=4000):
    try:
        with open(path, "r", encoding="utf-8") as f:
            t = f.read().strip()
        return t[:cap] + ("\n[... tronqué ...]" if len(t) > cap else "")
    except Exception:
        return ""

def _load_brain_context(user_text):
    """Si la question touche un projet (ou le cerveau en général), injecte la
    fiche pertinente du Brain dans le system prompt. Lecture seule, ciblée."""
    brain = _load_settings().get("brain_path", "")
    if not brain or not os.path.isdir(brain):
        return ""
    low = (user_text or "").lower()
    parts = []
    for proj, aliases in _BRAIN_ALIASES.items():
        if any(a in low for a in aliases):
            state = _brain_read_capped(os.path.join(brain, "projects", proj, "STATE.md"))
            if state:
                parts.append(f"[CERVEAU — état réel et à jour du projet {proj}]\n{state}")
            break
    if not parts and any(g in low for g in _BRAIN_GENERIC):
        idx = _brain_read_capped(os.path.join(brain, "INDEX.md"), 3500)
        if idx:
            parts.append("[CERVEAU — index des projets et connaissances de David]\n" + idx)
    if parts:
        parts.append("(Appuie-toi sur ces infos à jour. Réponse vocale : concise.)")
    return "\n\n".join(parts)

_PROVIDER_URLS = {
    "deepseek": "https://api.deepseek.com/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
}

def _resolve_provider(provider_name, key_setting=""):
    """Résout URL + clé + format API pour un provider donné."""
    p = provider_name.lower().strip()
    is_anthropic = (p == "anthropic")
    url = _PROVIDER_URLS.get(p, _PROVIDER_URLS["deepseek"])
    # Clé : setting custom > fichier local
    if key_setting:
        key = key_setting
    elif is_anthropic:
        key = ANTHROPIC_API_KEY
    else:
        key = DEEPSEEK_API_KEY
    return url, key, is_anthropic

def _ask_claude(text, image_path=None):
    global _conversation_history
    settings = _load_settings()
    max_tokens_llm = settings.get("max_tokens", 500)
    llm_timeout = settings.get("llm_timeout", 25)
    hist_size = settings.get("history_size", MAX_HISTORY)
    v_provider = settings.get("voice_provider", "deepseek")
    v_model = settings.get("voice_model", DEEPSEEK_MODEL)
    s_provider = settings.get("snap_provider", "anthropic")
    s_model = settings.get("snap_model", ANTHROPIC_MODEL)
    temp = settings.get("temperature", 0.7)
    use_vision = image_path is not None
    if use_vision:
        try:
            img_b64 = _encode_image_b64(image_path)
            user_content = [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_b64}},
                {"type": "text", "text": text}
            ]
            log(f"VISION: image attachee ({os.path.basename(image_path)})", LOG_FILE)
        except Exception as e:
            log(f"ERR vision encode: {e}", LOG_FILE)
            user_content = text
            use_vision = False
    else:
        user_content = text

    with _history_lock:
        _conversation_history.append({"role": "user", "content": user_content})
        messages = list(_conversation_history)

    system = _load_system_prompt()
    brain_ctx = _load_brain_context(text)
    if brain_ctx:
        system += "\n\n" + brain_ctx
        log("BRAIN: contexte cerveau injecte dans le prompt", LOG_FILE)
    if use_vision:
        system += ("\n\n[VISION] Tu vois une image de ta camera Kinect. "
                   "Ne decris PAS ce que tu vois sauf si demande explicite. "
                   "Utilise l'image pour COMPRENDRE le contexte.")

    try:
        if use_vision:
            cur_provider, cur_model = s_provider, s_model
            cur_tokens, cur_timeout = 150, 20
        else:
            cur_provider, cur_model = v_provider, v_model
            cur_tokens, cur_timeout = max_tokens_llm, llm_timeout

        # Résolution automatique URL + clé par provider
        v_key_setting = settings.get("voice_api_key", "")
        s_key_setting = settings.get("snap_api_key", "")
        key_setting = s_key_setting if use_vision else v_key_setting
        cur_url, cur_key, is_anthropic = _resolve_provider(cur_provider, key_setting)

        if is_anthropic:
            payload = json.dumps({
                "model": cur_model, "max_tokens": cur_tokens,
                "system": system, "messages": messages
            }).encode("utf-8")
            req = urllib.request.Request(cur_url, data=payload, method="POST", headers={
                "Content-Type": "application/json", "x-api-key": cur_key,
                "anthropic-version": "2023-06-01"
            })
            with urllib.request.urlopen(req, timeout=cur_timeout) as resp:
                reply = json.loads(resp.read().decode())["content"][0]["text"].strip()
        else:
            # Format OpenAI-compatible (DeepSeek, Ollama, OpenRouter, etc.)
            oai_messages = [{"role": "system", "content": system}]
            for m in messages:
                c = m["content"]
                if isinstance(c, list):
                    c = " ".join(b.get("text", "") for b in c if b.get("type") == "text").strip()
                    if not c:
                        continue
                oai_messages.append({"role": m["role"], "content": c})
            payload = json.dumps({
                "model": cur_model, "max_tokens": cur_tokens,
                "messages": oai_messages, "temperature": temp
            }).encode("utf-8")
            req = urllib.request.Request(cur_url, data=payload, method="POST", headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cur_key}"
            })
            with urllib.request.urlopen(req, timeout=cur_timeout) as resp:
                reply = json.loads(resp.read().decode())["choices"][0]["message"]["content"].strip()
                reply = re.sub(r'<think>.*?</think>', '', reply, flags=re.DOTALL).strip()

        tag = "vision" if use_vision else "text"
        log(f"LLM: {cur_provider}/{cur_model} ({tag})", LOG_FILE)

        with _history_lock:
            _conversation_history.append({"role": "assistant", "content": reply})
            if len(_conversation_history) > hist_size * 2:
                _conversation_history = _conversation_history[-(hist_size * 2):]
        return reply
    except Exception as e:
        log(f"ERR llm: {e}", LOG_FILE)
        with _history_lock:
            if _conversation_history and _conversation_history[-1]["role"] == "user":
                _conversation_history.pop()
        return None

# ====================================================================
# GESTES
# ====================================================================
_GESTURE_WORDS = {}
for g, ws in [
    ("oui", ["oui", "absolument", "exactement", "bien sur", "correct", "effectivement"]),
    ("non", ["non", "pas vraiment", "pas du tout", "jamais"]),
    ("hello", ["bonjour", "salut", "hello", "bonsoir"]),
    ("think", ["hmm", "interessant", "voyons", "je pense", "curieux"]),
]:
    for w in ws:
        _GESTURE_WORDS[w] = g

def _gesture_for(text):
    t = text.lower()
    for kw, gesture in _GESTURE_WORDS.items():
        if kw in t:
            return gesture
    return None

def _write_transcript(who, text):
    try:
        ts = time.strftime("%H:%M:%S")
        with open(TRANSCRIPT_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {who}: {text}\n")
    except Exception:
        pass

# ====================================================================
# HANDLE VOICE
# ====================================================================
def _handle_voice(text):
    log(f"VOICE -> {text[:60]}", LOG_FILE)
    if not _speaking.is_set():
        sfx_play("listen", blocking=True)

    # 1. Commandes utilitaires (locales, zéro latence API)
    util_reply = check_utility(text, on_alarm_callback=_on_timer_alarm)
    if util_reply:
        log(f"Util reply: {util_reply[:80]}", LOG_FILE)
        _write_transcript("Claudius", util_reply)
        gesture = _gesture_for(util_reply)
        if gesture:
            threading.Thread(target=_run, args=(gesture,), daemon=True).start()
        _tts_wait(util_reply)
        return

    # 2. Vision ?
    snap_path = None
    if _is_vision_request(text):
        log("VISION: trigger snap", LOG_FILE)
        _run("snap")
        for _ in range(8):
            time.sleep(0.5)
            snap_path = _find_recent_snap()
            if snap_path:
                break
        if not snap_path:
            log("VISION: pas de snap dispo", LOG_FILE)

    # 3. Appel LLM
    result_box = [None]

    def _query():
        try:
            result_box[0] = _ask_claude(text, image_path=snap_path)
        except Exception as e:
            log(f"ERR _query: {e}", LOG_FILE)

    t = threading.Thread(target=_query, daemon=True)
    t.start()
    threading.Thread(target=_run, args=("think",), daemon=True).start()
    t.join(timeout=25 if snap_path else 20)
    reply = result_box[0] or "Desole, je suis hors ligne."

    log(f"VOICE reply: {reply[:80]}", LOG_FILE)
    _write_transcript("Claudius", reply)

    gesture = _gesture_for(reply)
    if gesture:
        threading.Thread(target=_run, args=(gesture,), daemon=True).start()
    _tts_wait(reply)

# ====================================================================
# AUTO-BLINK
# ====================================================================
def _auto_blink():
    import random
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

# ====================================================================
# SLEEP / WAKE
# ====================================================================
def _do_sleep():
    _sleeping.set()
    try:
        open(SLEEP_FILE, "w").close()
    except Exception:
        pass
    _run("reset")
    log("Veille", LOG_FILE)

def _do_wake():
    _sleeping.clear()
    try:
        os.remove(SLEEP_FILE)
    except Exception:
        pass
    sfx_play("wake")
    _run("hello")
    log("Reveil", LOG_FILE)

# ====================================================================
# WATCHER cmd.txt
# ====================================================================
VALID_CMDS = {"oui", "non", "blink", "hello", "think", "reset", "snap", "sleep", "wake"}

def watch_cmd():
    while True:
        try:
            if os.path.exists(CMD_FILE):
                try:
                    with open(CMD_FILE, "r", encoding="utf-8") as f:
                        raw = f.read().strip()
                    os.remove(CMD_FILE)
                except Exception:
                    try:
                        os.remove(CMD_FILE)
                    except Exception:
                        pass
                    time.sleep(0.3)
                    continue

                if not raw:
                    time.sleep(0.3)
                    continue

                cmd = raw.lower()
                if cmd.startswith("voice:"):
                    if _sleeping.is_set():
                        log("VOICE ignore (veille)", LOG_FILE)
                    else:
                        text = raw[6:].strip()
                        if text:
                            _priority_evt.set()
                            try:
                                _handle_voice(text)
                            finally:
                                _priority_evt.clear()
                elif cmd in VALID_CMDS:
                    _priority_evt.set()
                    try:
                        if cmd == "snap":
                            _run_snap()
                        elif cmd == "sleep":
                            _do_sleep()
                        elif cmd == "wake":
                            _do_wake()
                        else:
                            _run(cmd)
                    finally:
                        _priority_evt.clear()
        except Exception as e:
            log(f"watch ERR: {e}", LOG_FILE)
            _priority_evt.clear()
        time.sleep(0.3)

# ====================================================================
# WATCHDOG VOICE
# ====================================================================
_WATCHDOG_INTERVAL = 30
_HEARTBEAT_TIMEOUT = 90
_MAX_RESTARTS = 5
_RESTART_RESET = 600

def _is_pid_alive(pid):
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
    except Exception:
        pass
    return False

def _kill_pid(pid):
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(1, False, pid)
        if h:
            ctypes.windll.kernel32.TerminateProcess(h, 0)
            ctypes.windll.kernel32.CloseHandle(h)
    except Exception:
        pass

def _launch_voice():
    try:
        subprocess.Popen(
            [PYTHON.replace("python.exe", "pythonw.exe"), VOICE_SCRIPT],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            cwd=_KINECT_DIR
        )
        log("WATCHDOG: Voice relance", LOG_FILE)
        return True
    except Exception as e:
        log(f"WATCHDOG ERR: {e}", LOG_FILE)
        return False

def _watchdog_voice():
    restart_count = 0
    last_restart = 0.0
    last_ok_time = time.time()
    time.sleep(15)
    log("WATCHDOG: actif", LOG_FILE)

    while True:
        time.sleep(_WATCHDOG_INTERVAL)
        now = time.time()

        if now - last_ok_time > _RESTART_RESET and restart_count > 0:
            restart_count = 0
            log("WATCHDOG: reset compteur", LOG_FILE)

        if restart_count >= _MAX_RESTARTS:
            if now - last_ok_time < _RESTART_RESET:
                continue
            else:
                restart_count = 0
                log("WATCHDOG: reset timeout", LOG_FILE)

        need_restart, reason = False, ""
        voice_pid = None
        try:
            if os.path.exists(VOICE_PID_FILE):
                voice_pid = int(open(VOICE_PID_FILE).read().strip())
        except (ValueError, OSError):
            pass

        if voice_pid is None:
            need_restart = True
            reason = "PID absent"
        elif not _is_pid_alive(voice_pid):
            need_restart = True
            reason = f"PID {voice_pid} mort"
        else:
            try:
                if os.path.exists(VOICE_HEARTBEAT):
                    hb_time = float(open(VOICE_HEARTBEAT).read().strip())
                    if now - hb_time > _HEARTBEAT_TIMEOUT:
                        need_restart = True
                        reason = f"heartbeat stale ({(now-hb_time):.0f}s)"
                        _kill_pid(voice_pid)
            except (ValueError, OSError):
                pass

        if need_restart:
            if now - last_restart < 60:
                continue
            log(f"WATCHDOG: Voice down — {reason}", LOG_FILE)
            for f in [VOICE_PID_FILE, VOICE_HEARTBEAT, TTS_LOCK_FILE]:
                try:
                    if os.path.exists(f):
                        os.remove(f)
                except Exception:
                    pass
            if _launch_voice():
                restart_count += 1
                last_restart = now
                time.sleep(10)
        else:
            last_ok_time = now

# ====================================================================
# PRESENCE WATCHER
# ====================================================================
_PRESENCE_GREETINGS = {
    "morning": ["Bonjour David !", "Bonjour !"],
    "afternoon": ["Bonjour David !", "Bon apres-midi !"],
    "evening": ["Bonsoir David !", "Bonsoir !"],
}
_PRESENCE_RETURN = ["Re !", "Bon retour !", "Te revoila !"]
_PRESENCE_COOLDOWN = 3600
_PRESENCE_MIN_ABSENCE = 300
_first_greeting_done = False

def _presence_watcher():
    global _first_greeting_done
    last_greeting = 0.0
    was_present = False
    absence_start = 0.0
    memory_saved = False
    log("PRESENCE: watcher actif", LOG_FILE)
    _piper_ready.wait(timeout=30)
    time.sleep(2)

    while True:
        time.sleep(2)
        if _sleeping.is_set() or _speaking.is_set():
            continue
        # Check presence_enabled dans settings
        try:
            with open(os.path.join(_DATA_DIR, "claudius_settings.json"), "r") as f:
                if not json.load(f).get("presence_enabled", True):
                    continue
        except Exception:
            pass

        try:
            if not os.path.exists(PRESENCE_FILE):
                was_present = False
                continue
            with open(PRESENCE_FILE, "r") as f:
                lines = f.read().strip().split("\n")
            if len(lines) < 2:
                continue
            present = (lines[0].strip() == "PRESENT")
        except Exception:
            continue

        now = time.time()

        if not present and was_present:
            absence_start = now
            if not memory_saved:
                with _history_lock:
                    history_copy = list(_conversation_history)
                if len(history_copy) >= 4:
                    memory_saved = True

                    def _do_save():
                        summary = _summarize_session(history_copy)
                        if summary:
                            _save_memory(summary, len(history_copy) // 2)
                    threading.Thread(target=_do_save, daemon=True).start()

        if present and not was_present:
            absence_dur = now - absence_start if absence_start else 9999
            if (now - last_greeting >= _PRESENCE_COOLDOWN) and (absence_dur >= _PRESENCE_MIN_ABSENCE):
                last_greeting = now
                memory_saved = False

                if not _first_greeting_done:
                    hour = int(time.strftime("%H"))
                    period = "morning" if hour < 12 else ("afternoon" if hour < 18 else "evening")
                    greeting = __import__("random").choice(_PRESENCE_GREETINGS[period])
                    _first_greeting_done = True
                else:
                    greeting = __import__("random").choice(_PRESENCE_RETURN)

                _priority_evt.set()
                try:
                    # Skip salutation si on a deja parle recemment
                    if _conversation_history:
                        log("PRESENCE: skip greeting (conversation active)", LOG_FILE)
                    else:
                        sfx_play("presence", blocking=True)
                        threading.Thread(target=_run, args=("hello",), daemon=True).start()
                        _tts_wait(greeting)
                        _write_transcript("Claudius", greeting)
                finally:
                    _priority_evt.clear()

        was_present = present

# ====================================================================
# WATCHDOG MOTOR
# ====================================================================
def _watchdog_motor():
    global _motor_daemon_mode, _motor_daemon_proc
    time.sleep(10)
    log("WATCHDOG MOTOR: actif", LOG_FILE)
    restart_count = 0
    while True:
        time.sleep(15)
        if not _motor_daemon_mode or _motor_daemon_proc is None:
            continue
        if _motor_daemon_proc.poll() is not None:
            log(f"MOTOR: daemon mort (code {_motor_daemon_proc.returncode})", LOG_FILE)
            if restart_count >= 10:
                _motor_daemon_mode = False
                continue
            time.sleep(3)
            if _launch_motor_daemon():
                restart_count += 1

# ====================================================================
# CUDA SETUP
# ====================================================================
def _setup_cuda():
    import site
    for sp in site.getsitepackages():
        for sub in ["nvidia/cublas/bin", "nvidia/cudnn/bin", "nvidia/cufft/bin",
                     "nvidia/cusolver/bin", "nvidia/cusparse/bin", "nvidia/nvjitlink/bin",
                     "nvidia/cuda_runtime/bin"]:
            p = os.path.join(sp, sub)
            if os.path.isdir(p):
                os.environ["PATH"] = p + ";" + os.environ.get("PATH", "")

# ====================================================================
# ENTRYPOINT
# ====================================================================
if __name__ == "__main__":
    _enforce_singleton()
    _cleanup_boot()
    _setup_cuda()

    if not DEEPSEEK_API_KEY:
        log("ERREUR: cle DeepSeek absente (deepseek_key.txt)", LOG_FILE)
    if not ANTHROPIC_API_KEY:
        log("ATTENTION: cle Anthropic absente — vision desactivee", LOG_FILE)

    log("=== KinectBridge v4 demarrage ===", LOG_FILE)

    # Pré-calculer les SFX au boot
    sfx_preload()

    # Lancer les services
    _launch_motor_daemon()
    threading.Thread(target=watch_cmd, daemon=True).start()
    threading.Thread(target=_auto_blink, daemon=True).start()
    threading.Thread(target=_load_piper_bg, daemon=True).start()
    threading.Thread(target=_watchdog_voice, daemon=True).start()
    threading.Thread(target=_watchdog_motor, daemon=True).start()
    threading.Thread(target=_presence_watcher, daemon=True).start()

    log("KinectBridge pret.", LOG_FILE)

    # Boucle principale
    while True:
        time.sleep(60)
