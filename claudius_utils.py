"""
claudius_utils.py — Utilitaires pour Claudius
Commandes utiles (heure, date, météo, timer, rappel, volume, musique, calculs,
conversions, veille, répète, état système), log, accentuation FR.
Tout est détecté LOCALEMENT avant l'appel LLM : zéro latence API.
"""
import os, re, time, json, threading, urllib.request
import ctypes
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

def cancel_timer_by_name(name):
    """Annule les timers dont le label contient `name`. Retourne le nombre."""
    name = name.lower().strip()
    with _timer_lock:
        hits = [t for t in _timers if name in t["label"].lower()]
        for t in hits:
            t["cancel"].set()
        _timers[:] = [t for t in _timers if name not in t["label"].lower()]
    return len(hits)

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

# --- Touches média Windows (contrôle le lecteur actif : navigateur, Spotify…) ---
_VK_MEDIA = {"next": 0xB0, "prev": 0xB1, "stop": 0xB2, "playpause": 0xB3}

def _media_key(action):
    vk = _VK_MEDIA[action]
    try:
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP
        return True
    except Exception as e:
        log(f"ERR media key: {e}", tag="UTIL")
        return False

# --- Nombres en lettres -> chiffres (Whisper écrit parfois « deux plus deux ») ---
_WORD_NUMS = {
    "zéro": 0, "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4,
    "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11,
    "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
    "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60,
    "cent": 100, "mille": 1000,
}
# (?<!pour ) : ne pas transformer « pour cent » en « pour 100 » (pourcentages)
_WORD_NUMS_RE = re.compile(r'(?<!pour )\b(' + '|'.join(_WORD_NUMS) + r')\b', re.IGNORECASE)

def _words_to_digits(t):
    return _WORD_NUMS_RE.sub(lambda m: str(_WORD_NUMS[m.group(0).lower()]), t)

def _fnum(s):
    return float(s.replace(",", "."))

def _say_num(v):
    """Formate un nombre pour le TTS FR : entier si rond, sinon « virgule »."""
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", " virgule ")

# --- Calculs ---
_CALC_TRIGGER = re.compile(r'combien\s+f(?:ont|ait)|calcule|[çc]a\s+fait\s+combien', re.IGNORECASE)
_CALC_PCT = re.compile(r'(\d+(?:[.,]\d+)?)\s*(?:%|pour\s*cent)\s+de\s+(\d+(?:[.,]\d+)?)', re.IGNORECASE)
_CALC_EXPR = re.compile(
    r'(-?\d+(?:[.,]\d+)?)\s*(plus|moins|fois|x|\*|\+|-|multipli[eé]e?s?\s+par|divis[eé]e?s?\s+par|sur|/)\s*'
    r'(-?\d+(?:[.,]\d+)?)', re.IGNORECASE)

def _try_calc(text):
    t = _words_to_digits(text)
    m = _CALC_PCT.search(t)
    if m:
        a, b = _fnum(m.group(1)), _fnum(m.group(2))
        return f"{_say_num(a)} pour cent de {_say_num(b)}, ça fait {_say_num(a * b / 100.0)}."
    m = _CALC_EXPR.search(t)
    if not m:
        return None
    # Sans déclencheur explicite (« combien font »), n'accepter que si la phrase
    # EST le calcul — sinon « il fait moins 5 dehors » deviendrait un calcul.
    if not _CALC_TRIGGER.search(t):
        rest = (t[:m.start()] + t[m.end():]).strip(" ?!.,")
        if rest:
            return None
    a, op, b = _fnum(m.group(1)), m.group(2).lower(), _fnum(m.group(3))
    if op in ("plus", "+"):
        r = a + b
    elif op in ("moins", "-"):
        r = a - b
    elif op in ("fois", "x", "*") or op.startswith("multipli"):
        r = a * b
    else:
        if b == 0:
            return "Division par zéro : même moi je ne peux pas."
        r = a / b
    return f"Ça fait {_say_num(r)}."

# --- Conversions d'unités ---
_CONVERSIONS = [
    (r"(?:degr[eé]s?\s+)?fahrenheit", r"(?:degr[eé]s?\s+)?celsius", lambda v: (v - 32) / 1.8, "degrés Celsius"),
    (r"(?:degr[eé]s?\s+)?celsius", r"(?:degr[eé]s?\s+)?fahrenheit", lambda v: v * 1.8 + 32, "degrés Fahrenheit"),
    (r"miles?", r"kilom[eè]tres?|km", lambda v: v * 1.609344, "kilomètres"),
    (r"kilom[eè]tres?|km", r"miles?", lambda v: v / 1.609344, "miles"),
    (r"pieds?", r"m[eè]tres?", lambda v: v * 0.3048, "mètres"),
    (r"m[eè]tres?", r"pieds?", lambda v: v / 0.3048, "pieds"),
    (r"pouces?", r"centim[eè]tres?|cm", lambda v: v * 2.54, "centimètres"),
    (r"centim[eè]tres?|cm", r"pouces?", lambda v: v / 2.54, "pouces"),
    (r"livres?", r"kilo(?:gramme)?s?|kg", lambda v: v * 0.45359237, "kilos"),
    (r"kilo(?:gramme)?s?|kg", r"livres?", lambda v: v / 0.45359237, "livres"),
]

def _try_convert(text):
    t = _words_to_digits(text)
    for src, dst, fn, name in _CONVERSIONS:
        m = re.search(rf'(-?\d+(?:[.,]\d+)?)\s*(?:{src})\b\s+en\s+(?:{dst})\b', t, re.IGNORECASE)
        if m:
            v = _fnum(m.group(1))
            return f"Ça fait {_say_num(fn(v))} {name}."
    return None

# --- Détection d'intention ---
_TIMER_WORD = r'(?:timer|minuteur|minuterie)'
_MUSIC_WORD = r'(?:musique|piste|chanson|morceau|titre|zik)'

_INTENT_HEURE = re.compile(r'(?:quelle?\s+heure|heure\s+(?:est|qu)|l\'heure|il\s+est\s+quelle|donne.*heure|dis.*heure)', re.IGNORECASE)
_INTENT_DATE = re.compile(r'(?:quel\s+jour|quelle\s+date|on\s+est\s+(?:le\s+)?(?:quel|combien)|date\s+(?:d\')?aujourd|jour\s+(?:on\s+est|sommes))', re.IGNORECASE)
_INTENT_METEO = re.compile(r'(?:meteo|m[eé]t[eé]o|quel\s+temps|temps\s+(?:fait|qu)|il\s+fait\s+(?:combien|chaud|froid|beau)|temperature|dehors|pleut|pluie|neige)', re.IGNORECASE)
_INTENT_TIMER = re.compile(r'(?:met[s]?[\s-]+(?:(?:moi\s+)?(?:un\s+)?)?' + _TIMER_WORD +
                           r'|lance[\s-]+(?:moi\s+)?(?:une?\s+)?' + _TIMER_WORD +
                           r'|' + _TIMER_WORD + r'\s+(?:de\s+)?\d'
                           r'|' + _TIMER_WORD + r'\s+\S{1,25}\s+(?:de\s+)?\d)', re.IGNORECASE)
_INTENT_RAPPEL = re.compile(r'(?:rappel(?:le)?[\s-]?moi|n\'oublie\s+pas|pense\s+[aà]\s+me\s+rappeler)', re.IGNORECASE)
_INTENT_TIMERS_STATUS = re.compile(r'(?:combien\s+(?:de\s+)?' + _TIMER_WORD + r'|' + _TIMER_WORD + r's?\s+(?:en\s+cours|actif)|temps\s+restant|reste\s+combien\s+de\s+temps|combien\s+de\s+temps\s+(?:il\s+)?reste)', re.IGNORECASE)
_INTENT_CANCEL_TIMER = re.compile(r'(?:annul(?:e|er?)\s+(?:les?\s+|la\s+)?(?:' + _TIMER_WORD + r'|rappel)|stop(?:pe)?\s+(?:les?\s+|la\s+)?' + _TIMER_WORD + r')', re.IGNORECASE)
_INTENT_CANCEL_NAMED = re.compile(r'annul(?:e|er?)\s+(?:le\s+|la\s+)?' + _TIMER_WORD + r'\s+(?:de\s+|des\s+|du\s+|pour\s+)?([a-zà-ÿ][a-zà-ÿ\' -]{1,20})', re.IGNORECASE)

# Volume de la voix
_INTENT_VOL_MAX = re.compile(r'volume\s+(?:au\s+)?(?:max(?:imum)?|[aà]\s+fond)', re.IGNORECASE)
_INTENT_VOL_MIN = re.compile(r'volume\s+(?:au\s+)?min(?:imum)?', re.IGNORECASE)
_INTENT_VOL_NORMAL = re.compile(r'volume\s+normal', re.IGNORECASE)
_INTENT_VOL_SET = re.compile(r'volume\s+(?:[aà]\s+)?(\d{1,3})\s*(?:%|pour\s*cent)?', re.IGNORECASE)
_INTENT_VOL_DOWN = re.compile(r'(?:parle\s+)?moins\s+fort|baisse\s+(?:un\s+peu\s+)?(?:le\s+)?(?:son|volume)|parle\s+(?:plus\s+bas|(?:plus\s+)?doucement)|trop\s+fort', re.IGNORECASE)
_INTENT_VOL_UP = re.compile(r'(?:parle\s+)?plus\s+fort|monte\s+(?:un\s+peu\s+)?(?:le\s+)?(?:son|volume)|je\s+(?:ne\s+)?t\'entends\s+(?:pas|mal)', re.IGNORECASE)

# Répète / état système / veille
_INTENT_REPEAT = re.compile(r'r[eé]p[eèé]t(?:e|er)|redis\b|tu\s+as\s+dit\s+quoi|qu(?:\'|\s)?est[\s-]?ce\s+que\s+tu\s+(?:as\s+dit|viens\s+de\s+dire)|j(?:\'|e\s+n\'?)ai\s+pas\s+(?:entendu|compris|capt[eé])', re.IGNORECASE)
_INTENT_SYSLOAD = re.compile(r'comment\s+(?:tu\s+te\s+sens|te\s+sens[\s-]?tu)|[eé]tat\s+(?:du\s+)?syst[eè]me|charge\s+syst[eè]me|ta\s+consommation|tes\s+ressources', re.IGNORECASE)
_INTENT_SLEEP = re.compile(r'\bdors\b|va\s+dormir|endors[\s-]?toi|mode\s+(?:nuit|silence|veille)|passe\s+en\s+veille|mets[\s-]?toi\s+en\s+veille|tais[\s-]?toi|bonne\s+nuit|laisse[\s-]?moi\s+tranquille|fiche[\s-]?moi\s+la\s+paix', re.IGNORECASE)

# Musique (touches média — marche car les navigateurs sont dans audio_ignore)
_INTENT_MUSIC_NEXT = re.compile(_MUSIC_WORD + r'\s+(?:suivante?|d\'?apr[eè]s)|(?:change|saute)\s+(?:de\s+|cette\s+)?' + _MUSIC_WORD, re.IGNORECASE)
_INTENT_MUSIC_PREV = re.compile(_MUSIC_WORD + r'\s+(?:pr[eé]c[eé]dente?|d\'?avant)', re.IGNORECASE)
_INTENT_MUSIC_PAUSE = re.compile(r'(?:pause|coupe|arr[eê]te|stoppe?)\s+(?:la\s+|le\s+|cette?\s+)?' + _MUSIC_WORD + r'|mets?\s+(?:la\s+musique\s+)?en\s+pause', re.IGNORECASE)
_INTENT_MUSIC_PLAY = re.compile(r'(?:remets|reprends|relance|joue)\s+(?:la\s+|le\s+|une?\s+)?' + _MUSIC_WORD, re.IGNORECASE)

_LABEL_STOPWORDS = {"de", "des", "du", "pour", "dans", "en", "le", "la", "les",
                    "un", "une", "et", "te", "me", "moi"}

def extract_timer_label(text):
    """« minuteur pâtes 8 minutes » -> « pâtes ». None si timer anonyme."""
    t = text.lower()
    m = re.search(_TIMER_WORD + r'\s+(?:pour\s+(?:les?\s+|la\s+)?)?([a-zà-ÿ][a-zà-ÿ\' -]{1,20}?)\s+(?:de\s+)?\d', t)
    if not m:
        return None
    words = [w for w in m.group(1).strip(" '-").split() if w not in _LABEL_STOPWORDS]
    return " ".join(words) if words else None

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

def _handle_volume(t, bridge):
    """Commandes volume. Retourne réponse TTS ou None. La réponse elle-même
    est jouée au NOUVEAU volume : feedback immédiat."""
    get_v, set_v = bridge.get("get_volume"), bridge.get("set_volume")
    if not set_v:
        return None

    def apply(gain):
        gain = max(0.2, min(2.0, gain))
        set_v(gain)
        return gain

    if _INTENT_VOL_MAX.search(t):
        apply(2.0)
        return "Volume au maximum !"
    if _INTENT_VOL_MIN.search(t):
        apply(0.2)
        return "Volume au minimum."
    if _INTENT_VOL_NORMAL.search(t):
        apply(1.0)
        return "Volume normal, cent pour cent."
    m = _INTENT_VOL_SET.search(t)
    if m:
        n = max(20, min(200, int(m.group(1))))
        apply(n / 100.0)
        return f"Volume à {n} pour cent."
    if _INTENT_VOL_DOWN.search(t):
        cur = get_v() if get_v else 1.0
        if cur <= 0.21:
            return "Je suis déjà au minimum."
        g = apply(cur * 0.7)
        return f"D'accord, je parle moins fort. Volume à {int(round(g * 100))} pour cent."
    if _INTENT_VOL_UP.search(t):
        cur = get_v() if get_v else 1.0
        if cur >= 1.99:
            return "Je suis déjà à fond !"
        g = apply(cur / 0.7)
        return f"D'accord, je parle plus fort ! Volume à {int(round(g * 100))} pour cent."
    return None

def check_utility(text, on_alarm_callback=None, bridge=None):
    """Vérifie commande utilitaire LOCALE (zéro appel LLM).
    Retourne réponse TTS ou None. `bridge` = leviers fournis par KinectBridge :
    last_reply() / get_volume() / set_volume(g) / sysload() / sleep()."""
    t = text.lower().strip()
    b = bridge or {}

    # Calculs & conversions — AVANT la météo : « ça fait combien » matche les deux
    reply = _try_calc(t)
    if reply:
        log(f"Util: calc -> {reply[:60]}", tag="UTIL")
        return reply
    reply = _try_convert(t)
    if reply:
        log(f"Util: convert -> {reply[:60]}", tag="UTIL")
        return reply

    reply = _handle_volume(t, b)
    if reply:
        log(f"Util: volume -> {reply[:60]}", tag="UTIL")
        return reply

    if _INTENT_REPEAT.search(t) and "last_reply" in b:
        last = b["last_reply"]()
        log("Util: repeat", tag="UTIL")
        return last if last else "Je n'ai encore rien dit."

    if _INTENT_SYSLOAD.search(t) and "sysload" in b:
        log("Util: sysload", tag="UTIL")
        return b["sysload"]()

    if _INTENT_MUSIC_NEXT.search(t):
        log("Util: music next", tag="UTIL")
        return "Piste suivante !" if _media_key("next") else "Je n'arrive pas à envoyer la commande média."
    if _INTENT_MUSIC_PREV.search(t):
        log("Util: music prev", tag="UTIL")
        return "Piste précédente." if _media_key("prev") else "Je n'arrive pas à envoyer la commande média."
    if _INTENT_MUSIC_PAUSE.search(t):
        log("Util: music pause", tag="UTIL")
        return "Pause !" if _media_key("playpause") else "Je n'arrive pas à envoyer la commande média."
    if _INTENT_MUSIC_PLAY.search(t):
        log("Util: music play", tag="UTIL")
        return "C'est reparti !" if _media_key("playpause") else "Je n'arrive pas à envoyer la commande média."

    if _INTENT_SLEEP.search(t) and "sleep" in b:
        log("Util: sleep", tag="UTIL")
        b["sleep"]()
        return "D'accord, je passe en veille. Dis, Claudius réveille-toi, quand tu auras besoin de moi."

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
    m = _INTENT_CANCEL_NAMED.search(t)
    if m:
        name = " ".join(w for w in m.group(1).strip().split() if w not in _LABEL_STOPWORDS)
        if name:
            count = cancel_timer_by_name(name)
            log(f"Util: cancel '{name}' -> {count}", tag="UTIL")
            if count:
                return f"J'ai annulé le minuteur {name}."
            return f"Je n'ai pas de minuteur {name} en cours."
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
            label = extract_timer_label(text)
            if label:
                start_timer(duration, message=f"minuteur {label}", on_alarm=on_alarm_callback)
                return f"Minuteur {label}, {format_duration(duration)}, c'est parti !"
            start_timer(duration, on_alarm=on_alarm_callback)
            return f"Timer de {format_duration(duration)}, c'est parti !"
        else:
            return None
    return None
