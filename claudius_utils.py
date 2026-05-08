"""
claudius_utils.py — Utilitaires pour Claudius
Commandes utiles (heure, date, météo, timer, rappel), log, accentuation FR.
"""
import os, re, time, json, threading, urllib.request
import locale

try:
    locale.setlocale(locale.LC_TIME, "fr_FR.UTF-8")
except Exception:
    try:
        locale.setlocale(locale.LC_TIME, "French_France.1252")
    except Exception:
        pass

# Coordonnées Lavelanet
_METEO_LAT, _METEO_LON = 42.94, 1.85
_METEO_URL = (
    f"https://api.open-meteo.com/v1/forecast?"
    f"latitude={_METEO_LAT}&longitude={_METEO_LON}"
    f"&current=temperature_2m,weathercode,windspeed_10m,relative_humidity_2m"
    f"&timezone=Europe/Paris"
)

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

# --- Re-accentuation FR ---
_ACCENT_MAP = {
    "tete": "tête", "tres": "très", "ete": "été", "pere": "père",
    "mere": "mère", "frere": "frère", "fete": "fête", "bete": "bête",
    "pret": "prêt", "foret": "forêt", "fenetre": "fenêtre",
    "interet": "intérêt", "desole": "désolé", "idee": "idée",
    "interessant": "intéressant", "prefere": "préféré",
    "probleme": "problème", "systeme": "système", "theme": "thème",
    "modele": "modèle", "premiere": "première", "derniere": "dernière",
    "lumiere": "lumière", "maniere": "manière", "matiere": "matière",
    "different": "différent", "experience": "expérience",
    "necessaire": "nécessaire", "reponse": "réponse", "energie": "énergie",
    "securite": "sécurité", "deja": "déjà", "voila": "voilà",
    "la": "là", "ou": "où", "a": "à", "etait": "était",
    "etaient": "étaient", "etes": "êtes", "etat": "état",
    "ecran": "écran", "ecouter": "écouter", "ecoute": "écoute",
    "regle": "règle", "reveil": "réveil", "eleve": "élève",
    "celebre": "célèbre", "colere": "colère", "derriere": "derrière",
    "numero": "numéro", "cafe": "café", "resume": "résumé",
    "cote": "côté", "generale": "générale", "general": "général",
    "generalement": "généralement", "completement": "complètement",
    "evidemment": "évidemment", "sincerement": "sincèrement",
    "developpement": "développement", "evenement": "événement",
}

_ACCENT_RE = re.compile(r"^([A-Za-zÀ-ÿ'-]+)(.*)")
_AVOIR_SUBJECTS = frozenset(("il", "elle", "on", "qui", "david", "claudius", "ca", "cela", "ça"))

def reaccentuate(text):
    """Remet les accents FR avant TTS."""
    words = text.split()
    out = []
    for idx, w in enumerate(words):
        m = _ACCENT_RE.match(w)
        if not m:
            out.append(w)
            continue
        core, punct = m.group(1), m.group(2)
        lower = core.lower()
        if lower == "a":
            prev = words[idx-1].lower().rstrip(".,!?;:") if idx > 0 else ""
            if prev in _AVOIR_SUBJECTS:
                out.append(w)
                continue
        if lower in _ACCENT_MAP:
            repl = _ACCENT_MAP[lower]
            if core[0].isupper():
                repl = repl[0].upper() + repl[1:]
            if core.isupper():
                repl = repl.upper()
            out.append(repl + punct)
        else:
            out.append(w)
    return " ".join(out)

# --- Log simple ---
_log_lock = threading.Lock()

def log(msg, log_file="kinect.log", tag=""):
    tag_str = f"[{tag}] " if tag else ""
    line = f"[{time.strftime('%H:%M:%S')}] {tag_str}{msg}"
    print(line, flush=True)
    with _log_lock:
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

# --- Commandes utilitaires ---
_timers = []
_timer_lock = threading.Lock()
_timer_counter = 0

def format_duration(seconds):
    h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    parts = []
    if h > 0: parts.append(f"{h} heure{'s' if h > 1 else ''}")
    if m > 0: parts.append(f"{m} minute{'s' if m > 1 else ''}")
    if s > 0 and h == 0: parts.append(f"{s} seconde{'s' if s > 1 else ''}")
    return " et ".join(parts) if parts else "0 secondes"

def parse_duration(text):
    t = text.lower()
    total, found = 0, False
    m = re.search(r'(\d+)\s*(?:heure|heures|h)\b', t)
    if m: total += int(m.group(1)) * 3600; found = True
    m = re.search(r'(\d+)\s*(?:minute|minutes|min)\b', t)
    if m: total += int(m.group(1)) * 60; found = True
    m = re.search(r'(\d+)\s*(?:seconde|secondes|sec)\b', t)
    if m: total += int(m.group(1)); found = True
    if not found:
        m = re.search(r'(\d+)', t)
        if m:
            n = int(m.group(1))
            if n > 0:
                total = n * 60
                found = True
    return total if found else None

def start_timer(seconds, message=None, on_alarm=None):
    """Lance un timer. on_alarm(text) est appelé quand le timer sonne."""
    global _timer_counter
    cancel = threading.Event()
    with _timer_lock:
        _timer_counter += 1
        tid = _timer_counter
    label = message or f"timer de {format_duration(seconds)}"
    with _timer_lock:
        _timers.append({"id": tid, "label": label, "end": time.time() + seconds, "cancel": cancel})

    def _run():
        cancelled = cancel.wait(timeout=seconds)
        with _timer_lock:
            _timers[:] = [t for t in _timers if t["id"] != tid]
        if cancelled:
            return
        log(f"TIMER: #{tid} termine — {label}", tag="TIMER")
        if on_alarm:
            on_alarm(message or None)

    threading.Thread(target=_run, daemon=True).start()
    return tid

def cancel_all_timers():
    with _timer_lock:
        for t in _timers:
            t["cancel"].set()
        count = len(_timers)
        _timers.clear()
    return count

def get_timers_status():
    with _timer_lock:
        if not _timers:
            return None
        now = time.time()
        parts = []
        for t in _timers:
            remaining = max(0, t["end"] - now)
            parts.append(f"{t['label']}, encore {format_duration(int(remaining))}")
        return "Timers en cours : " + ". ".join(parts) + "."

def fetch_meteo():
    try:
        req = urllib.request.Request(_METEO_URL, headers={"User-Agent": "Claudius/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        cur = data["current"]
        temp = cur["temperature_2m"]
        code = cur.get("weathercode", -1)
        wind = cur.get("windspeed_10m", 0)
        desc = _WMO_CODES.get(code, "conditions inconnues")
        parts = [f"Il fait {temp:.0f} degres", f"avec {desc}"]
        if wind > 20:
            parts.append(f"et du vent a {wind:.0f} kilometres heure")
        elif wind > 5:
            parts.append(f"avec un vent leger a {wind:.0f} kilometres heure")
        return ". ".join([", ".join(parts)])
    except Exception as e:
        log(f"ERR meteo: {e}", tag="METEO")
        return "Desole, je n'arrive pas a recuperer la meteo."

# --- Détection d'intention ---
_INTENT_HEURE = re.compile(r'(?:quelle?\s+heure|heure\s+(?:est|qu)|l\'heure|il\s+est\s+quelle|donne.*heure|dis.*heure)', re.IGNORECASE)
_INTENT_DATE = re.compile(r'(?:quel\s+jour|quelle\s+date|on\s+est\s+(?:le\s+)?(?:quel|combien)|date\s+(?:d\')?aujourd|jour\s+(?:on\s+est|sommes))', re.IGNORECASE)
_INTENT_METEO = re.compile(r'(?:meteo|m[eé]t[eé]o|quel\s+temps|temps\s+(?:fait|qu)|il\s+fait\s+(?:combien|chaud|froid|beau)|temperature|dehors|pleut|pluie|neige)', re.IGNORECASE)
_INTENT_TIMER = re.compile(r'(?:met[s]?[\s-]+(?:(?:moi\s+)?(?:un\s+)?)?(?:timer|minuteur)|lance[\s-]+(?:moi\s+)?(?:un\s+)?(?:timer|minuteur)|timer\s+(?:de\s+)?\d|minuteur\s+(?:de\s+)?\d)', re.IGNORECASE)
_INTENT_RAPPEL = re.compile(r'(?:rappel(?:le)?[\s-]?moi|n\'oublie\s+pas|pense\s+[aà]\s+me\s+rappeler)', re.IGNORECASE)
_INTENT_TIMERS_STATUS = re.compile(r'(?:combien\s+(?:de\s+)?(?:timer|minuteur)|timer[s]?\s+(?:en\s+cours|actif)|temps\s+restant)', re.IGNORECASE)
_INTENT_CANCEL_TIMER = re.compile(r'(?:annul(?:e|er?)\s+(?:le\s+)?(?:timer|minuteur|rappel)|stop(?:pe)?\s+(?:le\s+)?(?:timer|minuteur))', re.IGNORECASE)

def extract_rappel_message(text):
    t = text.lower()
    m = re.search(r'(?:rappel(?:le)?[\s-]?moi|fais[\s-]?moi\s+penser)\s+(?:de\s+|que\s+|d\'|qu\')?(.+?)(?:\s+dans\s+|\s+en\s+|\s+d\'ici\s+)', t)
    if m:
        return m.group(1).strip()
    m = re.search(r'(?:rappel(?:le)?[\s-]?moi|fais[\s-]?moi\s+penser)\s+(?:de\s+|que\s+|d\'|qu\')?(.+)', t)
    if m:
        msg = m.group(1).strip()
        msg = re.sub(r'\s+dans\s+\d+.*$', '', msg)
        msg = re.sub(r'\s+en\s+\d+.*$', '', msg)
        return msg.strip() if msg.strip() else None
    return None

def check_utility(text, on_alarm_callback=None):
    """Vérifie commande utilitaire. Retourne réponse TTS ou None."""
    t = text.lower().strip()
    if _INTENT_HEURE.search(t):
        now = time.strftime("%H heures %M")
        log(f"Util: heure -> {now}", tag="UTIL")
        return f"Il est {now}."
    if _INTENT_DATE.search(t):
        try:
            jour = time.strftime("%A %d %B %Y")
        except Exception:
            jour = time.strftime("%d/%m/%Y")
        log(f"Util: date -> {jour}", tag="UTIL")
        return f"On est le {jour}."
    if _INTENT_METEO.search(t):
        log("Util: meteo", tag="UTIL")
        return fetch_meteo()
    if _INTENT_CANCEL_TIMER.search(t):
        count = cancel_all_timers()
        return f"J'ai annule {count} timer{'s' if count > 1 else ''}." if count else "Aucun timer en cours."
    if _INTENT_TIMERS_STATUS.search(t):
        status = get_timers_status()
        return status or "Aucun timer en cours."
    if _INTENT_RAPPEL.search(t):
        duration = parse_duration(t)
        message = extract_rappel_message(text)
        if duration and message:
            start_timer(duration, message, on_alarm_callback)
            return f"C'est note, je te rappelle de {message} dans {format_duration(duration)}."
        elif duration:
            start_timer(duration, message="rappel", on_alarm=on_alarm_callback)
            return f"OK, rappel dans {format_duration(duration)}."
        else:
            return None
    if _INTENT_TIMER.search(t):
        duration = parse_duration(t)
        if duration:
            start_timer(duration, on_alarm=on_alarm_callback)
            return f"Timer de {format_duration(duration)}, c'est parti !"
        else:
            return None
    return None
