"""
claudius_sfx.py — Sons synthétiques pour Claudius
SFX générés en numpy + sounddevice, pré-calculés au boot.
Volume dynamique via claudius_settings.json.
"""
import numpy as np
import sounddevice as sd
import os, json

SFX_SR = 22050
_SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claudius_settings.json")

def _get_volume():
    try:
        with open(_SETTINGS_FILE, "r") as f:
            return float(json.load(f).get("sfx_volume", 0.3))
    except Exception:
        return 0.3

# Cache global (pré-rempli au boot)
_sfx_cache = {}

# --- Générateurs internes ---

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

def _gen_boot():
    """Boot jingle — 3 notes montantes + accord majeur (~1s)."""
    parts = []
    for freq, dur, vol in [(523, 0.15, 0.7), (659, 0.15, 0.8), (784, 0.2, 0.9)]:
        parts.append(_sfx_fade(_sfx_sin(freq, dur) * vol, 0.005, 0.02))
        parts.append(np.zeros(int(SFX_SR * 0.05)))
    chord = (_sfx_sin(523, 0.4) * 0.4 + _sfx_sin(659, 0.4) * 0.35 +
             _sfx_sin(784, 0.4) * 0.35 + _sfx_sin(1568, 0.4) * 0.1)
    parts.append(_sfx_fade(chord, 0.01, 0.15))
    return np.concatenate(parts) * 0.3

def _gen_presence():
    """Presence chime — ding doux avec harmoniques (~0.4s)."""
    dur = 0.4
    env = np.exp(-np.linspace(0, dur * 6, int(SFX_SR * dur)))
    tone = (_sfx_sin(880, dur) * 0.5 + _sfx_sin(1760, dur) * 0.25 +
            _sfx_sin(2640, dur) * 0.15 + _sfx_sin(1320, dur) * 0.1)
    return _sfx_fade(tone * env, 0.005, 0.01) * 0.3

def _gen_listen():
    """Listen beep — 2 bips courts montants (~0.25s)."""
    parts = [
        _sfx_fade(_sfx_sin(600, 0.08) * 1.0, 0.003, 0.010),
        np.zeros(int(SFX_SR * 0.04)),
        _sfx_fade(_sfx_sin(900, 0.08) * 1.0, 0.003, 0.010),
        np.zeros(int(SFX_SR * 0.05)),
    ]
    return np.concatenate(parts) * 0.45

def _gen_wake():
    """Wake chime — sweep ascendant + note finale (~0.6s)."""
    dur_s = 0.3
    t = np.linspace(0, dur_s, int(SFX_SR * dur_s), endpoint=False)
    freq = 400 + 400 * (t / dur_s)
    sweep = np.sin(2 * np.pi * np.cumsum(freq) / SFX_SR)
    sweep = sweep * 0.6 * np.linspace(0.3, 1.0, len(t))
    sweep = _sfx_fade(sweep, 0.01, 0.02)
    note = _sfx_fade(_sfx_sin(784, 0.25) * 0.7, 0.005, 0.1)
    return np.concatenate([sweep, np.zeros(int(SFX_SR * 0.05)), note]) * 0.3

def _gen_alarm():
    """Son alarme timer — 3 bips insistants (~0.8s)."""
    parts = []
    for _ in range(3):
        parts.append(_sfx_fade(_sfx_sin(880, 0.12) * 1.0, 0.005, 0.01))
        parts.append(np.zeros(int(SFX_SR * 0.08)))
    parts.append(np.zeros(int(SFX_SR * 0.05)))
    return np.concatenate(parts) * 0.6

# --- API publique ---

def preload_all():
    """Pré-génère tous les SFX en RAM au boot."""
    generators = {
        "boot": _gen_boot,
        "presence": _gen_presence,
        "listen": _gen_listen,
        "wake": _gen_wake,
        "alarm": _gen_alarm,
    }
    for name, gen in generators.items():
        _sfx_cache[name] = gen().astype(np.float32)

def play(name, blocking=False):
    """Joue un SFX. Volume lu dynamiquement depuis settings."""
    import threading
    def _do():
        try:
            audio = _sfx_cache.get(name)
            if audio is None:
                return
            vol = _get_volume()
            sd.play(audio * vol, samplerate=SFX_SR)
            sd.wait()
        except Exception:
            pass
    if blocking:
        _do()
    else:
        threading.Thread(target=_do, daemon=True).start()
