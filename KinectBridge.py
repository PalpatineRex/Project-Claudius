"""
KinectBridge.py - Pont principal Project Claudius
Tete animatronique Kinect Xbox 360.

LLM   : DeepSeek V4 Flash (texte) + Claude Haiku (vision)
TTS   : Piper Jessica+SIWIS blend spectral (CUDA)
Audio : sounddevice (cross-platform, RAM)
Moteur: KinectMotor.exe (oui/non/blink/hello/think/reset/snap)
Cmds  : oui/non/blink/hello/think/reset/snap/sleep/wake + VOICE:texte

https://github.com/PalpatineRex/Project-Claudius
"""
import subprocess, os, time, threading, random, json, sys, re, base64, glob
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
MOTOR_CMD_FILE   = os.path.join(_DATA_DIR, "motor_cmd.txt")
PRESENCE_FILE    = os.path.join(_DATA_DIR, "presence.txt")
MEMORY_FILE      = os.path.join(_DATA_DIR, "memory.json")
MAX_MEMORIES     = 15  # nb de souvenirs gardes dans le contexte
LOG_MAX_LINES    = 2000
_log_count       = 0

# --- DeepSeek V4 Flash (provider principal, texte) ---
DEEPSEEK_URL      = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_API_KEY  = ""
for _p in [os.path.join(_KINECT_DIR, "deepseek_key.txt"), os.path.join(_DATA_DIR, "deepseek_key.txt")]:
    try:
        _k = open(_p, "r").read().strip().strip('"').strip("'")
        if _k:
            DEEPSEEK_API_KEY = _k
            break
    except Exception:
        pass
if not DEEPSEEK_API_KEY:
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip().strip('"').strip("'")
DEEPSEEK_MODEL    = "deepseek-v4-flash"

# --- Anthropic Haiku (fallback vision uniquement) ---
ANTHROPIC_URL     = "https://api.anthropic.com/v1/messages"
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
    for _f in (SLEEP_FILE, TTS_LOCK_FILE, CMD_FILE, MOTOR_CMD_FILE):
        try:
            if os.path.exists(_f): os.remove(_f)
        except Exception: pass
    # Kill Motor residuel pour liberer le Kinect
    os.system("taskkill /f /im KinectMotor.exe >nul 2>nul")
    time.sleep(1)

# --- SFX : sons synthetiques (numpy + sounddevice) ---

SFX_VOLUME = 0.3  # volume global SFX (0.0-1.0)
SFX_SR     = 22050

def _sfx_sin(freq, duration):
    t = np.linspace(0, duration, int(SFX_SR * duration), endpoint=False)
    return np.sin(2 * np.pi * freq * t)

def _sfx_fade(audio, fade_in=0.01, fade_out=0.01):
    n_in = int(SFX_SR * fade_in)
    n_out = int(SFX_SR * fade_out)
    if n_in > 0 and n_in < len(audio):
        audio[:n_in] *= np.linspace(0, 1, n_in)
    if n_out > 0 and n_out < len(audio):
        audio[-n_out:] *= np.linspace(1, 0, n_out)
    return audio

def _sfx_boot():
    """Boot jingle — 3 notes montantes + accord majeur (~1s)."""
    parts = []
    for freq, dur, vol in [(523,0.15,0.7),(659,0.15,0.8),(784,0.2,0.9)]:
        parts.append(_sfx_fade(_sfx_sin(freq, dur) * vol, 0.005, 0.02))
        parts.append(np.zeros(int(SFX_SR * 0.05)))
    chord = _sfx_sin(523,0.4)*0.4 + _sfx_sin(659,0.4)*0.35 + _sfx_sin(784,0.4)*0.35 + _sfx_sin(1568,0.4)*0.1
    parts.append(_sfx_fade(chord, 0.01, 0.15))
    return np.concatenate(parts) * SFX_VOLUME

def _sfx_presence():
    """Presence chime — ding doux avec harmoniques (~0.4s)."""
    dur = 0.4
    t = np.linspace(0, dur, int(SFX_SR * dur), endpoint=False)
    env = np.exp(-t * 6)
    tone = _sfx_sin(880,dur)*0.5 + _sfx_sin(1760,dur)*0.25 + _sfx_sin(2640,dur)*0.15 + _sfx_sin(1320,dur)*0.1
    return _sfx_fade(tone * env, 0.005, 0.01) * SFX_VOLUME

def _sfx_listen():
    """Listen beep — 2 bips courts montants (~0.25s)."""
    parts = []
    parts.append(_sfx_fade(_sfx_sin(600, 0.08) * 1.0, 0.003, 0.01))
    parts.append(np.zeros(int(SFX_SR * 0.04)))
    parts.append(_sfx_fade(_sfx_sin(900, 0.08) * 1.0, 0.003, 0.01))
    # Petit silence final pour que sd.wait() finisse proprement
    parts.append(np.zeros(int(SFX_SR * 0.05)))
    return np.concatenate(parts) * (SFX_VOLUME * 1.5)  # boost volume listen

def _sfx_wake():
    """Wake chime — sweep ascendant + note finale (~0.6s)."""
    dur_s = 0.3
    t = np.linspace(0, dur_s, int(SFX_SR * dur_s), endpoint=False)
    freq = 400 + 400 * (t / dur_s)
    sweep = np.sin(2 * np.pi * np.cumsum(freq) / SFX_SR) * 0.6 * np.linspace(0.3, 1.0, len(t))
    sweep = _sfx_fade(sweep, 0.01, 0.02)
    note = _sfx_fade(_sfx_sin(784, 0.25) * 0.7, 0.005, 0.1)
    return np.concatenate([sweep, np.zeros(int(SFX_SR * 0.05)), note]) * SFX_VOLUME

# Cache des sons (generes une seule fois)
_sfx_cache = {}

def _play_sfx(name, blocking=False):
    """Joue un SFX par nom. Non-bloquant par defaut, sauf si blocking=True."""
    def _do():
        if _speaking.is_set():
            return  # ne pas jouer par-dessus le TTS
        try:
            if name not in _sfx_cache:
                gen = {"boot": _sfx_boot, "presence": _sfx_presence,
                       "listen": _sfx_listen, "wake": _sfx_wake}.get(name)
                if gen is None: return
                _sfx_cache[name] = gen().astype(np.float32)
            _log(f"SFX: {name} ({len(_sfx_cache[name])/SFX_SR:.2f}s)")
            sd.play(_sfx_cache[name], samplerate=SFX_SR)
            sd.wait()
        except Exception as e:
            _log(f"SFX ERR {name}: {e}")
    if blocking:
        _do()
    else:
        threading.Thread(target=_do, daemon=True).start()

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

_motor_daemon_mode = False  # set True when daemon is detected

def _run(cmd):
    with _motor_lock:
        if _motor_daemon_mode:
            # Daemon mode: write command to motor_cmd.txt
            try:
                with open(MOTOR_CMD_FILE, "w") as f:
                    f.write(cmd)
                _log("CMD>" + cmd)
            except Exception as e:
                _log("ERR _run cmd write: " + str(e))
        else:
            # Legacy: launch KinectMotor.exe directly
            try:
                subprocess.call([MOTOR_EXE, cmd], creationflags=subprocess.CREATE_NO_WINDOW)
                _log("OK:" + cmd)
            except Exception as e:
                _log("ERR _run " + cmd + ": " + str(e))

def _run_snap():
    _log("snap: debut")
    with _motor_lock:
        if _motor_daemon_mode:
            # Daemon mode: write snap command, wait for result in stdout of daemon
            # The daemon handles snap internally — we just trigger it
            try:
                with open(MOTOR_CMD_FILE, "w") as f:
                    f.write("snap")
                _log("snap: commande envoyee au daemon")
                # Wait a bit for the daemon to process (snap takes ~3-5s with warm-up)
                time.sleep(5)
                return "OK:snap_via_daemon"
            except Exception as e:
                _log("ERR snap cmd: " + str(e))
                return None
        # Legacy mode
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
            # Attendre que Voice ait fini de calibrer avant le jingle
            time.sleep(5)
            _play_sfx("boot")  # jingle demarrage

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

# --- Vision : snap recent pour appel multimodal ---

_SNAP_MAX_AGE = 10  # secondes max pour considerer un snap comme "frais"

def _find_recent_snap():
    """Cherche le snap Kinect le plus recent (< _SNAP_MAX_AGE secondes).
    Retourne le chemin absolu ou None."""
    pattern = os.path.join(_KINECT_DIR, "KinectSnap-*.png")
    snaps = glob.glob(pattern)
    if not snaps:
        return None
    # Le plus recent en premier
    snaps.sort(key=os.path.getmtime, reverse=True)
    newest = snaps[0]
    age = time.time() - os.path.getmtime(newest)
    if age <= _SNAP_MAX_AGE:
        _log(f"VISION: snap frais trouve ({os.path.basename(newest)}, {age:.1f}s)")
        return newest
    return None

def _encode_image_b64(path):
    """Encode une image en base64 pour l'API Anthropic."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

# --- Mots-cles vision (backup cote Bridge) ---
_VISION_KEYWORDS = [
    "regarde", "tu vois", "vois-tu", "c'est quoi", "qu'est-ce que tu vois",
    "montre", "observe", "qu'est-ce qu'il y a", "devant toi",
    "camera", "snap",
]

def _is_vision_request(text):
    """Detecte si le texte est une demande vision."""
    t = text.lower()
    return any(kw in t for kw in _VISION_KEYWORDS)

# --- Memoire longue ---

def _load_memories():
    """Charge les souvenirs depuis memory.json."""
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                memories = json.load(f)
            return memories[-MAX_MEMORIES:]  # garder les plus recents
    except Exception as e:
        _log(f"ERR load memories: {e}")
    return []

def _save_memory(summary, exchange_count):
    """Ajoute un souvenir dans memory.json."""
    try:
        memories = _load_memories() if os.path.exists(MEMORY_FILE) else []
        entry = {
            "date": time.strftime("%Y-%m-%d %H:%M"),
            "summary": summary,
            "exchanges": exchange_count
        }
        memories.append(entry)
        # Garder max 50 en fichier (on n'injecte que les 15 derniers)
        if len(memories) > 50:
            memories = memories[-50:]
        tmp = MEMORY_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(memories, f, ensure_ascii=False, indent=2)
        if os.path.exists(MEMORY_FILE):
            os.remove(MEMORY_FILE)
        os.rename(tmp, MEMORY_FILE)
        _log(f"MEMORY: souvenir sauve ({exchange_count} echanges)")
    except Exception as e:
        _log(f"ERR save memory: {e}")

def _summarize_session(history):
    """Demande a Haiku de resumer la conversation en 1-2 phrases."""
    if len(history) < 2:
        return None
    try:
        # Construire un historique texte simple (sans images)
        text_history = []
        for msg in history:
            role = "David" if msg["role"] == "user" else "Claudius"
            content = msg["content"]
            if isinstance(content, list):
                # Message multimodal — extraire le texte
                content = " ".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
            text_history.append(f"{role}: {content}")
        convo = "\n".join(text_history)
        payload = json.dumps({
            "model": ANTHROPIC_MODEL,
            "max_tokens": 80,
            "system": "Resume cette conversation en 1-2 phrases courtes en francais. Juste les faits saillants, pas de formule.",
            "messages": [{"role": "user", "content": convo}]
        }).encode("utf-8")
        req = urllib.request.Request(ANTHROPIC_URL, data=payload, method="POST", headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            summary = json.loads(resp.read().decode())["content"][0]["text"].strip()
        _log(f"MEMORY: resume genere: {summary[:80]}")
        return summary
    except Exception as e:
        _log(f"ERR summarize: {e}")
        return None

def _format_memories_for_prompt():
    """Formate les souvenirs pour injection dans le system prompt."""
    memories = _load_memories()
    if not memories:
        return ""
    lines = ["\nSOUVENIRS DES SESSIONS PRECEDENTES (du plus ancien au plus recent):"]
    for m in memories:
        lines.append(f"- [{m['date']}] {m['summary']}")
    lines.append("Utilise ces souvenirs naturellement si pertinent, sans les lister.")
    return "\n".join(lines)

# --- Ch8 : Commandes utilitaires (heure, meteo, timer, rappel) ---

import locale
try:
    locale.setlocale(locale.LC_TIME, "fr_FR.UTF-8")
except Exception:
    try: locale.setlocale(locale.LC_TIME, "French_France.1252")
    except Exception: pass

# Coordonnees Lavelanet (Occitanie) pour Open-Meteo
_METEO_LAT = 42.94
_METEO_LON = 1.85
_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast?"
    f"latitude={_METEO_LAT}&longitude={_METEO_LON}"
    "&current=temperature_2m,weathercode,windspeed_10m,relative_humidity_2m"
    "&timezone=Europe/Paris"
)

# WMO weather codes -> description FR
_WMO_CODES = {
    0: "ciel degage", 1: "peu nuageux", 2: "partiellement nuageux", 3: "couvert",
    45: "brouillard", 48: "brouillard givrant",
    51: "bruine legere", 53: "bruine", 55: "bruine forte",
    61: "pluie legere", 63: "pluie moderee", 65: "forte pluie",
    71: "neige legere", 73: "neige moderee", 75: "forte neige",
    77: "grains de neige", 80: "averses legeres", 81: "averses", 82: "fortes averses",
    85: "averses de neige legeres", 86: "fortes averses de neige",
    95: "orage", 96: "orage avec grele legere", 99: "orage avec forte grele",
}

# Timers/rappels actifs
_active_timers = []
_timer_lock = threading.Lock()
_timer_id_counter = 0

def _sfx_alarm():
    """Son alarme timer — 3 bips insistants (~0.8s)."""
    parts = []
    for _ in range(3):
        parts.append(_sfx_fade(_sfx_sin(880, 0.12) * 1.0, 0.005, 0.01))
        parts.append(np.zeros(int(SFX_SR * 0.08)))
    parts.append(np.zeros(int(SFX_SR * 0.05)))
    return np.concatenate(parts) * (SFX_VOLUME * 2.0)

def _play_alarm():
    """Joue le SFX alarme (bloquant)."""
    try:
        if "alarm" not in _sfx_cache:
            _sfx_cache["alarm"] = _sfx_alarm().astype(np.float32)
        _log(f"SFX: alarm ({len(_sfx_cache['alarm'])/SFX_SR:.2f}s)")
        sd.play(_sfx_cache["alarm"], samplerate=SFX_SR)
        sd.wait()
    except Exception as e:
        _log(f"SFX ERR alarm: {e}")

def _timer_thread(seconds, message=None):
    """Thread qui attend N secondes puis sonne + TTS. Annulable via cancel_event."""
    global _timer_id_counter
    cancel_evt = threading.Event()
    with _timer_lock:
        _timer_id_counter += 1
        timer_id = _timer_id_counter
    label = message or f"timer de {_format_duration(seconds)}"
    entry = {"id": timer_id, "label": label, "end": time.time() + seconds, "cancel": cancel_evt}
    with _timer_lock:
        _active_timers.append(entry)
    _log(f"TIMER: demarre #{timer_id} — {label} ({seconds}s)")
    # Attente annulable (poll toutes les 0.5s)
    cancelled = cancel_evt.wait(timeout=seconds)
    # Retirer des actifs
    with _timer_lock:
        _active_timers[:] = [t for t in _active_timers if t["id"] != timer_id]
    if cancelled:
        _log(f"TIMER: #{timer_id} annule — {label}")
        return
    _log(f"TIMER: #{timer_id} termine — {label}")
    _priority_evt.set()
    try:
        _play_alarm()
        if message:
            _tts_wait(f"David ! Rappel : {message}")
        else:
            _tts_wait(f"David ! Le timer de {_format_duration(seconds)} est termine !")
    finally:
        _priority_evt.clear()

def _format_duration(seconds):
    """Formate une duree en texte FR naturel."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    parts = []
    if h > 0: parts.append(f"{h} heure{'s' if h > 1 else ''}")
    if m > 0: parts.append(f"{m} minute{'s' if m > 1 else ''}")
    if s > 0 and h == 0: parts.append(f"{s} seconde{'s' if s > 1 else ''}")
    return " et ".join(parts) if parts else "0 secondes"

def _parse_duration(text):
    """Extrait une duree en secondes depuis le texte. Retourne None si pas de duree."""
    t = text.lower()
    total = 0
    found = False
    # Heures
    m = re.search(r'(\d+)\s*(?:heure|heures|h)\b', t)
    if m: total += int(m.group(1)) * 3600; found = True
    # Minutes
    m = re.search(r'(\d+)\s*(?:minute|minutes|min)\b', t)
    if m: total += int(m.group(1)) * 60; found = True
    # Secondes
    m = re.search(r'(\d+)\s*(?:seconde|secondes|sec)\b', t)
    if m: total += int(m.group(1)); found = True
    # Cas simple "5 minutes" sans mot explicite mais avec un nombre seul
    if not found:
        m = re.search(r'(\d+)', t)
        if m:
            n = int(m.group(1))
            # Heuristique : si le nombre est < 180, c'est probablement des minutes
            if n > 0:
                total = n * 60
                found = True
    return total if found and total > 0 else None

def _fetch_meteo():
    """Appelle Open-Meteo et retourne une phrase FR. Non bloquant pour le main thread."""
    try:
        req = urllib.request.Request(_METEO_URL, headers={"User-Agent": "Claudius/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        cur = data["current"]
        temp = cur["temperature_2m"]
        code = cur.get("weathercode", -1)
        wind = cur.get("windspeed_10m", 0)
        humidity = cur.get("relative_humidity_2m", 0)
        desc = _WMO_CODES.get(code, "conditions inconnues")
        # Construire la phrase
        parts = [f"Il fait {temp:.0f} degres"]
        parts.append(f"avec {desc}")
        if wind > 20:
            parts.append(f"et du vent a {wind:.0f} kilometres heure")
        elif wind > 5:
            parts.append(f"avec un vent leger a {wind:.0f} kilometres heure")
        return ". ".join([", ".join(parts)])
    except Exception as e:
        _log(f"ERR meteo: {e}")
        return "Desole, je n'arrive pas a recuperer la meteo."

# --- Detection intent utilitaire ---

_INTENT_HEURE = re.compile(
    r'(?:quelle?\s+heure|heure\s+(?:est|qu)|l\'heure|il\s+est\s+quelle|donne.*heure'
    r'|dis.*heure|heure\s+il\s+est|est.il)', re.IGNORECASE
)
_INTENT_DATE = re.compile(
    r'(?:quel\s+jour|quelle\s+date|on\s+est\s+(?:le\s+)?(?:quel|combien)|date\s+(?:d\')?aujourd'
    r'|jour\s+(?:on\s+est|sommes)|quel.*date|dis.*jour|le\s+combien)', re.IGNORECASE
)
_INTENT_METEO = re.compile(
    r'(?:meteo|m[eé]t[eé]o|quel\s+temps|temps\s+(?:fait|qu)|il\s+fait\s+(?:combien|chaud|froid|beau)'
    r'|temperature|dehors|pleut|pluie|neige|ensoleill)', re.IGNORECASE
)
_INTENT_TIMER = re.compile(
    r'(?:met[s]?[\s-]+(?:(?:moi\s+)?(?:un\s+)?)?(?:timer|minuteur|chrono)|lance[\s-]+(?:(?:moi\s+)?(?:un\s+)?)?(?:timer|minuteur)'
    r'|timer\s+(?:de\s+)?\d|minuteur\s+(?:de\s+)?\d|compte[\s-]+(?:a\s+)?rebours'
    r'|(?:un\s+)?timer\s+de\s+\d|(?:un\s+)?minuteur\s+de\s+\d)', re.IGNORECASE
)
_INTENT_RAPPEL = re.compile(
    r'(?:rappel(?:le)?[\s-]?moi|n\'oublie\s+pas|pense\s+[aà]\s+me\s+rappeler|fais[\s-]?moi\s+penser)',
    re.IGNORECASE
)
_INTENT_TIMERS_STATUS = re.compile(
    r'(?:combien\s+(?:de\s+)?(?:timer|minuteur|temps)|timer[s]?\s+(?:en\s+cours|actif)|il\s+reste\s+combien'
    r'|temps\s+restant|reste.*timer|reste.*minuteur|timer.*reste|oubli.*timer|timer.*oubli)', re.IGNORECASE
)
_INTENT_CANCEL_TIMER = re.compile(
    r'(?:annul(?:e|er?)\s+(?:le\s+)?(?:timer|minuteur|rappel)|stop(?:pe)?\s+(?:le\s+)?(?:timer|minuteur)'
    r'|coupe\s+(?:le\s+)?(?:timer|minuteur)|arr[eê]te\s+(?:le\s+)?(?:timer|minuteur))',
    re.IGNORECASE
)

def _extract_rappel_message(text):
    """Extrait le message du rappel. Ex: 'rappelle moi de sortir le linge dans 10 min' -> 'sortir le linge'"""
    t = text.lower()
    # Pattern "rappelle moi de/que/d' ... dans/en X minutes"
    m = re.search(r'(?:rappel(?:le)?[\s-]?moi|fais[\s-]?moi\s+penser)\s+(?:de\s+|que\s+|d\'|qu\')?(.+?)(?:\s+dans\s+|\s+en\s+|\s+d\'ici\s+)', t)
    if m:
        return m.group(1).strip()
    # Pattern "dans X minutes rappelle moi de ..."
    m = re.search(r'(?:rappel(?:le)?[\s-]?moi|fais[\s-]?moi\s+penser)\s+(?:de\s+|que\s+|d\'|qu\')?(.+)', t)
    if m:
        msg = m.group(1).strip()
        # Retirer la duree a la fin si presente
        msg = re.sub(r'\s+dans\s+\d+.*$', '', msg)
        msg = re.sub(r'\s+en\s+\d+.*$', '', msg)
        return msg.strip() if msg.strip() else None
    return None

def _check_utility_command(text):
    """Verifie si le texte est une commande utilitaire.
    Retourne la reponse TTS (str) si oui, None sinon."""
    t = text.lower().strip()

    # --- Heure ---
    if _INTENT_HEURE.search(t):
        now = time.strftime("%H heures %M")
        _log(f"UTIL: heure -> {now}")
        return f"Il est {now}."

    # --- Date ---
    if _INTENT_DATE.search(t):
        try:
            jour = time.strftime("%A %d %B %Y")
        except Exception:
            jour = time.strftime("%d/%m/%Y")
        _log(f"UTIL: date -> {jour}")
        return f"On est le {jour}."

    # --- Meteo ---
    if _INTENT_METEO.search(t):
        _log("UTIL: meteo demandee")
        return _fetch_meteo()

    # --- Annuler timer ---
    if _INTENT_CANCEL_TIMER.search(t):
        with _timer_lock:
            count = len(_active_timers)
            for t_info in _active_timers:
                t_info["cancel"].set()  # signal le thread pour qu'il s'arrete
            _active_timers.clear()
        if count > 0:
            return f"J'ai annule {count} timer{'s' if count > 1 else ''}."
        else:
            return "Il n'y a aucun timer en cours."

    # --- Status timers ---
    if _INTENT_TIMERS_STATUS.search(t):
        with _timer_lock:
            if not _active_timers:
                return "Aucun timer en cours."
            parts = []
            now = time.time()
            for t_info in _active_timers:
                remaining = max(0, t_info["end"] - now)
                parts.append(f"{t_info['label']}, encore {_format_duration(int(remaining))}")
            return "Timers en cours : " + ". ".join(parts) + "."

    # --- Rappel (avant timer car rappel inclut une duree) ---
    if _INTENT_RAPPEL.search(t):
        duration = _parse_duration(t)
        message = _extract_rappel_message(text)  # text original (pas lowercase)
        if duration and message:
            threading.Thread(target=_timer_thread, args=(duration, message), daemon=True).start()
            return f"C'est note, je te rappelle de {message} dans {_format_duration(duration)}."
        elif duration:
            threading.Thread(target=_timer_thread, args=(duration, "rappel"), daemon=True).start()
            return f"OK, rappel dans {_format_duration(duration)}."
        else:
            return None  # pas de duree detectee -> laisser Haiku gerer

    # --- Timer ---
    if _INTENT_TIMER.search(t):
        duration = _parse_duration(t)
        if duration:
            threading.Thread(target=_timer_thread, args=(duration,), daemon=True).start()
            return f"Timer de {_format_duration(duration)}, c'est parti !"
        else:
            return None  # pas de duree -> Haiku

    return None  # pas une commande utilitaire

# --- LLM Claude Haiku via API ---

_SYSTEM_FALLBACK = (
    "Tu es Claudius, une tete animatronique Kinect Xbox 360 sur le bureau de David. "
    "Reponds en francais, 1-2 phrases max, naturellement. Pas de markdown."
)

_cached_system_prompt = None
_cached_system_mtime = 0

def _load_system_prompt():
    """Charge le contexte depuis claudius_context.txt + souvenirs memoire."""
    global _cached_system_prompt, _cached_system_mtime
    for path in [CONTEXT_FILE, os.path.join(_KINECT_DIR, "claudius_context.txt")]:
        try:
            mt = os.path.getmtime(path)
            # Recharger aussi si memory.json a change
            mem_mt = 0
            try: mem_mt = os.path.getmtime(MEMORY_FILE)
            except: pass
            cache_key = (mt, mem_mt)
            if _cached_system_prompt and cache_key == _cached_system_mtime:
                return _cached_system_prompt
            with open(path, "r", encoding="utf-8") as f:
                ctx = f.read().strip()
            if ctx:
                # Ajouter les souvenirs
                memories_text = _format_memories_for_prompt()
                if memories_text:
                    ctx += "\n" + memories_text
                _cached_system_prompt = ctx
                _cached_system_mtime = cache_key
                return ctx
        except Exception:
            continue
    return _SYSTEM_FALLBACK

_conversation_history = []
_history_lock = threading.Lock()
MAX_HISTORY = 6  # nb d'echanges (user+assistant) gardes en memoire

def _ask_claude(text, image_path=None):
    global _conversation_history
    use_vision = image_path is not None
    # Construire le contenu du message user
    if use_vision:
        # Vision = Haiku (DeepSeek V4 Flash ne supporte pas les images)
        try:
            img_b64 = _encode_image_b64(image_path)
            user_content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_b64,
                    }
                },
                {"type": "text", "text": text}
            ]
            _log(f"VISION: image attachee ({os.path.basename(image_path)})")
        except Exception as e:
            _log(f"ERR vision encode: {e}")
            user_content = text
            use_vision = False
    else:
        user_content = text
    with _history_lock:
        _conversation_history.append({"role": "user", "content": user_content})
        messages = list(_conversation_history)
    # System prompt enrichi si vision
    system = _load_system_prompt()
    if use_vision:
        system += (
            "\n\n[VISION] Tu vois une image de ta camera Kinect. "
            "Ne decris PAS ce que tu vois sauf si David te le demande explicitement. "
            "Utilise l'image pour COMPRENDRE le contexte et repondre naturellement. "
            "Par exemple si David te montre un objet, parle de l'objet, pas de la piece."
        )
    try:
        if use_vision:
            # --- Haiku (vision multimodale) ---
            payload = json.dumps({
                "model": ANTHROPIC_MODEL,
                "max_tokens": 150,
                "system": system,
                "messages": messages
            }).encode("utf-8")
            req = urllib.request.Request(ANTHROPIC_URL, data=payload, method="POST", headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01"
            })
            with urllib.request.urlopen(req, timeout=20) as resp:
                reply = json.loads(resp.read().decode())["content"][0]["text"].strip()
            _log("LLM: Haiku (vision)")
        else:
            # --- DeepSeek V4 Flash (texte) ---
            # Format OpenAI ChatCompletions (system = premier message role:system)
            ds_messages = [{"role": "system", "content": system}]
            for m in messages:
                c = m["content"]
                # Si contenu multimodal (liste de blocs), extraire le texte
                if isinstance(c, list):
                    c = " ".join(b.get("text", "") for b in c if b.get("type") == "text").strip()
                    if not c:
                        continue
                ds_messages.append({"role": m["role"], "content": c})
            payload = json.dumps({
                "model": DEEPSEEK_MODEL,
                "max_tokens": 250,
                "messages": ds_messages,
                "temperature": 0.7
            }).encode("utf-8")
            req = urllib.request.Request(DEEPSEEK_URL, data=payload, method="POST", headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                reply = data["choices"][0]["message"]["content"].strip()
                # DeepSeek thinking mode : retirer les balises <think>...</think>
                reply = re.sub(r'<think>.*?</think>', '', reply, flags=re.DOTALL).strip()
            _log("LLM: DeepSeek V4 Flash")
        with _history_lock:
            _conversation_history.append({"role": "assistant", "content": reply})
            # Garder seulement les MAX_HISTORY derniers echanges (paires user/assistant)
            if len(_conversation_history) > MAX_HISTORY * 2:
                _conversation_history = _conversation_history[-(MAX_HISTORY * 2):]
        return reply
    except Exception as e:
        _log("ERR llm: " + str(e))
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
    if not _speaking.is_set():
        _play_sfx("listen", blocking=True)  # bip seulement si pas en train de parler
    # --- Ch8 : commandes utilitaires (heure, meteo, timer, rappel) ---
    util_reply = _check_utility_command(text)
    if util_reply:
        _log("UTIL reply: " + util_reply[:80])
        try:
            ts = time.strftime("%H:%M:%S")
            with open(TRANSCRIPT_FILE, "a", encoding="utf-8") as _tf:
                _tf.write(f"[{ts}] Claudius: {util_reply}\n")
        except Exception:
            pass
        gesture = _gesture_for(util_reply)
        if gesture:
            threading.Thread(target=_run, args=(gesture,), daemon=True).start()
        _tts_wait(util_reply)
        return
    # --- Vision : si demande vision, trigger snap et attendre ---
    snap_path = None
    if _is_vision_request(text):
        _log("VISION: demande detectee, trigger snap")
        _run("snap")
        # Attendre que le snap soit pris (daemon mode ~2-3s)
        for _ in range(8):  # max 4s d'attente
            time.sleep(0.5)
            snap_path = _find_recent_snap()
            if snap_path:
                break
        if not snap_path:
            _log("VISION: pas de snap disponible, appel texte seul")
    result_box = [None]
    _snap = snap_path  # capture pour le thread
    def _query():
        try:
            result_box[0] = _ask_claude(text, image_path=_snap)
        except Exception as e:
            _log("ERR _query: " + str(e))
    t = threading.Thread(target=_query, daemon=True)
    t.start()
    # Think en parallele (non bloquant pour le thread principal)
    threading.Thread(target=_run, args=("think",), daemon=True).start()
    t.join(timeout=25 if snap_path else 20)
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
    _play_sfx("wake")  # chime reveil
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

# --- Presence watcher ---

_PRESENCE_GREETINGS_FIRST = {
    "morning": ["Bonjour David !", "Bonjour !"],
    "afternoon": ["Bonjour David !", "Bon apres-midi !"],
    "evening": ["Bonsoir David !", "Bonsoir !"],
}
_PRESENCE_GREETINGS_RETURN = [
    "Re !",
    "Bon retour !",
    "Ah, te revoila !",
    "De retour sur ta chaise ?",
]
_PRESENCE_CHECK_INTERVAL = 2  # seconds between file checks
_PRESENCE_GREETING_COOLDOWN = 3600  # 1h entre greetings (pas de spam)
_PRESENCE_MIN_ABSENCE = 300  # 5 min d'absence minimum pour re-saluer
_PRESENCE_FIRST_DONE = False  # premier greeting de la session = bonjour/bonsoir

def _read_presence():
    """Lit presence.txt -> (state, timestamp_str, pixel_count) ou None."""
    try:
        if not os.path.exists(PRESENCE_FILE):
            return None
        with open(PRESENCE_FILE, "r") as f:
            lines = f.read().strip().split("\n")
        if len(lines) < 2:
            return None
        return lines[0].strip(), lines[1].strip(), int(lines[2]) if len(lines) > 2 else 0
    except Exception:
        return None

def _presence_watcher():
    """Thread qui surveille presence.txt et declenche un greeting quand quelqu'un arrive."""
    global _PRESENCE_FIRST_DONE
    last_greeting_time = 0.0
    was_present = False
    absence_start = 0.0  # quand l'absence a commence
    _memory_saved_this_session = False  # evite double sauvegarde
    _log("PRESENCE: watcher actif")

    # Attendre que Piper soit pret avant de saluer
    _piper_ready.wait(timeout=30)
    time.sleep(2)  # laisser le systeme se stabiliser

    while True:
        time.sleep(_PRESENCE_CHECK_INTERVAL)

        # Don't greet if sleeping or speaking
        if _sleeping.is_set() or _speaking.is_set():
            continue

        state = _read_presence()
        if state is None:
            was_present = False
            continue

        present = (state[0] == "PRESENT")

        # Track absence duration
        if not present and was_present:
            absence_start = time.time()
            # --- Memoire longue : sauvegarder quand David part ---
            if not _memory_saved_this_session:
                with _history_lock:
                    history_copy = list(_conversation_history)
                if len(history_copy) >= 4:  # au moins 2 echanges (2 user + 2 assistant)
                    _memory_saved_this_session = True
                    def _do_save():
                        summary = _summarize_session(history_copy)
                        if summary:
                            _save_memory(summary, len(history_copy) // 2)
                    threading.Thread(target=_do_save, daemon=True).start()
        
        if present and not was_present:
            now = time.time()
            absence_duration = now - absence_start if absence_start > 0 else 9999
            cooldown_ok = (now - last_greeting_time >= _PRESENCE_GREETING_COOLDOWN)
            absence_ok = (absence_duration >= _PRESENCE_MIN_ABSENCE)

            if cooldown_ok and absence_ok:
                _log(f"PRESENCE: detection! ({state[2]} pixels, absent {absence_duration:.0f}s)")
                last_greeting_time = now
                _memory_saved_this_session = False  # reset pour prochaine session

                # Premier greeting = bonjour/bonsoir, ensuite = retour
                if not _PRESENCE_FIRST_DONE:
                    hour = int(time.strftime("%H"))
                    if hour < 12:
                        greeting = random.choice(_PRESENCE_GREETINGS_FIRST["morning"])
                    elif hour < 18:
                        greeting = random.choice(_PRESENCE_GREETINGS_FIRST["afternoon"])
                    else:
                        greeting = random.choice(_PRESENCE_GREETINGS_FIRST["evening"])
                    _PRESENCE_FIRST_DONE = True
                else:
                    greeting = random.choice(_PRESENCE_GREETINGS_RETURN)

                _priority_evt.set()
                try:
                    _play_sfx("presence", blocking=True)  # chime avant greeting
                    threading.Thread(target=_run, args=("hello",), daemon=True).start()
                    _tts_wait(greeting)
                    try:
                        with open(TRANSCRIPT_FILE, "a", encoding="utf-8") as _tf:
                            _tf.write(f"[{time.strftime('%H:%M:%S')}] Claudius: {greeting}\n")
                    except Exception:
                        pass
                finally:
                    _priority_evt.clear()
            elif not cooldown_ok:
                _log(f"PRESENCE: cooldown ({_PRESENCE_GREETING_COOLDOWN}s)")
            elif not absence_ok:
                _log(f"PRESENCE: absence trop courte ({absence_duration:.0f}s < {_PRESENCE_MIN_ABSENCE}s)")

        was_present = present

# --- Motor daemon launcher ---

_motor_daemon_proc = None  # ref au process daemon

def _launch_motor_daemon():
    """Lance KinectMotor.exe en mode daemon (presence) si disponible."""
    global _motor_daemon_mode, _motor_daemon_proc
    if not os.path.exists(MOTOR_EXE):
        _log("MOTOR: exe introuvable — mode legacy")
        return False
    # Kill tout Motor residuel avant de lancer
    try:
        import ctypes
        os.system("taskkill /f /im KinectMotor.exe >nul 2>nul")
        time.sleep(1)
    except Exception:
        pass
    try:
        proc = subprocess.Popen(
            [MOTOR_EXE, "presence", _KINECT_DIR],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            cwd=_KINECT_DIR
        )
        time.sleep(3)  # let it start
        if proc.poll() is None:
            _motor_daemon_mode = True
            _motor_daemon_proc = proc
            _log(f"MOTOR: daemon lance (PID {proc.pid}) — presence + gestes via motor_cmd.txt")
            return True
        else:
            _log("MOTOR: daemon exit rapide — mode legacy")
            return False
    except Exception as e:
        _log(f"MOTOR: ERR lancement daemon: {e} — mode legacy")
        return False

def _watchdog_motor():
    """Thread watchdog Motor — relance le daemon s'il meurt."""
    global _motor_daemon_mode, _motor_daemon_proc
    time.sleep(10)  # laisser le daemon demarrer
    _log("WATCHDOG MOTOR: actif")
    restart_count = 0
    max_restarts = 10
    while True:
        time.sleep(15)
        if not _motor_daemon_mode:
            continue  # legacy mode, pas de watchdog
        if _motor_daemon_proc is None:
            continue
        if _motor_daemon_proc.poll() is not None:
            # Daemon mort
            _log(f"WATCHDOG MOTOR: daemon mort (exit code {_motor_daemon_proc.returncode})")
            if restart_count >= max_restarts:
                _log("WATCHDOG MOTOR: trop de relances — abandon")
                _motor_daemon_mode = False
                continue
            time.sleep(3)
            if _launch_motor_daemon():
                restart_count += 1
                _log(f"WATCHDOG MOTOR: relance #{restart_count}/{max_restarts}")
            else:
                _motor_daemon_mode = False
                _log("WATCHDOG MOTOR: echec relance — mode legacy")

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
    if not DEEPSEEK_API_KEY:
        _log("ERREUR: cle DeepSeek absente (deepseek_key.txt)")
    if not ANTHROPIC_API_KEY:
        _log("ATTENTION: cle Anthropic absente — vision desactivee")
    _log("=== KinectBridge demarrage (DeepSeek V4 Flash + Haiku vision) ===")
    _launch_motor_daemon()
    threading.Thread(target=watch_cmd, daemon=True).start()
    threading.Thread(target=_auto_blink, daemon=True).start()
    threading.Thread(target=_load_piper_bg, daemon=True).start()
    threading.Thread(target=_watchdog_voice, daemon=True).start()
    threading.Thread(target=_watchdog_motor, daemon=True).start()
    threading.Thread(target=_presence_watcher, daemon=True).start()
    _log("KinectBridge pret. (watchdog Voice + presence actifs)")
    while True:
        time.sleep(60)
