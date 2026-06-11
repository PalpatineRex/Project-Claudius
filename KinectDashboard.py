"""
KinectDashboard.py v4 — Dashboard temps reel Project Claudius
http://localhost:5005 — Lance en parallele de KinectBridge.
v4 (2026-06-11) : fenetre native pywebview FRAMELESS (plus de barre de titre),
themes + moteur d'effets herites du dashboard Odysseus (dashboard-fx.js),
HTML externe (claudius_dash.html, lu au runtime — itération sans recompil),
selecteur de micro PAR NOM, statut moteur honnete (motor_status.txt).
Features: auto-restart bridge si mort, commandes vocales, logs, transcript.
"""
from flask import Flask, request, jsonify, send_file
import os, sys, time, json, subprocess, threading

_SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
_DATA_DIR = os.environ.get("CLAUDIUS_DATA_DIR", _SCRIPT_DIR)
TRANSCRIPT_FILE = os.path.join(_DATA_DIR, "transcript.txt")
LOG_FILE = os.path.join(_DATA_DIR, "kinect.log")
CMD_FILE = os.path.join(_DATA_DIR, "cmd.txt")
MEMORY_FILE = os.path.join(_DATA_DIR, "memory.json")
PRESENCE_FILE = os.path.join(_DATA_DIR, "presence.txt")
BRIDGE_PID_FILE = os.path.join(_DATA_DIR, "bridge.pid")
VOICE_PID_FILE = os.path.join(_DATA_DIR, "voice.pid")
VOICE_HEARTBEAT = os.path.join(_DATA_DIR, "voice_heartbeat.txt")
MOTOR_STATUS_FILE = os.path.join(_DATA_DIR, "motor_status.txt")
BRIDGE_SCRIPT = os.path.join(_SCRIPT_DIR, "KinectBridge.py")
SETTINGS_FILE = os.path.join(_DATA_DIR, "claudius_settings.json")
STOP_FLAG = os.path.join(_DATA_DIR, "claudius_stop.flag")
WINDOW_FILE = os.path.join(_DATA_DIR, "claudius_window.json")
HTML_FILE = os.path.join(_SCRIPT_DIR, "claudius_dash.html")
FX_FILE = os.path.join(_SCRIPT_DIR, "dashboard-fx.js")

_DEFAULT_SETTINGS = {
    "sfx_volume": 0.3, "presence_enabled": True, "mic_threshold": 500,
    "theme": "dark", "max_tokens": 500, "llm_timeout": 25, "tts_speed": 1.0,
    "history_size": 6, "voice_provider": "deepseek", "voice_model": "deepseek-v4-flash",
    "voice_api_key": "", "snap_provider": "anthropic", "snap_model": "claude-haiku-4-5-20251001",
    "snap_api_key": "", "temperature": 0.7, "presence_cooldown": 1800,
    "whisper_model": "small", "wake_word": "claudius",
    "mic_name": "BIRD UM1", "brain_path": "", "audio_ignore": [],
    "bg_effect": "auto", "bg_intensity": 0.7, "bg_speed": 1.0, "lang": "fr",
    "theme_custom": {},
}
_boot_time = time.time()
_auto_restart_enabled = True
app = Flask(__name__)


def _check_pid(pidfile):
    try:
        pid = int(open(pidfile).read().strip())
        import ctypes; k = ctypes.windll.kernel32; h = k.OpenProcess(0x1000, False, pid)
        if h: k.CloseHandle(h); return True
    except Exception: pass
    return False

def _launch_bridge():
    try:
        pw = os.environ.get("CLAUDIUS_PYTHON", "pythonw.exe")
        subprocess.Popen([pw, BRIDGE_SCRIPT], creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS, cwd=_SCRIPT_DIR)
        return True
    except Exception: return False

def _auto_restart_thread():
    time.sleep(20)
    while True:
        time.sleep(15)
        if not _auto_restart_enabled: continue
        if os.path.exists(STOP_FLAG): continue
        if not _check_pid(BRIDGE_PID_FILE):
            print("[DASHBOARD] Bridge mort - relance...", flush=True); time.sleep(2); _launch_bridge()


@app.after_request
def _no_cache(resp):
    # WebView2 CACHE agressivement la page -> les fenetres affichaient un
    # VIEUX HTML/JS malgre les relances (jauge inerte, vecu 2026-06-11).
    # Pattern Odysseus : no-store partout + ?v=ticks cote fenetre.
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp

@app.route("/")
def index():
    try:
        with open(HTML_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"<pre>claudius_dash.html introuvable : {e}</pre>", 500

@app.route("/dashboard-fx.js")
def fx_js():
    return send_file(FX_FILE, mimetype="application/javascript")

@app.route("/claudius_i18n.js")
def i18n_js():
    return send_file(os.path.join(_SCRIPT_DIR, "claudius_i18n.js"), mimetype="application/javascript")

@app.route("/api/transcript")
def api_transcript():
    start = int(request.args.get("from", 0))
    try:
        with open(TRANSCRIPT_FILE, "r", encoding="utf-8") as f: all_lines = f.readlines()
        return jsonify({"lines": [l.rstrip() for l in all_lines[start:]], "total": len(all_lines)})
    except FileNotFoundError: return jsonify({"lines": [], "total": 0})

_LOG_NOISE = ("CMD> blink", "CMD: blink", "OK: blink", "DEPTH:", "Config:")

@app.route("/api/logs")
def api_logs():
    n = int(request.args.get("n", 150))
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f: all_lines = f.readlines()
        filtered = [l.rstrip() for l in all_lines if not any(x in l for x in _LOG_NOISE)]
        return jsonify({"lines": filtered[-n:], "total": len(filtered)})
    except FileNotFoundError: return jsonify({"lines": [], "total": 0})

@app.route("/api/stats")
def api_stats():
    uptime = int(time.time() - _boot_time)
    presence = "unknown"
    try: presence = open(PRESENCE_FILE).read().strip().split('\n')[0]
    except Exception: pass
    mem_count = 0
    try: mem_count = len(json.load(open(MEMORY_FILE, encoding="utf-8")))
    except Exception: pass
    exchanges = 0
    try: exchanges = sum(1 for l in open(TRANSCRIPT_FILE, encoding="utf-8") if "David:" in l)
    except Exception: pass
    bridge_alive = _check_pid(BRIDGE_PID_FILE); voice_alive = _check_pid(VOICE_PID_FILE)
    voice_hb_age = -1
    try: voice_hb_age = int(time.time() - os.path.getmtime(VOICE_HEARTBEAT))
    except Exception: pass
    motor_status = "unknown"
    try:
        if bridge_alive:
            motor_status = open(MOTOR_STATUS_FILE).read().strip() or "unknown"
    except Exception: pass
    # Vu-metre micro : "rms;seuil_effectif" ecrit par KinectVoice (~0.4 s), -1 si stale
    mic_level, mic_threshold = -1, -1
    try:
        lf = os.path.join(_DATA_DIR, "voice_level.txt")
        if time.time() - os.path.getmtime(lf) < 3:
            parts = open(lf).read().strip().split(";")
            mic_level = int(float(parts[0]))
            if len(parts) > 1:
                mic_threshold = int(float(parts[1]))
    except Exception: pass
    return jsonify({"uptime": uptime, "presence": presence, "memories": mem_count,
                    "exchanges": exchanges, "bridge_alive": bridge_alive,
                    "voice_alive": voice_alive, "voice_hb_age": voice_hb_age,
                    "motor_status": motor_status,
                    "mic_level": mic_level, "mic_threshold": mic_threshold})

@app.route("/api/miclevel")
def api_miclevel():
    """Vu-metre : poll leger et rapide (la jauge a son propre rythme, 400 ms)."""
    level, threshold = -1, -1
    try:
        lf = os.path.join(_DATA_DIR, "voice_level.txt")
        if time.time() - os.path.getmtime(lf) < 3:
            parts = open(lf).read().strip().split(";")
            level = int(float(parts[0]))
            if len(parts) > 1:
                threshold = int(float(parts[1]))
    except Exception: pass
    return jsonify({"level": level, "threshold": threshold})

@app.route("/api/devices")
def api_devices():
    """Micros disponibles (hostapi 0 = MME), dedupliques — pour le selecteur
    'micro par nom' du dashboard."""
    inputs = []
    try:
        import sounddevice as sd
        seen = set()
        for d in sd.query_devices():
            if d.get("max_input_channels", 0) > 0 and d.get("hostapi", -1) == 0:
                name = d["name"].strip()
                if name and name not in seen and "Mapper" not in name:
                    seen.add(name)
                    inputs.append(name)
    except Exception as e:
        return jsonify({"inputs": [], "error": str(e)})
    return jsonify({"inputs": inputs})

@app.route("/api/cmd", methods=["POST"])
def api_cmd():
    cmd = request.get_json().get("cmd", "").strip()
    if not cmd: return jsonify({"ok": False})
    with open(CMD_FILE, "w", encoding="utf-8") as f: f.write(cmd)
    return jsonify({"ok": True, "cmd": cmd})

@app.route("/api/restart", methods=["POST"])
def api_restart():
    try:
        try: os.remove(STOP_FLAG)
        except FileNotFoundError: pass
        try:
            pid = int(open(BRIDGE_PID_FILE).read().strip())
            import ctypes; h = ctypes.windll.kernel32.OpenProcess(1, False, pid)
            if h: ctypes.windll.kernel32.TerminateProcess(h, 0); ctypes.windll.kernel32.CloseHandle(h)
        except Exception: pass
        # Tuer aussi Voice : il relit settings (micro/seuil/wake) a son boot,
        # et le watchdog du nouveau Bridge le relancera proprement.
        try:
            pid = int(open(VOICE_PID_FILE).read().strip())
            import ctypes; h = ctypes.windll.kernel32.OpenProcess(1, False, pid)
            if h: ctypes.windll.kernel32.TerminateProcess(h, 0); ctypes.windll.kernel32.CloseHandle(h)
            os.remove(VOICE_PID_FILE)
        except Exception: pass
        time.sleep(2); _launch_bridge(); return jsonify({"ok": True})
    except Exception as e: return jsonify({"ok": False, "error": str(e)})

@app.route("/api/logs/clear", methods=["POST"])
def api_logs_clear():
    try: open(LOG_FILE, "w").close(); return jsonify({"ok": True})
    except Exception: return jsonify({"ok": False})

@app.route("/api/settings")
def api_settings_get():
    try:
        with open(SETTINGS_FILE, "r") as f: s = json.load(f)
        for k, v in _DEFAULT_SETTINGS.items():
            if k not in s: s[k] = v
        return jsonify(s)
    except Exception: return jsonify(dict(_DEFAULT_SETTINGS))

@app.route("/api/settings", methods=["POST"])
def api_settings_set():
    try:
        data = request.get_json()
        try:
            with open(SETTINGS_FILE, "r") as f: s = json.load(f)
        except Exception: s = dict(_DEFAULT_SETTINGS)
        for k, v in data.items():
            if k in _DEFAULT_SETTINGS:
                # Cle API vide envoyee = "ne pas changer" (le champ password est
                # toujours vide a l'affichage)
                if k in ("voice_api_key", "snap_api_key") and v == "":
                    continue
                s[k] = v
        with open(SETTINGS_FILE, "w") as f: json.dump(s, f, indent=2)
        return jsonify({"ok": True, "settings": s})
    except Exception as e: return jsonify({"ok": False, "error": str(e)})

@app.route("/api/profiles")
def api_profiles_list():
    pfile = os.path.join(_DATA_DIR, "claudius_profiles.json")
    try:
        with open(pfile, "r") as f: return jsonify(json.load(f))
    except Exception: return jsonify({})

@app.route("/api/profiles", methods=["POST"])
def api_profiles_save():
    data = request.get_json(); pfile = os.path.join(_DATA_DIR, "claudius_profiles.json")
    try:
        with open(pfile, "r") as f: profiles = json.load(f)
    except Exception: profiles = {}
    name = data.get("name", "")
    if data.get("delete"): profiles.pop(name, None)
    else: profiles[name] = data.get("settings", {})
    with open(pfile, "w") as f: json.dump(profiles, f, indent=2)
    return jsonify({"ok": True, "profiles": list(profiles.keys())})

@app.route("/api/window", methods=["POST"])
def api_window_save():
    try:
        with open(WINDOW_FILE, "w") as f: json.dump(request.get_json(), f)
        return jsonify({"ok": True})
    except Exception: return jsonify({"ok": False})


# ====================================================================
# FENETRE NATIVE pywebview — frameless, drag dans la topbar HTML
# ====================================================================
class _WinApi:
    """API exposee au JS (window.pywebview.api.*) pour les boutons – ▢ ✕.
    ⚠️ La Window DOIT etre dans un attribut PRIVE (_window) : un attribut
    public est serialise par le bridge JS de pywebview, qui part en recursion
    infinie sur l'objet WinForms natif et CRASH le process (vecu 2026-06-11)."""
    def __init__(self):
        self._window = None
        self._maximized = False

    def minimize(self):
        if self._window: self._window.minimize()

    def toggle_maximize(self):
        if not self._window: return
        if self._maximized:
            self._window.restore(); self._maximized = False
        else:
            self._window.maximize(); self._maximized = True

    def close_window(self):
        if self._window: self._window.destroy()


def _load_geometry():
    w, h, x, y = 1280, 800, None, None
    try:
        with open(WINDOW_FILE, "r") as f:
            wc = json.load(f)
            w, h = int(wc.get("w", 1280)), int(wc.get("h", 800))
            x, y = wc.get("x"), wc.get("y")
    except Exception: pass
    return w, h, x, y


def _save_geometry(window):
    try:
        with open(WINDOW_FILE, "w") as f:
            json.dump({"w": window.width, "h": window.height,
                       "x": window.x, "y": window.y}, f)
    except Exception: pass


def _enable_native_resize(window):
    """Frameless + WS_THICKFRAME = poignees de resize natives sur les bords
    (hack borderless classique : Windows gere le resize/snap, zero JS)."""
    try:
        import ctypes
        h = window.native.Handle
        hwnd = int(h.ToInt64()) if hasattr(h, "ToInt64") else int(h)
        GWL_STYLE = -16
        WS_THICKFRAME = 0x00040000
        WS_MAXIMIZEBOX = 0x00010000
        WS_MINIMIZEBOX = 0x00020000
        u = ctypes.windll.user32
        get_l = getattr(u, "GetWindowLongPtrW", u.GetWindowLongW)
        set_l = getattr(u, "SetWindowLongPtrW", u.SetWindowLongW)
        style = get_l(hwnd, GWL_STYLE) | WS_THICKFRAME | WS_MAXIMIZEBOX | WS_MINIMIZEBOX
        set_l(hwnd, GWL_STYLE, style)
        # SWP_FRAMECHANGED : appliquer le nouveau cadre sans bouger la fenetre
        u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0020 | 0x0002 | 0x0001 | 0x0004)
    except Exception:
        pass  # pas de resize natif, la fenetre reste utilisable


def _open_native_window():
    import webview
    api = _WinApi()
    w, h, x, y = _load_geometry()
    kwargs = dict(width=w, height=h, frameless=True, easy_drag=False,
                  background_color="#111111", js_api=api)
    if x is not None and y is not None:
        kwargs.update(x=int(x), y=int(y))
    # ?v=<ts> : URL unique a chaque lancement -> le cache WebView2 ne peut
    # jamais resservir une vieille page (le serveur envoie aussi no-store)
    win = webview.create_window("Claudius Dashboard",
                                f"http://localhost:5005/?v={int(time.time())}", **kwargs)
    api._window = win

    def _on_shown():
        _enable_native_resize(win)

    def _on_geom(*_a):
        # Sauver a CHAQUE resize/move : la geometrie survit meme a un kill
        # (avant : seulement a la fermeture propre — feature aimee de David)
        _save_geometry(win)

    def _on_closing():
        _save_geometry(win)
    win.events.shown += _on_shown
    win.events.resized += _on_geom
    win.events.moved += _on_geom
    win.events.closing += _on_closing
    webview.start()


if __name__ == "__main__":
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    port_taken = sock.connect_ex(("127.0.0.1", 5005)) == 0
    sock.close()

    if port_taken:
        # Serveur deja actif — ouvrir juste la fenetre native et quitter apres
        if "--no-window" not in sys.argv:
            _open_native_window()
        sys.exit(0)

    print("[DASHBOARD] http://localhost:5005")
    threading.Thread(target=_auto_restart_thread, daemon=True).start()

    if "--no-window" in sys.argv:
        app.run(host="127.0.0.1", port=5005, debug=False, use_reloader=False)
    else:
        # Flask en thread + fenetre native au premier plan
        threading.Thread(
            target=lambda: app.run(host="127.0.0.1", port=5005, debug=False, use_reloader=False),
            daemon=True).start()
        time.sleep(1.0)
        _open_native_window()
