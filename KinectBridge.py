"""
KinectBridge.py - Pont principal Project Claudius
Tete animatronique Kinect Xbox 360.

LLM   : Claude Haiku via API Anthropic
TTS   : Piper Jessica+SIWIS blend spectral (CUDA)
Audio : sounddevice (cross-platform, RAM)
Moteur: KinectMotor.exe (oui/non/blink/hello/think/reset/snap)
Cmds  : oui/non/blink/hello/think/reset/snap/sleep/wake + VOICE:texte

https://github.com/PalpatineRex/Project-Claudius
"""
import subprocess, os, time, threading, random, json, sys, re
import urllib.request
import numpy as np
import sounddevice as sd
try:
    from scipy.ndimage import uniform_filter1d as _smooth1d
except ImportError:
    _smooth1d = None

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
VOICE_PID_FILE    = os.path.join(_DATA_DIR, "voice.pid")
VOICE_HEARTBEAT   = os.path.join(_DATA_DIR, "voice_heartbeat.txt")
VOICE_SCRIPT      = os.path.join(_KINECT_DIR, "KinectVoice.py")

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
        if _log_count >= 500:
            _log_count = 0
            try:
                size = os.path.getsize(LOG_FILE)
                # ~80 chars/ligne * LOG_MAX_LINES = ~160KB. Si le fichier est petit, skip.
                if size > LOG_MAX_LINES * 100:
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
    """Blend Jessica+SIWIS — DTW spectral + warp continu + blend spectral (fusion DBZ v3d).
    
    1. Features spectrales (mel bands 13) par segment 25ms → alignement phonemique
    2. DTW cosine sur features → warping path
    3. Warp continu np.interp → SIWIS alignee sample par sample
    4. STFT vectorisee + blend magnitudes + phase Jessica
    5. Gate silence + HF preserve consonnes + conservation energie
    """
    sr = 22050
    seg_len = int(sr * 0.025)  # 25ms = 551 samples (2x plus fin)
    n_mel = 13  # bandes spectrales pour l'alignement
    
    j = j_audio.astype(np.float64)
    s = s_audio.astype(np.float64)
    nj = max(1, len(j) // seg_len)
    ns = max(1, len(s) // seg_len)
    
    # --- Features spectrales vectorisees (mel-like bands) ---
    def _mel_features(audio, seg, n_bands):
        n_segs = len(audio) // seg
        if n_segs == 0:
            return np.zeros((1, n_bands))
        # Reshape + FFT batch (pas de boucle Python)
        trimmed = audio[:n_segs * seg].reshape(n_segs, seg)
        specs = np.abs(np.fft.rfft(trimmed, axis=1)) ** 2  # (n_segs, n_freq)
        n_freq = specs.shape[1]
        bsz = max(1, n_freq // n_bands)
        # Somme par bande via reshape+sum (pad si necessaire)
        pad_len = bsz * n_bands - n_freq
        if pad_len > 0:
            specs = np.pad(specs, ((0,0),(0,pad_len)))
        feats = specs[:, :bsz * n_bands].reshape(n_segs, n_bands, bsz).sum(axis=2)
        return feats
    
    fj = _mel_features(j, seg_len, n_mel)
    fs = _mel_features(s, seg_len, n_mel)
    
    # Distance cosine (meilleure que L2 pour comparer des spectres)
    fj_n = fj / (np.linalg.norm(fj, axis=1, keepdims=True) + 1e-10)
    fs_n = fs / (np.linalg.norm(fs, axis=1, keepdims=True) + 1e-10)
    dist = 1.0 - fj_n @ fs_n.T  # (nj, ns) cosine distance
    
    # --- DTW (acces array direct, evite min() Python) ---
    cost = np.full((nj + 1, ns + 1), np.inf)
    cost[0, 0] = 0.0
    # Acces direct aux arrays pour eviter l'overhead Python de min()
    cost_flat = cost.ravel()
    stride = ns + 1
    for i in range(1, nj + 1):
        di = dist[i - 1]  # (ns,) distances pour cette ligne
        base = i * stride
        base_prev = (i - 1) * stride
        for k in range(1, ns + 1):
            d = di[k - 1]
            c_diag = cost_flat[base_prev + k - 1]
            c_up   = cost_flat[base_prev + k]
            c_left = cost_flat[base + k - 1]
            # Inline min — plus rapide que min() builtin sur 3 args
            m = c_diag
            if c_up < m: m = c_up
            if c_left < m: m = c_left
            cost_flat[base + k] = d + m
    
    # Backtrack
    path = []
    i, k = nj, ns
    while i > 0 or k > 0:
        if i > 0 and k > 0:
            path.append((i-1, k-1))
        elif i > 0:
            path.append((i-1, max(0, k-1)))
        else:
            break
        choices = []
        if i > 0 and k > 0: choices.append((cost[i-1, k-1], i-1, k-1))
        if i > 0:            choices.append((cost[i-1, k],   i-1, k))
        if k > 0:            choices.append((cost[i, k-1],   i,   k-1))
        _, ni, nk = min(choices)
        if ni == i and nk == k:
            break
        i, k = ni, nk
    path.reverse()
    
    # --- Warp continu ---
    path_arr = np.array(path)  # (N, 2)
    j_anchors = (path_arr[:, 0] + 0.5) * seg_len
    s_anchors = (path_arr[:, 1] + 0.5) * seg_len
    n_out = nj * seg_len
    s_positions = np.clip(np.interp(np.arange(n_out, dtype=np.float64), j_anchors, s_anchors), 0, len(s) - 1)
    s_idx = s_positions.astype(np.int64)
    s_frac = s_positions - s_idx
    s_idx_next = np.minimum(s_idx + 1, len(s) - 1)
    s_warped = s[s_idx] * (1.0 - s_frac) + s[s_idx_next] * s_frac
    
    # --- Blend spectral ---
    j_trimmed = j[:n_out]
    n_fft = 2048
    hop = 512
    win = np.hanning(n_fft)
    n_frames = (n_out - n_fft) // hop + 1
    if n_frames < 1:
        out = j_trimmed * (1.0 - ratio) + s_warped * ratio
    else:
        # STFT vectorisee
        starts = np.arange(n_frames) * hop
        idx = starts[:, None] + np.arange(n_fft)[None, :]
        J = np.fft.rfft(j_trimmed[idx] * win[None, :], axis=1).T
        S = np.fft.rfft(s_warped[idx] * win[None, :], axis=1).T
        mag_j = np.abs(J)
        mag_s = np.abs(S)
        phase_j = np.angle(J)
        n_bins = n_fft // 2 + 1
        
        # --- Gate ameliore : silence + transitions rapides ---
        # RMS par segment vectorise (utilise pour le gate, pas pour le DTW)
        j_segs = j[:nj * seg_len].reshape(nj, seg_len)
        env_j = np.sqrt(np.mean(j_segs ** 2, axis=1))
        env_j_peak = np.max(env_j) if nj > 0 else 1.0
        gate_thresh = env_j_peak * 0.12  # 12% plus agressif
        gate_seg = np.where(env_j > gate_thresh, 1.0, (env_j / gate_thresh) ** 2)  # courbe quadratique = fade plus rapide
        gate_centers = (np.arange(nj) + 0.5) * seg_len
        frame_centers = np.arange(n_frames, dtype=np.float64) * hop + n_fft // 2
        gate_frames = np.clip(np.interp(frame_centers, gate_centers, gate_seg), 0.0, 1.0)
        
        # HF preserve — consonnes Jessica >4kHz
        freq_bins = np.arange(n_bins) * sr / n_fft
        hf_mask = np.ones(n_bins)
        hf_zone = (freq_bins > 4000) & (freq_bins <= 8000)
        hf_mask[hf_zone] = 1.0 - 0.7 * (freq_bins[hf_zone] - 4000) / 4000
        hf_mask[freq_bins > 8000] = 0.3
        
        # Detecteur de transitoires : frames ou l'energie change vite = consonnes
        # Sur ces frames, reduire fortement SIWIS pour garder la nettete Jessica
        energy_per_frame = np.sum(mag_j ** 2, axis=0)
        energy_diff = np.abs(np.diff(energy_per_frame, prepend=energy_per_frame[0]))
        energy_median = np.median(energy_per_frame) + 1e-10
        transient_score = energy_diff / energy_median
        # transient_mask: 1.0 = voyelle stable, 0.3 = consonne/transitoire
        transient_mask = np.where(transient_score > 0.5, 0.3, 1.0)
        # Smooth pour pas de coupure brutale
        if _smooth1d is not None:
            transient_mask = _smooth1d(transient_mask, size=3)
        
        eff_ratio = ratio * gate_frames[None, :] * hf_mask[:, None] * transient_mask[None, :]
        mag_blend = mag_j * (1.0 - eff_ratio) + mag_s * eff_ratio
        
        # Conservation d'energie frame-par-frame : le blend ne doit pas
        # reduire le volume par rapport a Jessica
        energy_j = np.sum(mag_j ** 2, axis=0)  # energie par frame
        energy_b = np.sum(mag_blend ** 2, axis=0)
        gain = np.where(energy_b > 0, np.sqrt(energy_j / energy_b), 1.0)
        mag_blend *= gain[None, :]
        
        # iSTFT vectorisee overlap-add (np.add.at evite la boucle Python)
        blend_frames = np.fft.irfft(mag_blend * np.exp(1j * phase_j), axis=0).T  # (n_frames, n_fft)
        blend_frames *= win[None, :]
        win_sq = win ** 2
        out = np.zeros(n_out, dtype=np.float64)
        win_sum = np.zeros(n_out, dtype=np.float64)
        # Indices vectorises pour overlap-add sans boucle
        frame_idx = np.arange(n_frames)[:, None]  # (n_frames, 1)
        sample_idx = np.arange(n_fft)[None, :]    # (1, n_fft)
        target_idx = (frame_idx * hop + sample_idx).ravel()  # indices absolus
        np.add.at(out, target_idx, blend_frames.ravel())
        np.add.at(win_sum, target_idx, np.tile(win_sq, n_frames))
        stable_mask = win_sum > 0.1
        out[stable_mask] /= win_sum[stable_mask]
        out[~stable_mask] = j_trimmed[~stable_mask]
    
    # --- Normalisation (volume fort) ---
    peak = np.max(np.abs(out))
    if peak > 0:
        out *= 31000.0 / peak
    return out.astype(np.float32)

# --- Re-accentuation FR (pre-TTS) ---
# Piper prononce mal les mots sans accents (e muet au lieu de é/è/ê)
# Dictionnaire: mot sans accent -> mot avec accent
_ACCENT_MAP = {
    "tete": "tête", "tetes": "têtes", "tres": "très", "ete": "été",
    "pere": "père", "mere": "mère", "frere": "frère", "fete": "fête",
    "bete": "bête", "pret": "prêt", "prete": "prête", "foret": "forêt",
    "fenetre": "fenêtre", "interet": "intérêt", "arret": "arrêt",
    "desole": "désolé", "desolee": "désolée", "idee": "idée",
    "interessant": "intéressant", "interessante": "intéressante",
    "interesse": "intéressé", "interessee": "intéressée",
    "prefere": "préféré", "preferer": "préférer", "preferes": "préférés",
    "repete": "répète", "repeter": "répéter", "cree": "créé",
    "creee": "créée", "general": "général", "generale": "générale",
    "probleme": "problème", "problemes": "problèmes",
    "systeme": "système", "systemes": "systèmes",
    "theme": "thème", "modele": "modèle", "modeles": "modèles",
    "premiere": "première", "derniere": "dernière", "lumiere": "lumière",
    "maniere": "manière", "matiere": "matière", "entiere": "entière",
    "different": "différent", "differente": "différente",
    "developpement": "développement", "developper": "développer",
    "evenement": "événement", "element": "élément", "elements": "éléments",
    "experience": "expérience", "necessaire": "nécessaire",
    "reponse": "réponse", "repondre": "répondre",
    "energie": "énergie", "securite": "sécurité", "realite": "réalité",
    "verite": "vérité", "societe": "société", "qualite": "qualité",
    "liberte": "liberté", "beaute": "beauté", "egalite": "égalité",
    "deja": "déjà", "voila": "voilà", "la": "là", "ou": "où",
    "a": "à",  # preposition
    "evidemment": "évidemment", "generalement": "généralement",
    "particulierement": "particulièrement", "completement": "complètement",
    "immediatement": "immédiatement", "reellement": "réellement",
    "eventuellement": "éventuellement", "sincerement": "sincèrement",
    "etait": "était", "etaient": "étaient", "etes": "êtes",
    "etat": "état", "etats": "états", "ecran": "écran",
    "ecouter": "écouter", "ecoute": "écoute", "ecrit": "écrit",
    "ecrire": "écrire", "electrique": "électrique",
    "electronique": "électronique", "regle": "règle", "regles": "règles",
    "reveil": "réveil", "reveler": "révéler", "eleve": "élève",
    "celebre": "célèbre", "colere": "colère", "derriere": "derrière",
    "legere": "légère", "leger": "léger", "severe": "sévère",
    "numero": "numéro", "opera": "opéra", "cafe": "café",
    "resume": "résumé", "passe": "passé", "cote": "côté",
}

_ACCENT_RE = re.compile(r"^([A-Za-zÀ-ÿ'-]+)(.*)")
_AVOIR_SUBJECTS = frozenset(("il", "elle", "on", "qui", "david", "claudius", "ca", "cela", "tout", "ça"))

def _reaccentuate(text):
    """Remet les accents FR sur les mots courants avant envoi a Piper."""
    words = text.split()
    out = []
    for idx, w in enumerate(words):
        match = _ACCENT_RE.match(w)
        if not match:
            out.append(w)
            continue
        core, punct = match.group(1), match.group(2)
        lower = core.lower()
        # Cas special "a" -> "à" seulement si c'est la preposition
        if lower == "a":
            prev = words[idx-1].lower().rstrip(".,!?;:") if idx > 0 else ""
            if prev in _AVOIR_SUBJECTS:
                out.append(w)  # verbe avoir, pas de changement
                continue
        if lower in _ACCENT_MAP:
            repl = _ACCENT_MAP[lower]
            # Preserver la casse
            if core[0].isupper():
                repl = repl[0].upper() + repl[1:]
            if core.isupper():
                repl = repl.upper()
            out.append(repl + punct)
        else:
            out.append(w)
    return " ".join(out)

def _tts_wait(text):
    text = _reaccentuate(text)  # accents FR avant Piper
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
                    # Audio toujours en range int16 (peak ~31000) -> normalise [-1, 1]
                    sd.play(audio_data / 32768.0, samplerate=sample_rate)
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
    for path in [CONTEXT_FILE, os.path.join(_KINECT_DIR, "claudius_context.txt")]:
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

# Mots-cles -> geste, scanne une seule fois
_GESTURE_WORDS = {}
for _g, _ws in [
    ("oui",   ["oui","absolument","exactement","bien sur","correct","effectivement"]),
    ("non",   ["non","pas vraiment","pas du tout","jamais"]),
    ("hello", ["bonjour","salut","hello","bonsoir"]),
    ("think", ["hmm","interessant","voyons","je pense","curieux"]),
]:
    for _w in _ws:
        _GESTURE_WORDS[_w] = _g

def _gesture_for(text):
    t = text.lower()
    for kw, gesture in _GESTURE_WORDS.items():
        if kw in t:
            return gesture
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

# --- Watchdog Voice ---

_WATCHDOG_INTERVAL = 30    # secondes entre chaque check
_HEARTBEAT_TIMEOUT = 90    # secondes sans heartbeat = Voice figé
_RESTART_COOLDOWN  = 60    # secondes minimum entre deux relances
_MAX_RESTARTS      = 5     # max relances avant abandon (reset au bout de 10 min OK)
_RESTART_RESET     = 600   # secondes de fonctionnement OK pour reset le compteur

def _is_pid_alive(pid):
    """Verifie si un PID Windows existe encore."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False

def _kill_pid(pid):
    """Tue un process Windows par PID."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(1, False, pid)  # PROCESS_TERMINATE
        if handle:
            kernel32.TerminateProcess(handle, 0)
            kernel32.CloseHandle(handle)
    except Exception:
        pass

def _launch_voice():
    """Lance KinectVoice.py en background."""
    try:
        subprocess.Popen(
            [PYTHON.replace("python.exe", "pythonw.exe"), VOICE_SCRIPT],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            cwd=_KINECT_DIR
        )
        _log("WATCHDOG: Voice relance")
        return True
    except Exception as e:
        _log(f"WATCHDOG ERR: impossible de lancer Voice: {e}")
        return False

def _watchdog_voice():
    """Thread watchdog — surveille Voice via PID + heartbeat, relance si mort/fige."""
    restart_count = 0
    last_restart = 0.0
    last_ok_time = time.time()

    # Attendre que Voice ait eu le temps de demarrer
    time.sleep(15)
    _log("WATCHDOG: actif — surveillance Voice")

    while True:
        time.sleep(_WATCHDOG_INTERVAL)
        now = time.time()

        # Reset compteur si Voice tourne bien depuis longtemps
        if now - last_ok_time > _RESTART_RESET and restart_count > 0:
            _log(f"WATCHDOG: Voice stable depuis {_RESTART_RESET}s — reset compteur ({restart_count}->0)")
            restart_count = 0

        # Max restarts atteint?
        if restart_count >= _MAX_RESTARTS:
            _log(f"WATCHDOG: {_MAX_RESTARTS} relances — abandon (check manuellement)")
            # Attend le reset timeout avant de reessayer
            if now - last_ok_time < _RESTART_RESET:
                continue
            else:
                restart_count = 0
                _log("WATCHDOG: reset apres timeout — reprend surveillance")

        need_restart = False
        reason = ""

        # Check 1 : PID vivant?
        voice_pid = None
        try:
            if os.path.exists(VOICE_PID_FILE):
                voice_pid = int(open(VOICE_PID_FILE).read().strip())
        except (ValueError, OSError):
            pass

        if voice_pid is None:
            need_restart = True
            reason = "PID file absent"
        elif not _is_pid_alive(voice_pid):
            need_restart = True
            reason = f"PID {voice_pid} mort"
        else:
            # Check 2 : heartbeat recent?
            try:
                if os.path.exists(VOICE_HEARTBEAT):
                    hb_time = float(open(VOICE_HEARTBEAT).read().strip())
                    age = now - hb_time
                    if age > _HEARTBEAT_TIMEOUT:
                        need_restart = True
                        reason = f"heartbeat stale ({age:.0f}s)"
                        # Tuer le process fige
                        _kill_pid(voice_pid)
                        time.sleep(1)
                else:
                    # Pas de heartbeat file — Voice trop ancien ou n'a pas encore ecrit
                    # On ne relance pas pour ca, juste un warning
                    pass
            except (ValueError, OSError):
                pass

        if need_restart:
            # Cooldown entre relances
            if now - last_restart < _RESTART_COOLDOWN:
                continue
            _log(f"WATCHDOG: Voice down — {reason}")
            # Nettoyer les fichiers residuels
            for f in [VOICE_PID_FILE, VOICE_HEARTBEAT, TTS_LOCK_FILE]:
                try:
                    if os.path.exists(f): os.remove(f)
                except Exception: pass
            if _launch_voice():
                restart_count += 1
                last_restart = now
                _log(f"WATCHDOG: relance #{restart_count}/{_MAX_RESTARTS}")
                # Attendre que Voice demarre
                time.sleep(10)
        else:
            last_ok_time = now

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
    threading.Thread(target=_watchdog_voice, daemon=True).start()
    _log("KinectBridge pret. (watchdog Voice actif)")
    while True:
        time.sleep(60)
