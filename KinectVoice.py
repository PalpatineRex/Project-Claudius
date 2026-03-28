"""
KinectVoice.py - Reconnaissance vocale Claudius
faster-whisper GPU float16 / CPU int8 fallback
Bird UM1 device 1
--- v2: singleton, queue unique, anti-flood, filtre hallucination renforce ---
"""
import sounddevice as sd
import numpy as np
import time, os, re, threading, queue, sys

# --- Detection audio systeme (mute quand video/musique joue) ---
_system_audio_active = False
_AUDIO_IGNORE = {"pythonw.exe", "python.exe"}  # nos propres process TTS

def _audio_monitor():
    """Thread qui check toutes les 0.5s si du son systeme joue."""
    global _system_audio_active
    try:
        from pycaw.pycaw import AudioUtilities
    except ImportError:
        _log("pycaw absent — pas de detection audio systeme")
        return
    while True:
        try:
            sessions = AudioUtilities.GetAllSessions()
            active = False
            for s in sessions:
                if s.State == 1:  # AudioSessionState.Active
                    name = s.Process.name() if s.Process else "system"
                    if name.lower() not in _AUDIO_IGNORE:
                        active = True
                        break
            if active != _system_audio_active:
                _system_audio_active = active
                _log(f"Audio systeme: {'ACTIF — mute voice' if active else 'inactif — ecoute'}")
        except Exception:
            pass
        time.sleep(0.5)

SAMPLE_RATE     = 16000
CHUNK_DURATION  = 0.1
CHUNK_SAMPLES   = int(SAMPLE_RATE * CHUNK_DURATION)

SILENCE_AFTER   = 0.8
MIN_DURATION    = 0.5
MAX_DURATION    = 8.0
FIXED_THRESHOLD = 500
MODEL_SIZE      = "small"

# Chemins portables : relatifs au script, overridables par env
BASE_DIR        = os.environ.get("CLAUDIUS_DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
CMD_FILE        = os.path.join(BASE_DIR, "cmd.txt")
LOG_FILE        = os.path.join(BASE_DIR, "kinect.log")
TRANSCRIPT_FILE = os.path.join(BASE_DIR, "transcript.txt")
TTS_LOCK_FILE   = os.path.join(BASE_DIR, "tts_speaking.lock")
SLEEP_FILE      = os.path.join(BASE_DIR, "claudius_sleep.lock")
HEARTBEAT_FILE  = os.path.join(BASE_DIR, "voice_heartbeat.txt")
PID_FILE        = os.path.join(BASE_DIR, "voice.pid")
# Micro : index du device (overridable par env, -1 = default systeme)
BIRD_DEVICE_ID  = int(os.environ.get("CLAUDIUS_MIC_DEVICE", "1"))

# --- Singleton : tue les instances precedentes ---
def _enforce_singleton():
    my_pid = os.getpid()
    if os.path.exists(PID_FILE):
        try:
            old_pid = int(open(PID_FILE).read().strip())
            if old_pid != my_pid:
                try:
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    handle = kernel32.OpenProcess(1, False, old_pid)  # PROCESS_TERMINATE
                    if handle:
                        kernel32.TerminateProcess(handle, 0)
                        kernel32.CloseHandle(handle)
                except Exception:
                    pass
                time.sleep(0.5)
        except (ValueError, OSError):
            pass
    with open(PID_FILE, "w") as f:
        f.write(str(my_pid))

# Hallucinations Whisper — mots-cles en minuscule
HALLUCINATION_KEYWORDS = [
    "amara", "sous-titr", "sous titr", "wikimedia", "creative commons",
    "merci d'avoir regard", "merci d avoir regard",
    "n'oubliez pas", "abonnez", "likez", "partagez",
    "youtube.com", "twitter.com", "facebook.com",
    "inscrivez", "commentez", "cliquez",
    "merci pour votre", "a bientot", "à bientôt",
    "bienvenue sur", "bienvenue dans",
]

# Queue unique pour serialiser les transcriptions
_transcribe_queue = queue.Queue(maxsize=3)
_send_lock = threading.Lock()

# --- Heartbeat : ecrit un timestamp toutes les 10s pour le watchdog ---
def _heartbeat_loop():
    while True:
        try:
            with open(HEARTBEAT_FILE, "w") as f:
                f.write(str(time.time()))
        except Exception:
            pass
        time.sleep(10)

def _log(msg):
    line = f"[VOICE {time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def _write_transcript(speaker, text):
    try:
        with open(TRANSCRIPT_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {speaker}: {text}\n")
    except Exception:
        pass

def rms(chunk):
    return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))

def _clean(text):
    return text.lower().replace("\u2019", "'").replace("\u2018", "'").replace("\u2032", "'")

def is_hallucination(text):
    t = text.strip()
    if not t:
        return True
    tc = _clean(t)
    for kw in HALLUCINATION_KEYWORDS:
        if kw in tc:
            _log(f"Hallucination filtree: {repr(t[:60])}")
            return True
    # Ponctuation seule
    if len(re.sub(r"[^\w]", "", t)) < 3:
        _log(f"Hallucination (trop court/ponctuation): {repr(t[:60])}")
        return True
    # Moins de 2 vrais mots
    if len(re.findall(r"[a-zA-Z\u00C0-\u024F]{2,}", t)) < 2:
        _log(f"Hallucination (< 2 mots): {repr(t[:60])}")
        return True
    return False

def transcribe(frames, model):
    audio = np.concatenate(frames).flatten().astype(np.float32) / 32768.0
    segments, info = model.transcribe(
        audio,
        language="fr",
        beam_size=5,
        vad_filter=False,
        no_speech_threshold=0.4,
        log_prob_threshold=-0.5,
        compression_ratio_threshold=2.4,
        initial_prompt="Claudius, bonjour. Claudius, comment ça va ?",
    )
    seg_list = list(segments)
    text = " ".join(s.text for s in seg_list).strip()
    # Moyenne des log_prob — plus c'est bas, plus c'est louche
    if seg_list:
        avg_lp = sum(s.avg_logprob for s in seg_list) / len(seg_list)
    else:
        avg_lp = -999.0
    return text, avg_lp

# --- Filtre mot-cle "Claudius" ---
# Match fuzzy : cherche "claudius" ou variantes n'importe ou dans la phrase
_WAKE_EXACT = {"claudius", "clodius", "clodious", "klodius", "cloudius", "clodeus",
               "cladius", "clodias", "clodis", "klaudius", "lodius", "laudice",
               "clodice", "clodisse", "claude", "clodice", "laudis", "lodice"}
# Noyaux phonetiques — si un mot les contient, c'est probablement "Claudius"
_WAKE_CORES = ("claud", "clod", "klod", "klaud", "laudic", "lodic", "lodiu", "audiu", "audic", "audi")

def _contains_wake_word(text):
    """Cherche le mot-cle Claudius n'importe ou dans la phrase.
    Retourne (True, texte_nettoyé) ou (False, text_original).
    Retire le mot-cle et tout ce qui est avant."""
    t = text.strip()
    if not t:
        return False, t
    words = t.split()
    for i, w in enumerate(words):
        wl = w.lower().strip(".,!?;:'\"")
        # Check exact
        if wl in _WAKE_EXACT:
            # Garder tout apres le mot-cle
            rest = " ".join(words[i+1:]).strip(" ,.:!?")
            return True, rest
        # Check noyau phonetique
        for core in _WAKE_CORES:
            if core in wl:
                rest = " ".join(words[i+1:]).strip(" ,.:!?")
                return True, rest
        # Check apostrophe split (ex: "l'audice")
        if "'" in wl:
            parts = wl.split("'")
            for p in parts:
                if p in _WAKE_EXACT:
                    rest = " ".join(words[i+1:]).strip(" ,.:!?")
                    return True, rest
                for core in _WAKE_CORES:
                    if core in p:
                        rest = " ".join(words[i+1:]).strip(" ,.:!?")
                        return True, rest
    return False, t

def send_voice(text):
    """Envoie le texte transcrit dans cmd.txt si contient 'Claudius'."""
    if is_hallucination(text):
        return
    # Filtre mot-cle : la phrase doit contenir "Claudius" quelque part
    has_wake, clean_text = _contains_wake_word(text)
    if not has_wake:
        _log(f"Pas de mot-cle: {repr(text[:60])}")
        return
    if not clean_text:
        # Juste le mot-cle (ex: "Bonjour Claudius") — envoyer "bonjour" comme contenu
        has_wake2, _ = _contains_wake_word(text)
        # Recup le texte avant le mot-cle comme contenu
        t = text.strip()
        words = t.split()
        for i, w in enumerate(words):
            wl = w.lower().strip(".,!?;:'\"")
            if wl in _WAKE_EXACT or any(c in wl for c in _WAKE_CORES):
                before = " ".join(words[:i]).strip(" ,.:!?")
                if before:
                    text = before
                    break
                else:
                    text = "bonjour"
                    break
                break
        else:
            text = "bonjour"
    text = clean_text
    if os.path.exists(SLEEP_FILE):
        _log("Veille — ignore"); return
    if os.path.exists(TTS_LOCK_FILE):
        _log("TTS actif — ignore"); return
    with _send_lock:
        if os.path.exists(CMD_FILE):
            _log("cmd.txt occupe — ignore"); return
        try:
            with open(CMD_FILE, "w", encoding="utf-8") as f:
                f.write("VOICE:" + text)
            _write_transcript("David", text)
            _log(f">>> {text}")
        except Exception as e:
            _log(f"ERR send: {e}")

def _transcription_worker(model):
    """Thread unique qui depile les utterances une par une."""
    while True:
        frames = _transcribe_queue.get()
        if frames is None:
            break
        try:
            # Pre-filtre : energie moyenne de l'utterance
            audio_all = np.concatenate(frames).flatten()
            avg_rms = float(np.sqrt(np.mean(audio_all.astype(np.float32) ** 2)))
            if avg_rms < FIXED_THRESHOLD * 0.7:
                _log(f"Pre-filtre RMS moyen trop bas ({avg_rms:.0f}) — skip")
                continue
            t0 = time.time()
            txt, avg_lp = transcribe(frames, model)
            dt = time.time() - t0
            _log(f"Transcrit en {dt:.2f}s (logprob={avg_lp:.2f})")
            # Filtre log_prob : en dessous de -0.7, Whisper n'est pas confiant
            if avg_lp < -0.7:
                _log(f"Logprob trop bas ({avg_lp:.2f}) — ignore: {repr(txt[:60])}")
                continue
            send_voice(txt)
        except Exception as e:
            _log(f"ERR transcribe: {e}")

def calibrate(stream, duration=2.0):
    _log(f"Calibration {duration}s — silence svp...")
    levels = [rms(stream.read(CHUNK_SAMPLES)[0]) for _ in range(int(duration / CHUNK_DURATION))]
    ambient = float(np.mean(levels))
    # Seuil = max(FIXED_THRESHOLD, ambiant * 1.5) pour s'adapter au bruit
    threshold = max(FIXED_THRESHOLD, ambient * 1.5)
    _log(f"Ambiant: {ambient:.0f} -> seuil: {threshold:.0f}")
    return threshold

def listen_loop(model, threshold, stream):
    _log(f"Ecoute active — seuil RMS={threshold:.0f}")
    recording = False
    frames    = []
    t_silence = 0.0
    t_speech  = 0.0
    rms_peak  = 0.0
    # Anti-flood : cooldown apres envoi d'une utterance
    last_send_time = 0.0
    COOLDOWN = 2.0  # secondes minimum entre deux envois

    while True:
        chunk, _ = stream.read(CHUNK_SAMPLES)
        level    = rms(chunk)

        # TTS actif ou audio systeme (video, musique) : reset silencieux
        if os.path.exists(TTS_LOCK_FILE) or _system_audio_active:
            if recording:
                recording = False; frames = []; t_speech = 0.0; t_silence = 0.0; rms_peak = 0.0
            continue

        if level > threshold:
            if not recording:
                # Anti-flood cooldown
                if time.time() - last_send_time < COOLDOWN:
                    continue
                recording = True; frames = []; t_speech = 0.0; t_silence = 0.0
            frames.append(chunk.copy())
            t_speech += CHUNK_DURATION
            t_silence = 0.0
            if level > rms_peak:
                rms_peak = level
            if t_speech >= MAX_DURATION:
                _log(f"MAX_DURATION ({rms_peak:.0f} peak)")
                try:
                    _transcribe_queue.put_nowait(frames[:])
                except queue.Full:
                    _log("Queue pleine — utterance ignoree")
                last_send_time = time.time()
                recording = False; frames = []; t_speech = 0.0; t_silence = 0.0; rms_peak = 0.0
        else:
            if recording:
                frames.append(chunk.copy())
                t_silence += CHUNK_DURATION
                if t_silence >= SILENCE_AFTER:
                    if t_speech >= MIN_DURATION:
                        _log(f"Fin utterance ({t_speech:.1f}s, RMS peak={rms_peak:.0f})")
                        try:
                            _transcribe_queue.put_nowait(frames[:])
                        except queue.Full:
                            _log("Queue pleine — utterance ignoree")
                        last_send_time = time.time()
                    else:
                        pass  # Trop court — silencieux pour ne pas polluer les logs
                    recording = False; frames = []; t_speech = 0.0; t_silence = 0.0; rms_peak = 0.0

# --- Entrypoint ---

if __name__ == "__main__":
    _enforce_singleton()

    # CUDA DLLs — chercher automatiquement dans site-packages nvidia
    import site
    for sp in site.getsitepackages():
        for sub in ["nvidia/cublas/bin", "nvidia/cudnn/bin"]:
            p = os.path.join(sp, sub)
            if os.path.isdir(p):
                os.environ["PATH"] = p + ";" + os.environ.get("PATH", "")
    try:
        import ctranslate2
        ctranslate2.get_supported_compute_types("cuda")
        device, compute = "cuda", "float16"
    except Exception:
        device, compute = "cpu", "int8"
    _log(f"Chargement faster-whisper '{MODEL_SIZE}' ({device} {compute})...")

    from faster_whisper import WhisperModel
    model = WhisperModel(MODEL_SIZE, device=device, compute_type=compute)
    _log(f"Modele pret. [{device.upper()} {compute}]")
    try:
        dev_info = sd.query_devices(BIRD_DEVICE_ID)
        _log(f"Audio: {dev_info['name']} (device {BIRD_DEVICE_ID})")
    except Exception:
        _log(f"Audio: device {BIRD_DEVICE_ID} (info indispo)")

    # Thread unique de transcription (pas de threads multiples)
    worker = threading.Thread(target=_transcription_worker, args=(model,), daemon=True)
    worker.start()

    # Thread detection audio systeme (mute quand video/musique)
    threading.Thread(target=_audio_monitor, daemon=True).start()

    # Thread heartbeat pour le watchdog Bridge
    threading.Thread(target=_heartbeat_loop, daemon=True).start()

    with sd.InputStream(device=BIRD_DEVICE_ID, samplerate=SAMPLE_RATE,
                        channels=1, dtype="int16", blocksize=CHUNK_SAMPLES) as stream:
        threshold = calibrate(stream)
        try:
            listen_loop(model, threshold, stream)
        except KeyboardInterrupt:
            _log("Arret.")
