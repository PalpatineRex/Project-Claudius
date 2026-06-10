"""
KinectDashboard.py v3 — Dashboard temps reel Project Claudius
http://localhost:5005 — Lance en parallele de KinectBridge.
Features: auto-restart bridge si mort, commandes vocales, logs, transcript.
"""
from flask import Flask, request, jsonify
import os, sys, time, json, subprocess, threading, webbrowser

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
BRIDGE_SCRIPT = os.path.join(_SCRIPT_DIR, "KinectBridge.py")
SETTINGS_FILE = os.path.join(_DATA_DIR, "claudius_settings.json")
STOP_FLAG = os.path.join(_DATA_DIR, "claudius_stop.flag")
_DEFAULT_SETTINGS = {"sfx_volume":0.3,"presence_enabled":True,"mic_threshold":500,"theme":"dark","max_tokens":500,"llm_timeout":25,"tts_speed":1.0,"history_size":6,"voice_provider":"deepseek","voice_model":"deepseek-v4-flash","voice_api_key":"","snap_provider":"anthropic","snap_model":"claude-haiku-4-5-20251001","snap_api_key":"","temperature":0.7,"presence_cooldown":30,"whisper_model":"small","wake_word":"claudius"}
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
@app.route("/")
def index(): return HTML
@app.route("/api/transcript")
def api_transcript():
    start = int(request.args.get("from", 0))
    try:
        with open(TRANSCRIPT_FILE, "r", encoding="utf-8") as f: all_lines = f.readlines()
        return jsonify({"lines": [l.rstrip() for l in all_lines[start:]], "total": len(all_lines)})
    except FileNotFoundError: return jsonify({"lines": [], "total": 0})
@app.route("/api/logs")
def api_logs():
    n = int(request.args.get("n", 150))
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f: all_lines = f.readlines()
        filtered = [l.rstrip() for l in all_lines if "CMD> blink" not in l and "CMD: blink" not in l and "DEPTH:" not in l and "Config:" not in l]
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
    return jsonify({"uptime":uptime,"presence":presence,"memories":mem_count,"exchanges":exchanges,"bridge_alive":bridge_alive,"voice_alive":voice_alive,"voice_hb_age":voice_hb_age})
@app.route("/api/cmd", methods=["POST"])
def api_cmd():
    cmd = request.get_json().get("cmd", "").strip()
    if not cmd: return jsonify({"ok": False})
    with open(CMD_FILE, "w", encoding="utf-8") as f: f.write(cmd)
    return jsonify({"ok": True, "cmd": cmd})
@app.route("/api/restart", methods=["POST"])
def api_restart():
    try:
        # Supprimer le stop flag si present
        try: os.remove(STOP_FLAG)
        except FileNotFoundError: pass
        try:
            pid = int(open(BRIDGE_PID_FILE).read().strip())
            import ctypes; h = ctypes.windll.kernel32.OpenProcess(1, False, pid)
            if h: ctypes.windll.kernel32.TerminateProcess(h, 0); ctypes.windll.kernel32.CloseHandle(h)
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
            if k in _DEFAULT_SETTINGS: s[k] = v
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
        data = request.get_json()
        win_file = os.path.join(_DATA_DIR, "claudius_window.json")
        with open(win_file, "w") as f: json.dump(data, f)
        return jsonify({"ok": True})
    except Exception: return jsonify({"ok": False})

HTML = r"""<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Claudius Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600&family=Orbitron:wght@400;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#080a0f;--panel:#0c1018;--border:#1a2233;--cyan:#00e5ff;--green:#39ff14;--amber:#ffb300;--red:#ff1744;--dim:#4a5568;--text:#c9d1d9;}
*{margin:0;padding:0;box-sizing:border-box;}
body{background:var(--bg);color:var(--text);font-family:'JetBrains Mono',monospace;font-size:13px;overflow:hidden;height:100vh;}
.hdr{display:flex;align-items:center;justify-content:space-between;padding:10px 20px;border-bottom:1px solid var(--border);background:var(--panel);}
.hdr-left{display:flex;align-items:center;gap:12px;}.logo{font-family:Orbitron;font-size:16px;font-weight:700;color:var(--cyan);letter-spacing:2px;}
.hdr-right{display:flex;align-items:center;gap:16px;font-size:11px;}.hdr-right b{margin-left:3px;}
.grid{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr auto;height:calc(100vh - 45px);gap:1px;background:var(--border);}
.pnl{background:var(--panel);display:flex;flex-direction:column;overflow:hidden;}
.pnl-hdr{padding:8px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;font-size:10px;font-family:Orbitron;letter-spacing:1px;}
.pnl-body{flex:1;overflow-y:auto;padding:10px 14px;}
.ctrl{background:var(--panel);grid-column:1/3;display:flex;align-items:center;gap:12px;padding:8px 14px;border-top:1px solid var(--border);}
.ctrl select,.ctrl input{background:#111827;color:var(--text);border:1px solid var(--border);padding:4px 8px;font-family:inherit;font-size:12px;border-radius:3px;outline:none;}
.ctrl input{flex:1;padding:5px 10px;}.ctrl input:focus{border-color:var(--cyan);box-shadow:0 0 6px rgba(0,229,255,0.2);}
.btn{border:none;padding:5px 16px;font-family:Orbitron;font-size:10px;font-weight:700;border-radius:3px;cursor:pointer;letter-spacing:1px;}
.btn-send{background:var(--cyan);color:#000;}.btn-rst{background:var(--red);color:#fff;padding:5px 12px;font-size:9px;}
.btn-clr{background:#333;color:var(--text);padding:5px 8px;font-size:9px;}
.msg-david{color:#7eb8da;}.msg-claudius{color:var(--green);}
.msg-david .nm{color:var(--cyan);font-weight:600;}.msg-claudius .nm{color:var(--green);font-weight:600;}
.ts{color:#333d4a;font-size:11px;margin-right:6px;}
.log-err{color:var(--red);}.log-llm{color:var(--cyan);}.log-motor{color:#555;}.log-voice{color:var(--amber);}.log-sfx{color:#9966cc;}.log-timer{color:var(--green);}
#logs{font-size:11px;color:#8899aa;}
.si{background:#111827;color:var(--text);border:1px solid var(--border);padding:4px 8px;font-family:inherit;font-size:11px;border-radius:3px;width:100%;margin-top:4px;}
.tip{font-size:9px;color:#555;margin-top:2px;}
::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
</style></head><body>
<div class="hdr"><div class="hdr-left"><span class="logo">&#x2B21; CLAUDIUS</span><span id="st-status" style="font-size:11px;color:var(--dim)">connecting...</span></div>
<div class="hdr-right"><span>UPTIME <b id="st-uptime" style="color:var(--cyan)">--</b></span><span>PRESENCE <b id="st-presence" style="color:var(--dim)">--</b></span><span>EXCHANGES <b id="st-exchanges" style="color:var(--amber)">0</b></span><span>MEMORIES <b id="st-memories" style="color:var(--green)">0</b></span></div></div>
<div class="grid">
<div class="pnl"><div class="pnl-hdr" style="color:var(--cyan)">&#x25B8; CONVERSATION <span id="conv-count" style="color:var(--dim)"></span></div><div class="pnl-body" id="conv"></div></div>
<div class="pnl"><div class="pnl-hdr" style="color:var(--amber)">&#x25B8; BRIDGE LOGS <button class="btn btn-clr" onclick="clearLogs()" style="margin-left:auto">CLEAR</button><label style="margin-left:8px;font-size:10px;color:var(--dim);cursor:pointer;font-family:inherit"><input type="checkbox" id="log-auto" checked style="margin-right:4px">autoscroll</label></div><div class="pnl-body" id="logs"></div></div>
<div class="ctrl"><span style="color:var(--green);font-size:10px;font-family:Orbitron;letter-spacing:1px">&#x25B8; CTRL</span>
<select id="cmd-prefix"><option value="VOICE:">VOICE:</option><option value="">RAW</option><option value="oui">oui</option><option value="non">non</option><option value="hello">hello</option><option value="think">think</option><option value="blink">blink</option><option value="snap">snap</option></select>
<input id="cmd-input" type="text" placeholder="Message ou commande...">
<button class="btn btn-send" onclick="sendCmd()">SEND</button><button class="btn btn-rst" onclick="restartBridge()">RESTART</button>
<span style="font-size:10px;color:var(--dim)">Bridge <b id="st-bridge">?</b> | Voice <b id="st-voice">?</b> <span id="st-hb"></span></span>
<button class="btn" style="background:#222;color:var(--text);margin-left:8px;font-size:10px" onclick="toggleSettings()">&#x2699; OPTIONS</button></div></div>
<div id="settings-overlay" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:100;justify-content:center;align-items:center;">
<div style="background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:24px 32px;width:560px;max-height:85vh;overflow-y:auto;">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;"><span style="font-family:Orbitron;font-size:13px;color:var(--cyan);letter-spacing:1px">&#x2699; OPTIONS</span><button onclick="toggleSettings()" style="background:none;border:none;color:var(--dim);cursor:pointer;font-size:18px">&times;</button></div>
<div style="display:flex;flex-direction:column;gap:14px;">
<div style="font-family:Orbitron;font-size:10px;color:var(--cyan);letter-spacing:1px;margin-top:4px" data-i18n="sec_audio">&#x25B8; AUDIO</div>
<div><label style="font-size:11px;color:var(--dim)" data-i18n="vol_lbl">VOLUME SFX</label><div style="display:flex;align-items:center;gap:10px;margin-top:4px"><input type="range" id="set-vol" min="0" max="100" value="30" style="flex:1;accent-color:var(--cyan)"><span id="set-vol-val" style="font-size:12px;color:var(--cyan);min-width:32px">30%</span></div><div class="tip" data-i18n="vol_tip">Volume des effets sonores (boot, listen, presence, alarm).</div></div>
<div><label style="font-size:11px;color:var(--dim)" data-i18n="mic_lbl">SEUIL MICRO (RMS)</label><div style="display:flex;align-items:center;gap:10px;margin-top:4px"><input type="range" id="set-mic" min="200" max="2000" step="50" value="500" style="flex:1;accent-color:var(--amber)"><span id="set-mic-val" style="font-size:12px;color:var(--amber);min-width:40px">500</span></div><div class="tip" data-i18n="mic_tip">Sensibilite du micro. Bas = capte tout, haut = ignore le bruit ambiant. Calibre auto au boot (~ambiant x1.5).</div></div>
<div><label style="font-size:11px;color:var(--dim)" data-i18n="tts_lbl">VITESSE TTS</label><div style="display:flex;align-items:center;gap:10px;margin-top:4px"><input type="range" id="set-tts" min="70" max="130" step="5" value="100" style="flex:1;accent-color:var(--amber)"><span id="set-tts-val" style="font-size:12px;color:var(--amber);min-width:40px">1.0x</span></div><div class="tip" data-i18n="tts_tip">Vitesse de la voix Piper. 0.8x = lent/clair, 1.0x = normal, 1.2x = rapide.</div></div>
<div><label style="font-size:11px;color:var(--dim)" data-i18n="whisper_lbl">MODELE WHISPER</label><select id="set-whisper" class="si"><option value="tiny">tiny (rapide, moins precis)</option><option value="base">base</option><option value="small" selected>small (recommande)</option><option value="medium">medium (lent, plus precis)</option></select><div class="tip" data-i18n="whisper_tip">Modele faster-whisper pour la reconnaissance vocale. Necessite un restart du Bridge.</div></div>
<div><label style="font-size:11px;color:var(--dim)" data-i18n="wake_lbl">MOT-CLE WAKE</label><input type="text" id="set-wake" value="claudius" class="si"><div class="tip" data-i18n="wake_tip">Mot-cle pour activer l'ecoute. Fuzzy match phonetique (tolere les approximations).</div></div>
<hr style="border:none;border-top:1px solid var(--border);margin:4px 0">
<div style="font-family:Orbitron;font-size:10px;color:var(--green);letter-spacing:1px" data-i18n="sec_llm">&#x25B8; LLM / IA</div>
<div style="font-size:10px;color:var(--cyan);margin-bottom:2px" data-i18n="vprov_sub">Voix (reponses texte)</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><div><label style="font-size:11px;color:var(--dim)" data-i18n="vprov_lbl">PROVIDER</label><input type="text" id="set-vprov" value="deepseek" placeholder="deepseek" class="si"></div><div><label style="font-size:11px;color:var(--dim)" data-i18n="vmodel_lbl">MODELE</label><input type="text" id="set-vmodel" value="deepseek-v4-flash" class="si"></div></div>
<div><label style="font-size:11px;color:var(--dim)" data-i18n="vkey_lbl">CLE API VOIX</label><input type="password" id="set-vkey" value="" data-i18n="vkey_ph" placeholder="Laisser vide = utilise deepseek_key.txt" class="si"></div>
<div class="tip" data-i18n="vprov_tip">Provider = nom du service API. Supportes : <b>deepseek</b> (deepseek-v4-flash, deepseek-v4-pro), <b>anthropic</b> (claude-haiku-4-5-20251001, claude-sonnet-4-20250514), <b>openrouter</b> (500+ modeles, format: provider/modele), <b>openai</b> (gpt-4o). L'URL est resolue automatiquement. Cle vide = fallback sur deepseek_key.txt ou api_key.txt local.</div>
<div style="font-size:10px;color:var(--cyan);margin-top:8px;margin-bottom:2px" data-i18n="sprov_sub">Vision (commande snap)</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><div><label style="font-size:11px;color:var(--dim)" data-i18n="sprov_lbl">PROVIDER</label><input type="text" id="set-sprov" value="anthropic" placeholder="anthropic" class="si"></div><div><label style="font-size:11px;color:var(--dim)" data-i18n="smodel_lbl">MODELE</label><input type="text" id="set-smodel" value="claude-haiku-4-5-20251001" class="si"></div></div>
<div><label style="font-size:11px;color:var(--dim)" data-i18n="skey_lbl">CLE API VISION</label><input type="password" id="set-skey" value="" data-i18n="skey_ph" placeholder="Laisser vide = utilise api_key.txt" class="si"></div>
<div class="tip" data-i18n="sprov_tip">La vision necessite un modele multimodal (qui accepte les images). Seul Anthropic (Claude Haiku/Sonnet) est garanti. DeepSeek ne supporte pas les images via API. Via OpenRouter, choisir un modele multimodal (ex: anthropic/claude-haiku-4-5-20251001).</div>
<hr style="border:none;border-top:1px solid var(--border);margin:4px 0">
<div style="font-family:Orbitron;font-size:10px;color:#9966cc;letter-spacing:1px" data-i18n="sec_profiles">&#x25B8; PROFILS</div>
<div style="display:flex;gap:8px;align-items:center"><select id="set-profile" class="si" style="width:auto;flex:1"><option value="_default">Defaut</option></select><button onclick="saveProfile()" class="btn" style="background:#333;color:var(--text);font-size:9px;padding:4px 10px">SAVE</button><button onclick="loadProfile()" class="btn" style="background:#333;color:var(--text);font-size:9px;padding:4px 10px">LOAD</button><button onclick="deleteProfile()" class="btn" style="background:#331111;color:var(--red);font-size:9px;padding:4px 10px">DEL</button></div>
<div style="display:flex;gap:8px;align-items:center"><input type="text" id="new-profile-name" data-i18n="prof_ph" placeholder="Nom du nouveau profil..." class="si" style="width:auto;flex:1"><button onclick="createProfile()" class="btn" style="background:#113311;color:var(--green);font-size:9px;padding:4px 10px">NEW</button></div>
<div class="tip" data-i18n="prof_tip">Sauvegarder et charger des configurations completes. Creez un profil avec NEW, puis SAVE. LOAD pour restaurer.</div>
<div><label style="font-size:11px;color:var(--dim)" data-i18n="tokens_lbl">MAX TOKENS</label><div style="display:flex;align-items:center;gap:10px;margin-top:4px"><input type="range" id="set-tokens" min="100" max="2000" step="50" value="500" style="flex:1;accent-color:var(--green)"><span id="set-tokens-val" style="font-size:12px;color:var(--green);min-width:40px">500</span></div><div class="tip" data-i18n="tokens_tip">Longueur max des reponses LLM. 200=concis, 500=normal, 1000+=detaille. Les modeles avec reflexion (DeepSeek) consomment des tokens pour reflechir.</div></div>
<div><label style="font-size:11px;color:var(--dim)" data-i18n="timeout_lbl">TIMEOUT LLM</label><div style="display:flex;align-items:center;gap:10px;margin-top:4px"><input type="range" id="set-timeout" min="10" max="60" step="5" value="25" style="flex:1;accent-color:var(--green)"><span id="set-timeout-val" style="font-size:12px;color:var(--green);min-width:32px">25s</span></div><div class="tip" data-i18n="timeout_tip">Temps max d'attente pour la reponse API. Augmenter si connexion lente.</div></div>
<div><label style="font-size:11px;color:var(--dim)" data-i18n="temp_lbl">TEMPERATURE</label><div style="display:flex;align-items:center;gap:10px;margin-top:4px"><input type="range" id="set-temp" min="0" max="100" step="5" value="70" style="flex:1;accent-color:var(--green)"><span id="set-temp-val" style="font-size:12px;color:var(--green);min-width:32px">0.7</span></div><div class="tip" data-i18n="temp_tip">Creativite des reponses. 0.0=deterministe, 0.7=naturel, 1.0+=imprevisible.</div></div>
<div><label style="font-size:11px;color:var(--dim)" data-i18n="hist_lbl">HISTORIQUE CONV</label><div style="display:flex;align-items:center;gap:10px;margin-top:4px"><input type="range" id="set-hist" min="2" max="20" step="1" value="6" style="flex:1;accent-color:var(--cyan)"><span id="set-hist-val" style="font-size:12px;color:var(--cyan);min-width:24px">6</span></div><div class="tip" data-i18n="hist_tip">Paires question/reponse en memoire courte. Plus=meilleur contexte, mais plus de tokens par requete.</div></div>
<hr style="border:none;border-top:1px solid var(--border);margin:4px 0">
<div style="font-family:Orbitron;font-size:10px;color:var(--amber);letter-spacing:1px" data-i18n="sec_system">&#x25B8; SYSTEME</div>
<div style="display:flex;align-items:center;justify-content:space-between"><div><label style="font-size:11px;color:var(--dim)" data-i18n="pres_lbl">PRESENCE DETECTION</label><div class="tip" data-i18n="pres_tip">Salutation auto quand le Kinect detecte une personne.</div></div><label style="position:relative;width:40px;height:22px;cursor:pointer;flex-shrink:0"><input type="checkbox" id="set-presence" checked style="opacity:0;width:0;height:0"><span id="set-presence-bg" style="position:absolute;top:0;left:0;right:0;bottom:0;background:var(--green);border-radius:11px;transition:.3s"></span><span id="set-presence-dot" style="position:absolute;top:2px;left:20px;width:18px;height:18px;background:#fff;border-radius:50%;transition:.3s"></span></label></div>
<div><label style="font-size:11px;color:var(--dim)" data-i18n="pcool_lbl">COOLDOWN PRESENCE</label><div style="display:flex;align-items:center;gap:10px;margin-top:4px"><input type="range" id="set-pcool" min="10" max="120" step="5" value="30" style="flex:1;accent-color:var(--amber)"><span id="set-pcool-val" style="font-size:12px;color:var(--amber);min-width:32px">30s</span></div><div class="tip" data-i18n="pcool_tip">Delai minimum entre deux salutations. Evite le spam si vous passez souvent devant le Kinect.</div></div>
<div style="display:flex;align-items:center;justify-content:space-between"><label style="font-size:11px;color:var(--dim)">THEME</label><select id="set-theme" class="si" style="width:auto" onchange="applyTheme(this.value)"><option value="dark">Sombre</option><option value="light">Clair</option><option value="midnight">Midnight</option><option value="matrix">Matrix</option><option value="ember">Ember</option><option value="cyberpunk">Cyberpunk</option><option value="ocean">Ocean</option><option value="nord">Nord</option><option value="solar">Solar</option><option value="synthwave">Synthwave</option></select></div>
<div style="display:flex;align-items:center;justify-content:space-between"><label style="font-size:11px;color:var(--dim)" data-i18n="lang_label">LANGUE / LANGUAGE</label><select id="set-lang" class="si" style="width:auto" onchange="applyLang(this.value)"><option value="fr">Francais</option><option value="en">English</option></select></div>
</div>
<button onclick="saveSettings()" class="btn btn-send" style="margin-top:20px;width:100%;padding:8px">SAUVEGARDER</button>
<div class="tip" style="text-align:center;margin-top:8px">Les changements de provider, cle API, Whisper ou Wake Word necessitent un restart du Bridge.</div>
</div></div>
<script>
let cLen=0,lHash='',_lang='fr';const $=id=>document.getElementById(id);
const _i18n={fr:{
conv_hdr:'CONVERSATION',logs_hdr:'BRIDGE LOGS',ctrl_lbl:'CTRL',
msg_ph:'Message ou commande...',save_btn:'SAUVEGARDER',opts_title:'OPTIONS',
sec_audio:'AUDIO',sec_llm:'LLM / IA',sec_profiles:'PROFILS',sec_system:'SYSTEME',
vol_lbl:'VOLUME SFX',vol_tip:'Volume des effets sonores (boot, listen, presence, alarm).',
mic_lbl:'SEUIL MICRO (RMS)',mic_tip:'Sensibilite du micro. Bas = capte tout, haut = ignore le bruit ambiant. Calibre auto au boot (~ambiant x1.5).',
tts_lbl:'VITESSE TTS',tts_tip:'Vitesse de la voix Piper. 0.8x = lent/clair, 1.0x = normal, 1.2x = rapide.',
whisper_lbl:'MODELE WHISPER',whisper_tip:'Modele faster-whisper pour la reconnaissance vocale. Necessite un restart du Bridge.',
wake_lbl:'MOT-CLE WAKE',wake_tip:'Mot-cle pour activer l\'ecoute. Fuzzy match phonetique (tolere les approximations).',
vprov_sub:'Voix (reponses texte)',vprov_lbl:'PROVIDER',vmodel_lbl:'MODELE',vkey_lbl:'CLE API VOIX',
vkey_ph:'Laisser vide = utilise deepseek_key.txt',
vprov_tip:'Provider = nom du service API. Supportes : deepseek (deepseek-v4-flash, deepseek-v4-pro), anthropic (claude-haiku-4-5-20251001, claude-sonnet-4-20250514), openrouter (500+ modeles, format: provider/modele), openai (gpt-4o). L\'URL est resolue automatiquement. Cle vide = fallback sur deepseek_key.txt ou api_key.txt local.',
sprov_sub:'Vision (commande snap)',sprov_lbl:'PROVIDER',smodel_lbl:'MODELE',skey_lbl:'CLE API VISION',
skey_ph:'Laisser vide = utilise api_key.txt',
sprov_tip:'La vision necessite un modele multimodal (qui accepte les images). Seul Anthropic (Claude Haiku/Sonnet) est garanti. DeepSeek ne supporte pas les images via API. Via OpenRouter, choisir un modele multimodal (ex: anthropic/claude-haiku-4-5-20251001).',
prof_tip:'Sauvegarder et charger des configurations completes. Creez un profil avec NEW, puis SAVE. LOAD pour restaurer.',
prof_ph:'Nom du nouveau profil...',
tokens_lbl:'MAX TOKENS',tokens_tip:'Longueur max des reponses LLM. 200=concis, 500=normal, 1000+=detaille. Les modeles avec reflexion (DeepSeek) consomment des tokens pour reflechir.',
timeout_lbl:'TIMEOUT LLM',timeout_tip:'Temps max d\'attente pour la reponse API. Augmenter si connexion lente.',
temp_lbl:'TEMPERATURE',temp_tip:'Creativite des reponses. 0.0=deterministe, 0.7=naturel, 1.0+=imprevisible.',
hist_lbl:'HISTORIQUE CONV',hist_tip:'Paires question/reponse en memoire courte. Plus=meilleur contexte, mais plus de tokens par requete.',
pres_lbl:'PRESENCE DETECTION',pres_tip:'Salutation auto quand le Kinect detecte une personne.',
pcool_lbl:'COOLDOWN PRESENCE',pcool_tip:'Delai minimum entre deux salutations. Evite le spam si vous passez souvent devant le Kinect.',
lang_label:'LANGUE / LANGUAGE',save_note:'Les changements de provider, cle API, Whisper ou Wake Word necessitent un restart du Bridge.',
here:'ICI',absent:'ABSENT',restart_confirm:'Restart Bridge + Voice ?',restart_ok:'Bridge relance !',logs_cleared:'Logs effaces.',
prof_save_err:'Selectionnez ou creez un profil avant de sauver.',prof_saved:'Profil sauve: ',prof_del_confirm:'Supprimer le profil ',prof_new_err:'Entrez un nom de profil.',prof_created:'Profil cree: ',save_err:'Erreur sauvegarde'
},en:{
conv_hdr:'CONVERSATION',logs_hdr:'BRIDGE LOGS',ctrl_lbl:'CTRL',
msg_ph:'Message or command...',save_btn:'SAVE',opts_title:'OPTIONS',
sec_audio:'AUDIO',sec_llm:'LLM / AI',sec_profiles:'PROFILES',sec_system:'SYSTEM',
vol_lbl:'SFX VOLUME',vol_tip:'Sound effects volume (boot, listen, presence, alarm).',
mic_lbl:'MIC THRESHOLD (RMS)',mic_tip:'Mic sensitivity. Low = picks up everything, high = ignores ambient noise. Auto-calibrated at boot (~ambient x1.5).',
tts_lbl:'TTS SPEED',tts_tip:'Piper voice speed. 0.8x = slow/clear, 1.0x = normal, 1.2x = fast.',
whisper_lbl:'WHISPER MODEL',whisper_tip:'Faster-whisper model for voice recognition. Requires Bridge restart.',
wake_lbl:'WAKE WORD',wake_tip:'Keyword to activate listening. Phonetic fuzzy match (tolerates approximations).',
vprov_sub:'Voice (text responses)',vprov_lbl:'PROVIDER',vmodel_lbl:'MODEL',vkey_lbl:'VOICE API KEY',
vkey_ph:'Leave empty = uses deepseek_key.txt',
vprov_tip:'Provider = API service name. Supported: deepseek (deepseek-v4-flash, deepseek-v4-pro), anthropic (claude-haiku-4-5-20251001, claude-sonnet-4-20250514), openrouter (500+ models, format: provider/model), openai (gpt-4o). URL is resolved automatically. Empty key = fallback to local deepseek_key.txt or api_key.txt.',
sprov_sub:'Vision (snap command)',sprov_lbl:'PROVIDER',smodel_lbl:'MODEL',skey_lbl:'VISION API KEY',
skey_ph:'Leave empty = uses api_key.txt',
sprov_tip:'Vision requires a multimodal model (that accepts images). Only Anthropic (Claude Haiku/Sonnet) is guaranteed. DeepSeek does not support images via API. Via OpenRouter, choose a multimodal model (e.g. anthropic/claude-haiku-4-5-20251001).',
prof_tip:'Save and load complete configurations. Create a profile with NEW, then SAVE. LOAD to restore.',
prof_ph:'New profile name...',
tokens_lbl:'MAX TOKENS',tokens_tip:'Max LLM response length. 200=concise, 500=normal, 1000+=detailed. Models with reasoning (DeepSeek) use tokens to "think".',
timeout_lbl:'LLM TIMEOUT',timeout_tip:'Max wait time for API response. Increase if connection is slow.',
temp_lbl:'TEMPERATURE',temp_tip:'Response creativity. 0.0=deterministic, 0.7=natural, 1.0+=unpredictable.',
hist_lbl:'CONV HISTORY',hist_tip:'Question/answer pairs in short-term memory. More=better context, but more tokens per request.',
pres_lbl:'PRESENCE DETECTION',pres_tip:'Auto greeting when Kinect detects a person.',
pcool_lbl:'PRESENCE COOLDOWN',pcool_tip:'Min delay between greetings. Prevents spam if you walk by the Kinect often.',
lang_label:'LANGUE / LANGUAGE',save_note:'Provider, API key, Whisper or Wake Word changes require a Bridge restart.',
here:'HERE',absent:'ABSENT',restart_confirm:'Restart Bridge + Voice?',restart_ok:'Bridge restarted!',logs_cleared:'Logs cleared.',
prof_save_err:'Select or create a profile before saving.',prof_saved:'Profile saved: ',prof_del_confirm:'Delete profile ',prof_new_err:'Enter a profile name.',prof_created:'Profile created: ',save_err:'Save error'
}};
function T(k){return (_i18n[_lang]||_i18n.fr)[k]||k;}
function applyLang(l){_lang=l;document.querySelectorAll('[data-i18n]').forEach(el=>{const k=el.getAttribute('data-i18n');const t=T(k);if(el.tagName==='INPUT')el.placeholder=t;else if(el.classList.contains('tip'))el.textContent=t;else el.textContent=t;});}
function fmtUp(s){const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sc=s%60;return(h?h+'h ':'')+(m+'m ')+(sc+'s');}
async function pollConv(){try{const r=await fetch('/api/transcript?from='+cLen);const d=await r.json();if(d.lines.length){const el=$('conv');d.lines.forEach(l=>{const m=l.match(/^\[(\d{2}:\d{2}:\d{2})\] (David|Claudius): (.+)$/);if(!m)return;const div=document.createElement('div');div.className=m[2]==='David'?'msg-david':'msg-claudius';const ts=document.createElement('span');ts.className='ts';ts.textContent=m[1];const nm=document.createElement('span');nm.className='nm';nm.textContent=m[2];div.appendChild(ts);div.appendChild(nm);div.appendChild(document.createTextNode(' '+m[3]));el.appendChild(div);});el.scrollTop=el.scrollHeight;cLen=d.total;$('conv-count').textContent=d.total+' msgs';}}catch(e){}}
async function pollLogs(){try{const r=await fetch('/api/logs?n=60');const d=await r.json();const h=d.lines.join('\n');if(h!==lHash){lHash=h;const el=$('logs');el.innerHTML=d.lines.map(l=>{let c='';if(l.includes('ERR'))c='log-err';else if(l.includes('LLM:'))c='log-llm';else if(l.includes('MOTOR'))c='log-motor';else if(l.includes('VOICE'))c='log-voice';else if(l.includes('SFX'))c='log-sfx';else if(l.includes('TIMER')||l.includes('UTIL'))c='log-timer';return'<div class="'+c+'">'+l.replace(/</g,'&lt;')+'</div>';}).join('');if($('log-auto').checked)el.scrollTop=el.scrollHeight;}}catch(e){}}
async function pollStats(){try{const r=await fetch('/api/stats');const d=await r.json();$('st-uptime').textContent=fmtUp(d.uptime);const p=$('st-presence');p.textContent=d.presence==='PRESENT'?'ICI':'ABSENT';p.style.color=d.presence==='PRESENT'?'var(--green)':'var(--dim)';$('st-exchanges').textContent=d.exchanges;$('st-memories').textContent=d.memories;const b=$('st-bridge');b.textContent=d.bridge_alive?'ON':'OFF';b.style.color=d.bridge_alive?'var(--green)':'var(--red)';const v=$('st-voice');v.textContent=d.voice_alive?'ON':'OFF';v.style.color=d.voice_alive?'var(--green)':'var(--red)';$('st-hb').textContent=d.voice_hb_age>=0?'('+d.voice_hb_age+'s)':'';$('st-status').textContent='live';$('st-status').style.color='var(--green)';}catch(e){$('st-status').textContent='offline';$('st-status').style.color='var(--red)';}}
async function sendCmd(){const pfx=$('cmd-prefix').value;const inp=$('cmd-input');let cmd=inp.value.trim();if(!cmd&&pfx==='VOICE:')return;if(pfx==='VOICE:')cmd='VOICE:'+cmd;else if(pfx)cmd=pfx;try{await fetch('/api/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cmd})});inp.value='';}catch(e){}}
async function restartBridge(){if(!confirm('Restart Bridge + Voice ?'))return;try{const r=await fetch('/api/restart',{method:'POST'});const d=await r.json();alert(d.ok?'Bridge relance !':'Erreur');}catch(e){alert('Erreur');}}
async function clearLogs(){try{await fetch('/api/logs/clear',{method:'POST'});lHash='';$('logs').innerHTML='<div style="color:var(--dim);font-style:italic">Logs effaces.</div>';}catch(e){}}
$('cmd-input').addEventListener('keydown',e=>{if(e.key==='Enter')sendCmd();});
function toggleSettings(){const o=$('settings-overlay');o.style.display=o.style.display==='flex'?'none':'flex';}
$('set-vol').oninput=function(){$('set-vol-val').textContent=this.value+'%';};
$('set-mic').oninput=function(){$('set-mic-val').textContent=this.value;};
$('set-tts').oninput=function(){$('set-tts-val').textContent=(this.value/100).toFixed(1)+'x';};
$('set-tokens').oninput=function(){$('set-tokens-val').textContent=this.value;};
$('set-timeout').oninput=function(){$('set-timeout-val').textContent=this.value+'s';};
$('set-temp').oninput=function(){$('set-temp-val').textContent=(this.value/100).toFixed(1);};
$('set-hist').oninput=function(){$('set-hist-val').textContent=this.value;};
$('set-pcool').oninput=function(){$('set-pcool-val').textContent=this.value+'s';};
$('set-presence').onchange=function(){$('set-presence-bg').style.background=this.checked?'var(--green)':'#555';$('set-presence-dot').style.left=this.checked?'20px':'2px';};
async function loadSettings(){try{const r=await fetch('/api/settings');const s=await r.json();
$('set-vol').value=Math.round((s.sfx_volume||0.3)*100);$('set-vol-val').textContent=$('set-vol').value+'%';
$('set-mic').value=s.mic_threshold||500;$('set-mic-val').textContent=$('set-mic').value;
$('set-tts').value=Math.round((s.tts_speed||1.0)*100);$('set-tts-val').textContent=(s.tts_speed||1.0).toFixed(1)+'x';
$('set-whisper').value=s.whisper_model||'small';$('set-wake').value=s.wake_word||'claudius';
$('set-vprov').value=s.voice_provider||'deepseek';$('set-vmodel').value=s.voice_model||'deepseek-v4-flash';$('set-vkey').value='';
$('set-sprov').value=s.snap_provider||'anthropic';$('set-smodel').value=s.snap_model||'claude-haiku-4-5-20251001';$('set-skey').value='';
$('set-tokens').value=s.max_tokens||500;$('set-tokens-val').textContent=s.max_tokens||500;
$('set-timeout').value=s.llm_timeout||25;$('set-timeout-val').textContent=(s.llm_timeout||25)+'s';
$('set-temp').value=Math.round((s.temperature||0.7)*100);$('set-temp-val').textContent=(s.temperature||0.7).toFixed(1);
$('set-hist').value=s.history_size||6;$('set-hist-val').textContent=s.history_size||6;
$('set-presence').checked=s.presence_enabled!==false;$('set-presence-bg').style.background=$('set-presence').checked?'var(--green)':'#555';$('set-presence-dot').style.left=$('set-presence').checked?'20px':'2px';
$('set-pcool').value=s.presence_cooldown||30;$('set-pcool-val').textContent=(s.presence_cooldown||30)+'s';
$('set-theme').value=s.theme||'dark';applyTheme(s.theme||'dark');}catch(e){}}
async function saveSettings(){const s={sfx_volume:$('set-vol').value/100,mic_threshold:parseInt($('set-mic').value),tts_speed:$('set-tts').value/100,whisper_model:$('set-whisper').value,wake_word:$('set-wake').value,voice_provider:$('set-vprov').value.trim(),voice_model:$('set-vmodel').value.trim(),voice_api_key:$('set-vkey').value.trim(),snap_provider:$('set-sprov').value.trim(),snap_model:$('set-smodel').value.trim(),snap_api_key:$('set-skey').value.trim(),max_tokens:parseInt($('set-tokens').value),llm_timeout:parseInt($('set-timeout').value),temperature:$('set-temp').value/100,history_size:parseInt($('set-hist').value),presence_enabled:$('set-presence').checked,presence_cooldown:parseInt($('set-pcool').value),theme:$('set-theme').value};
try{await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(s)});applyTheme(s.theme);$('set-vkey').value='';$('set-skey').value='';toggleSettings();}catch(e){alert('Erreur sauvegarde');}}
function applyTheme(t){const r=document.documentElement.style;const themes={dark:{bg:'#080a0f',panel:'#0c1018',border:'#1a2233',text:'#c9d1d9',dim:'#4a5568',logs:'#8899aa'},light:{bg:'#f0f2f5',panel:'#ffffff',border:'#d0d5dd',text:'#1a1a1a',dim:'#888',logs:'#555'},midnight:{bg:'#0a0e1a',panel:'#101630',border:'#1e2d5a',text:'#b8c4e0',dim:'#4a5580',logs:'#7788bb'},matrix:{bg:'#000a00',panel:'#001200',border:'#003300',text:'#00ff41',dim:'#006600',logs:'#009900'},ember:{bg:'#120808',panel:'#1a0c0c',border:'#3a1515',text:'#e0c0b0',dim:'#6a4a3a',logs:'#aa7766'},cyberpunk:{bg:'#0a0012',panel:'#120020',border:'#2a1050',text:'#e0d0ff',dim:'#6644aa',logs:'#9977dd'},ocean:{bg:'#041520',panel:'#082030',border:'#104060',text:'#b0d8e8',dim:'#407090',logs:'#6099bb'},nord:{bg:'#2e3440',panel:'#3b4252',border:'#4c566a',text:'#eceff4',dim:'#7b88a1',logs:'#a3b1c8'},solar:{bg:'#002b36',panel:'#073642',border:'#094959',text:'#93a1a1',dim:'#586e75',logs:'#839496'},synthwave:{bg:'#13001a',panel:'#1a0025',border:'#3d0066',text:'#ff71ce',dim:'#7b2d8e',logs:'#b967ff'}};const c=themes[t]||themes.dark;r.setProperty('--bg',c.bg);r.setProperty('--panel',c.panel);r.setProperty('--border',c.border);r.setProperty('--text',c.text);r.setProperty('--dim',c.dim);$('logs').style.color=c.logs;}
function getCurrentSettings(){return{sfx_volume:$('set-vol').value/100,mic_threshold:parseInt($('set-mic').value),tts_speed:$('set-tts').value/100,whisper_model:$('set-whisper').value,wake_word:$('set-wake').value,voice_provider:$('set-vprov').value.trim(),voice_model:$('set-vmodel').value.trim(),snap_provider:$('set-sprov').value.trim(),snap_model:$('set-smodel').value.trim(),max_tokens:parseInt($('set-tokens').value),llm_timeout:parseInt($('set-timeout').value),temperature:$('set-temp').value/100,history_size:parseInt($('set-hist').value),presence_enabled:$('set-presence').checked,presence_cooldown:parseInt($('set-pcool').value),theme:$('set-theme').value};}
function applySettingsToUI(s){$('set-vol').value=Math.round((s.sfx_volume||0.3)*100);$('set-vol-val').textContent=$('set-vol').value+'%';$('set-mic').value=s.mic_threshold||500;$('set-mic-val').textContent=$('set-mic').value;$('set-tts').value=Math.round((s.tts_speed||1.0)*100);$('set-tts-val').textContent=(s.tts_speed||1.0).toFixed(1)+'x';$('set-whisper').value=s.whisper_model||'small';$('set-wake').value=s.wake_word||'claudius';$('set-vprov').value=s.voice_provider||'deepseek';$('set-vmodel').value=s.voice_model||'deepseek-v4-flash';$('set-sprov').value=s.snap_provider||'anthropic';$('set-smodel').value=s.snap_model||'claude-haiku-4-5-20251001';$('set-tokens').value=s.max_tokens||500;$('set-tokens-val').textContent=s.max_tokens||500;$('set-timeout').value=s.llm_timeout||25;$('set-timeout-val').textContent=(s.llm_timeout||25)+'s';$('set-temp').value=Math.round((s.temperature||0.7)*100);$('set-temp-val').textContent=(s.temperature||0.7).toFixed(1);$('set-hist').value=s.history_size||6;$('set-hist-val').textContent=s.history_size||6;$('set-presence').checked=s.presence_enabled!==false;$('set-presence-bg').style.background=$('set-presence').checked?'var(--green)':'#555';$('set-presence-dot').style.left=$('set-presence').checked?'20px':'2px';$('set-pcool').value=s.presence_cooldown||30;$('set-pcool-val').textContent=(s.presence_cooldown||30)+'s';$('set-theme').value=s.theme||'dark';applyTheme(s.theme||'dark');}
async function loadProfiles(){try{const r=await fetch('/api/profiles');const p=await r.json();const sel=$('set-profile');const cur=sel.value;sel.innerHTML='<option value="_default">Defaut</option>';Object.keys(p).forEach(n=>{const o=document.createElement('option');o.value=n;o.textContent=n;sel.appendChild(o);});if(cur)sel.value=cur;}catch(e){}}
async function saveProfile(){const name=$('set-profile').value;if(name==='_default'){alert('Selectionnez ou creez un profil avant de sauver.');return;}const s=getCurrentSettings();const r=await fetch('/api/profiles',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,settings:s})});const d=await r.json();if(d.ok){await loadProfiles();alert('Profil sauve: '+name);}}
async function loadProfile(){const name=$('set-profile').value;if(name==='_default'){loadSettings();return;}try{const r=await fetch('/api/profiles');const p=await r.json();if(p[name])applySettingsToUI(p[name]);}catch(e){}}
async function deleteProfile(){const name=$('set-profile').value;if(name==='_default')return;if(!confirm('Supprimer le profil '+name+' ?'))return;await fetch('/api/profiles',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,delete:true})});await loadProfiles();}
async function createProfile(){const name=$('new-profile-name').value.trim();if(!name){alert('Entrez un nom de profil.');return;}const s=getCurrentSettings();const r=await fetch('/api/profiles',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,settings:s})});const d=await r.json();if(d.ok){$('new-profile-name').value='';await loadProfiles();$('set-profile').value=name;alert('Profil cree: '+name);}}
loadSettings();loadProfiles();setInterval(pollConv,800);setInterval(pollLogs,1000);setInterval(pollStats,2000);pollConv();pollLogs();pollStats();
let _winSaveTimer=null;function saveWindowSize(){if(_winSaveTimer)clearTimeout(_winSaveTimer);_winSaveTimer=setTimeout(()=>{fetch('/api/window',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({w:window.outerWidth,h:window.outerHeight,x:window.screenX,y:window.screenY})}).catch(()=>{});},500);}
window.addEventListener('resize',saveWindowSize);window.addEventListener('beforeunload',()=>{navigator.sendBeacon('/api/window',new Blob([JSON.stringify({w:window.outerWidth,h:window.outerHeight,x:window.screenX,y:window.screenY})],{type:'application/json'}));});
</script></body></html>"""

def _open_app_window():
    """Ouvre le dashboard dans une fenetre app standalone (Edge ou Chrome --app mode)."""
    import shutil
    url = "http://localhost:5005"
    # Charger la taille de fenetre sauvegardee
    win_file = os.path.join(_DATA_DIR, "claudius_window.json")
    w, h, x, y = 1280, 800, None, None
    try:
        with open(win_file, "r") as f:
            wc = json.load(f)
            w, h = wc.get("w", 1280), wc.get("h", 800)
            x, y = wc.get("x"), wc.get("y")
    except Exception: pass
    args = [f"--app={url}", "--new-window", f"--window-size={w},{h}"]
    if x is not None and y is not None:
        args.append(f"--window-position={x},{y}")
    edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    chrome = shutil.which("chrome") or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    for browser in [edge, chrome]:
        if os.path.exists(browser):
            try:
                subprocess.Popen([browser] + args, creationflags=subprocess.CREATE_NO_WINDOW)
                return
            except Exception: continue
    webbrowser.open(url)

if __name__ == "__main__":
    # Verifier si le port 5005 est deja pris (dashboard deja lance)
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    port_taken = sock.connect_ex(("127.0.0.1", 5005)) == 0
    sock.close()
    if port_taken:
        # Dashboard deja actif — ouvrir juste la fenetre et quitter
        if "--no-window" not in sys.argv:
            _open_app_window()
        sys.exit(0)
    print("[DASHBOARD] http://localhost:5005")
    threading.Thread(target=_auto_restart_thread, daemon=True).start()
    if "--no-window" not in sys.argv:
        threading.Timer(2.0, _open_app_window).start()
    app.run(host="0.0.0.0", port=5005, debug=False, use_reloader=False)
