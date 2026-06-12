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
# Du son SORT reellement des enceintes (peak metering, MEME pour les process
# ignores comme le navigateur) -> wake STRICT : une video YouTube qui dit
# « audio » ne reveille plus Claudius, mais « Claudius » exact passe toujours
# (= on peut couper la musique a la voix). Vu en reel 2026-06-12 : des dizaines
# d'utterances de video transcrites, calibration faite en pleine video.
_system_audio_loud = False
_PEAK_THRESHOLD = 0.02
# nos process + navigateurs (onglets media idle) + Wallpaper Engine (session
# active par a-coups en continu : flood mute/unmute vu en reel 2026-06-11)
_AUDIO_IGNORE = {"pythonw.exe", "python.exe", "opera.exe", "comet.exe",
                 "wallpaper64.exe", "wallpaper32.exe"}
# Exclus du peak metering : notre TTS + Wallpaper Engine (ambiance SANS voix
# qui joue quasi en continu — sinon strict permanent, vu en reel 2026-06-12).
# Les navigateurs restent surveilles : c'est eux qui diffusent les videos.
_PEAK_IGNORE = {"pythonw.exe", "python.exe", "wallpaper64.exe", "wallpaper32.exe"}

def _audio_monitor():
    """Thread 0.5s : etat des sessions audio. Deux niveaux :
    - _system_audio_active : session ACTIVE d'un process non ignore -> mute total
    - _system_audio_loud   : du son sort VRAIMENT (peak), tout process sauf les
      notres -> mode wake strict (exact). Hysteresis 2s contre les blancs."""
    global _system_audio_active, _system_audio_loud
    try:
        from pycaw.pycaw import AudioUtilities
    except ImportError:
        _log("pycaw absent — pas de detection audio systeme")
        return
    try:
        from pycaw.pycaw import IAudioMeterInformation
    except ImportError:
        IAudioMeterInformation = None
        _log("pycaw sans IAudioMeterInformation — pas de peak metering (wake strict off)")
    ignore = set(_AUDIO_IGNORE)
    try:
        extra = _load_settings().get("audio_ignore", [])
        ignore |= {str(x).lower() for x in extra}
    except Exception:
        pass
    quiet_ticks = 0
    while True:
        try:
            sessions = AudioUtilities.GetAllSessions()
            active = False
            culprit = ""
            loud_now = False
            loud_culprit = ""
            for s in sessions:
                name = (s.Process.name() if s.Process else "system").lower()
                if s.State == 1 and name not in ignore:  # AudioSessionState.Active
                    active = True
                    culprit = name
                if IAudioMeterInformation is not None and name not in _PEAK_IGNORE and not loud_now:
                    try:
                        peak = s._ctl.QueryInterface(IAudioMeterInformation).GetPeakValue()
                        if peak > _PEAK_THRESHOLD:
                            loud_now = True
                            loud_culprit = name
                    except Exception:
                        pass
            if active != _system_audio_active:
                _system_audio_active = active
                _log(f"Audio systeme: {f'ACTIF ({culprit}) — mute voice' if active else 'inactif — ecoute'}")
            if loud_now:
                quiet_ticks = 0
                if not _system_audio_loud:
                    _system_audio_loud = True
                    _log(f"Son en sortie ({loud_culprit}) — wake STRICT (mot exact requis)")
            elif _system_audio_loud:
                quiet_ticks += 1
                if quiet_ticks >= 4:  # ~2s de silence
                    _system_audio_loud = False
                    _log("Silence en sortie — wake normal (fuzzy)")
        except Exception:
            pass
        time.sleep(0.5)

SAMPLE_RATE     = 16000
CHUNK_DURATION  = 0.1
CHUNK_SAMPLES   = int(SAMPLE_RATE * CHUNK_DURATION)

SILENCE_AFTER   = 0.8
MIN_DURATION    = 0.5
MAX_DURATION    = 8.0

# Chemins portables : relatifs au script, overridables par env
BASE_DIR        = os.environ.get("CLAUDIUS_DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
CMD_FILE        = os.path.join(BASE_DIR, "cmd.txt")
LOG_FILE        = os.path.join(BASE_DIR, "kinect.log")
TRANSCRIPT_FILE = os.path.join(BASE_DIR, "transcript.txt")
TTS_LOCK_FILE   = os.path.join(BASE_DIR, "tts_speaking.lock")
SLEEP_FILE      = os.path.join(BASE_DIR, "claudius_sleep.lock")
HEARTBEAT_FILE  = os.path.join(BASE_DIR, "voice_heartbeat.txt")
PID_FILE        = os.path.join(BASE_DIR, "voice.pid")
SETTINGS_FILE   = os.path.join(BASE_DIR, "claudius_settings.json")

def _load_settings():
    try:
        import json
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

_settings       = _load_settings()
# Reglages pilotes par le dashboard (claudius_settings.json), env = override
FIXED_THRESHOLD = int(os.environ.get("CLAUDIUS_MIC_THRESHOLD",
                                     _settings.get("mic_threshold", 500)))
MODEL_SIZE      = os.environ.get("CLAUDIUS_WHISPER_MODEL",
                                 _settings.get("whisper_model", "small"))
WAKE_WORD       = os.environ.get("CLAUDIUS_WAKE_WORD",
                                 _settings.get("wake_word", "claudius")).strip().lower()
# Micro : choisi PAR NOM (les index glissent quand un peripherique USB
# apparait — vu en reel 2026-06-11 : une manette Nacon a pris l'index 1 du
# Bird UM1 et Claudius ecoutait un micro de casque silencieux).
MIC_NAME        = os.environ.get("CLAUDIUS_MIC_NAME",
                                 _settings.get("mic_name", "BIRD UM1"))
MIC_INDEX_ENV   = os.environ.get("CLAUDIUS_MIC_DEVICE", "")  # index force (debug)

def _resolve_input_device():
    """Retourne (device_id, label). Cherche MIC_NAME dans les devices d'entree
    (hostapi 0 = MME en priorite), sinon index force, sinon defaut systeme."""
    if MIC_INDEX_ENV.strip().lstrip("-").isdigit():
        idx = int(MIC_INDEX_ENV)
        if idx >= 0:
            try:
                return idx, sd.query_devices(idx)["name"] + " (index force)"
            except Exception:
                pass
    needle = MIC_NAME.lower()
    candidates = []
    try:
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0 and needle in d["name"].lower():
                candidates.append((d.get("hostapi", 99), i, d["name"]))
    except Exception as e:
        _log(f"ERR scan devices: {e}")
    if candidates:
        candidates.sort()
        _, idx, name = candidates[0]
        return idx, name
    _log(f"WARN: micro '{MIC_NAME}' introuvable — fallback device par defaut systeme")
    return None, "defaut systeme"

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

# initial_prompt DYNAMIQUE : Whisper ne sait transcrire un nom inventé
# (« Le Glaude », « Cloclo ») QUE s'il l'a vu dans le prompt — sinon il sort
# une utterance VIDE (vecu 2026-06-12 : « Le Glaude » seul -> '' logprob -999).
_INITIAL_PROMPT = (", ".join(t.strip().title() for t in WAKE_WORD.split(",") if t.strip())
                   or "Claudius") + ". Claudius, bonjour. Quelle heure est-il ?"

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
        initial_prompt=_INITIAL_PROMPT,
    )
    seg_list = list(segments)
    text = " ".join(s.text for s in seg_list).strip()
    # Moyenne des log_prob — plus c'est bas, plus c'est louche
    if seg_list:
        avg_lp = sum(s.avg_logprob for s in seg_list) / len(seg_list)
    else:
        avg_lp = -999.0
    return text, avg_lp

# --- Filtre mot-cle wake (configurable, MULTI-TAGS via virgules) ---
# Match fuzzy : cherche le(s) mot(s)-cle ou leurs variantes n'importe ou.
# wake_word peut etre une LISTE : "claudius, claude, clodius" — chaque tag
# ajoute son exact + son noyau phonetique (5 premieres lettres).
_CLAUDIUS_EXACT = {"claudius", "clodius", "clodious", "klodius", "cloudius", "clodeus",
                   "cladius", "clodias", "clodis", "klaudius", "lodius", "laudice",
                   "clodice", "clodisse", "claude", "clodice", "laudis", "lodice"}
# Noyaux phonetiques : « audi »/« audic »/« audiu » RETIRES (2026-06-12) — ils
# matchaient « audio », « audience », « Audi »… = wake fantome sur les videos.
_CLAUDIUS_CORES = ("claud", "clod", "klod", "klaud", "laudic", "lodic", "lodiu")

_WAKE_EXACT = set()
_WAKE_CORES = ()
_WAKE_PHRASES = []  # tags MULTI-MOTS (« le glaude ») : le match mot-a-mot ne
# peut jamais les voir -> regex sous-chaine sur la phrase entiere (bug vecu
# 2026-06-12 : « Le Glaude » configure au dash et totalement ignore)
for _tag in [t.strip() for t in WAKE_WORD.split(",") if t.strip()]:
    if _tag == "claudius":
        _WAKE_EXACT |= _CLAUDIUS_EXACT
        _WAKE_CORES += _CLAUDIUS_CORES
    elif " " in _tag:
        _WAKE_PHRASES.append(re.compile(
            r'\b' + r'[\s-]+'.join(re.escape(w) for w in _tag.split()) + r'\b', re.IGNORECASE))
    else:
        _WAKE_EXACT.add(_tag)
        _WAKE_CORES += ((_tag[:5],) if len(_tag) >= 5 else (_tag,))
if not _WAKE_EXACT and not _WAKE_PHRASES:
    _WAKE_EXACT, _WAKE_CORES = set(_CLAUDIUS_EXACT), _CLAUDIUS_CORES

def _contains_wake_word(text, strict=False):
    """Cherche le mot-cle Claudius n'importe ou dans la phrase.
    Retourne (True, texte_nettoyé) ou (False, text_original).
    Retire le mot-cle et tout ce qui est avant.
    strict=True (du son sort des enceintes) : mots EXACTS seulement, pas de
    noyau phonetique — une video ne reveille pas Claudius, David si."""
    t = text.strip()
    if not t:
        return False, t
    # Tags multi-mots (« le glaude ») : sous-chaine sur la phrase entiere.
    # Exacts par nature -> valides aussi en mode strict.
    for ph in _WAKE_PHRASES:
        m = ph.search(t)
        if m:
            rest = t[m.end():].strip(" ,.:!?")
            if not rest:  # « Quelle heure il est, le Glaude ? » -> garder l'avant
                rest = t[:m.start()].strip(" ,.:!?")
            return True, rest
    words = t.split()
    for i, w in enumerate(words):
        wl = w.lower().strip(".,!?;:'\"")
        # Whisper colle parfois des tirets/points dans le mot (« Clo-clo »)
        wl = wl.replace("-", "").replace(".", "")
        # Check exact
        if wl in _WAKE_EXACT:
            # Garder tout apres le mot-cle
            rest = " ".join(words[i+1:]).strip(" ,.:!?")
            return True, rest
        # Check noyau phonetique
        if not strict:
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
                if not strict:
                    for core in _WAKE_CORES:
                        if core in p:
                            rest = " ".join(words[i+1:]).strip(" ,.:!?")
                            return True, rest
    return False, t

_wake_armed_until = [0.0]  # fenetre « j'ecoute » apres un wake prononce SEUL
WAKE_ARMED_WINDOW = 6.0

def send_voice(text):
    """Envoie le texte transcrit dans cmd.txt si contient 'Claudius'."""
    if is_hallucination(text):
        return
    # Filtre mot-cle : la phrase doit contenir "Claudius" quelque part.
    # Si du son sort des enceintes (video, musique) : mot EXACT requis.
    strict = _system_audio_loud
    has_wake, clean_text = _contains_wake_word(text, strict=strict)
    if not has_wake:
        # « Le Glaude... [pause] ...quelle heure il est » : le decoupage par
        # silence separe le wake de la commande -> fenetre armee 6 s
        if time.time() < _wake_armed_until[0]:
            _wake_armed_until[0] = 0.0
            clean_text = text.strip(" ,.:!?")
            _log(f"Fenetre wake armee — accepte sans mot-cle: {repr(clean_text[:60])}")
        else:
            _log(f"Pas de mot-cle{' (strict, audio en sortie)' if strict else ''}: {repr(text[:60])}")
            return
    if has_wake and not clean_text:
        # Wake sans rien APRES : recuperer ce qu'il y avait AVANT ("Bonjour Claudius")
        t = text.strip()
        words = t.split()
        for i, w in enumerate(words):
            wl = w.lower().strip(".,!?;:'\"").replace("-", "").replace(".", "")
            if wl in _WAKE_EXACT or any(c in wl for c in _WAKE_CORES):
                before = " ".join(words[:i]).strip(" ,.:!?")
                if before:
                    clean_text = before
                break
        if not clean_text:
            # Wake prononce SEUL : bip d'acquittement + on ecoute la suite 6 s
            if os.path.exists(SLEEP_FILE) or os.path.exists(TTS_LOCK_FILE):
                return
            _wake_armed_until[0] = time.time() + WAKE_ARMED_WINDOW
            with _send_lock:
                if not os.path.exists(CMD_FILE):
                    try:
                        with open(CMD_FILE, "w", encoding="utf-8") as f:
                            f.write("ack")
                    except Exception:
                        pass
            _log("Wake seul — bip + fenetre de 6 s sans mot-cle")
            return
    text = clean_text
    if os.path.exists(SLEEP_FILE):
        # Seul le reveil passe (« Claudius reveille-toi ») — le Bridge gere
        if not re.search(r'r[eé]veil|debout', text, re.IGNORECASE):
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
    # Attendre le VRAI silence avant de calibrer : sessions actives ET son en
    # sortie (peak) — avant, une video dans le navigateur (process ignore)
    # faisait calibrer en plein bruit (seuil 2780 vu en reel 2026-06-12)
    if _system_audio_active or _system_audio_loud:
        _log("Calibration: audio systeme actif, attente...")
        for _ in range(60):  # max 30s d'attente
            time.sleep(0.5)
            if not _system_audio_active and not _system_audio_loud:
                break
        if _system_audio_active or _system_audio_loud:
            _log("Calibration: audio toujours actif, calibration forcee")
        else:
            _log("Calibration: audio inactif, go")
            time.sleep(0.5)  # petite marge
    _log(f"Calibration {duration}s — silence svp...")
    levels = [rms(stream.read(CHUNK_SAMPLES)[0]) for _ in range(int(duration / CHUNK_DURATION))]
    ambient = float(np.mean(levels))
    # Seuil = max(FIXED_THRESHOLD, ambiant * 1.5) pour s'adapter au bruit
    threshold = max(FIXED_THRESHOLD, ambient * 1.5)
    # Securite : si seuil anormalement haut, forcer un seuil raisonnable
    if threshold > 3000:
        _log(f"WARN: seuil calibre trop haut ({threshold:.0f}) — force a {FIXED_THRESHOLD}")
        threshold = float(FIXED_THRESHOLD)
    _log(f"Ambiant: {ambient:.0f} -> seuil: {threshold:.0f}")
    return threshold

LEVEL_FILE = os.path.join(BASE_DIR, "voice_level.txt")

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
    last_level_write = 0.0
    level_peak_win = 0.0

    while True:
        chunk, _ = stream.read(CHUNK_SAMPLES)
        level    = rms(chunk)

        # Vu-metre du dashboard : "rms_PEAK;seuil_EFFECTIF" — on ecrit le PIC
        # de la fenetre (l'instantane ratait les pics de voix : jauge inerte)
        if level > level_peak_win:
            level_peak_win = level
        _now = time.time()
        if _now - last_level_write > 0.4:
            last_level_write = _now
            try:
                with open(LEVEL_FILE, "w") as lf:
                    lf.write(f"{level_peak_win:.0f};{threshold:.0f}")
            except Exception:
                pass
            level_peak_win = 0.0

        # TTS actif ou audio systeme (video, musique) : reset silencieux
        if os.path.exists(TTS_LOCK_FILE) or _system_audio_active:
            if recording:
                recording = False; frames = []; t_speech = 0.0; t_silence = 0.0; rms_peak = 0.0
            continue

        if level > threshold:
            if not recording:
                # Anti-flood cooldown (raccourci si fenetre wake armee : la
                # commande arrive juste apres le bip, ne pas la manger)
                cd = 0.5 if time.time() < _wake_armed_until[0] else COOLDOWN
                if time.time() - last_send_time < cd:
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
    mic_id, mic_label = _resolve_input_device()
    _log(f"Audio: {mic_label} (device {mic_id if mic_id is not None else 'auto'}) | seuil={FIXED_THRESHOLD} | wake='{WAKE_WORD}'")

    # Thread detection audio systeme (mute quand video/musique)
    # Lance AVANT calibration pour eviter de calibrer pendant que l'audio joue
    threading.Thread(target=_audio_monitor, daemon=True).start()
    time.sleep(1.5)  # laisser le monitor detecter l'etat audio

    # Thread unique de transcription (pas de threads multiples)
    worker = threading.Thread(target=_transcription_worker, args=(model,), daemon=True)
    worker.start()

    # Thread heartbeat pour le watchdog Bridge
    threading.Thread(target=_heartbeat_loop, daemon=True).start()

    with sd.InputStream(device=mic_id, samplerate=SAMPLE_RATE,
                        channels=1, dtype="int16", blocksize=CHUNK_SAMPLES) as stream:
        threshold = calibrate(stream)
        try:
            listen_loop(model, threshold, stream)
        except KeyboardInterrupt:
            _log("Arret.")
