"""
KinectVoice.py - Reconnaissance vocale Claudius
faster-whisper GPU float16 / CPU int8 fallback
Bird UM1 device 1
--- v2: singleton, queue unique, anti-flood, filtre hallucination renforce ---
"""
import sounddevice as sd
import numpy as np
import time, os, re, threading, queue, sys

BIRD_DEVICE_ID  = 1
SAMPLE_RATE     = 16000
CHUNK_DURATION  = 0.1
CHUNK_SAMPLES   = int(SAMPLE_RATE * CHUNK_DURATION)

SILENCE_AFTER   = 1.5
MIN_DURATION    = 0.8
MAX_DURATION    = 8.0
FIXED_THRESHOLD = 800
MODEL_SIZE      = "small"

BASE_DIR        = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect"
CMD_FILE        = os.path.join(BASE_DIR, "cmd.txt")
LOG_FILE        = os.path.join(BASE_DIR, "kinect.log")
TRANSCRIPT_FILE = os.path.join(BASE_DIR, "transcript.txt")
TTS_LOCK_FILE   = os.path.join(BASE_DIR, "tts_speaking.lock")
SLEEP_FILE      = os.path.join(BASE_DIR, "claudius_sleep.lock")
PID_FILE        = os.path.join(BASE_DIR, "voice.pid")

# --- Singleton : tue les instances precedentes ---
def _enforce_singleton():
    my_pid = os.getpid()
    if os.path.exists(PID_FILE):
        try:
            old_pid = int(open(PID_FILE).read().strip())
            if old_pid != my_pid:
                import signal
                os.kill(old_pid, signal.SIGTERM)
                time.sleep(0.5)
        except (ValueError, OSError, ProcessLookupError):
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
        no_speech_threshold=0.6,
        log_prob_threshold=-1.0,
        compression_ratio_threshold=2.4,
    )
    seg_list = list(segments)
    text = " ".join(s.text for s in seg_list).strip()
    # Moyenne des log_prob — plus c'est bas, plus c'est louche
    if seg_list:
        avg_lp = sum(s.avg_logprob for s in seg_list) / len(seg_list)
    else:
        avg_lp = -999.0
    return text, avg_lp

def send_voice(text):
    """Envoie le texte transcrit dans cmd.txt si pas hallucination."""
    if is_hallucination(text):
        return
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
    threshold = FIXED_THRESHOLD if FIXED_THRESHOLD > 0 else max(ambient * 4.0, 200.0)
    _log(f"Ambiant: {ambient:.0f} -> seuil: {threshold:.0f}")
    return threshold

def listen_loop(model, threshold, stream):
    _log(f"Ecoute active — seuil RMS={threshold:.0f}")
    recording = False
    frames    = []
    t_silence = 0.0
    t_speech  = 0.0
    # Anti-flood : cooldown apres envoi d'une utterance
    last_send_time = 0.0
    COOLDOWN = 2.0  # secondes minimum entre deux envois

    while True:
        chunk, _ = stream.read(CHUNK_SAMPLES)
        level    = rms(chunk)

        # TTS actif : reset silencieux
        if os.path.exists(TTS_LOCK_FILE):
            if recording:
                recording = False; frames = []; t_speech = 0.0; t_silence = 0.0
            continue

        if level > threshold:
            if not recording:
                # Anti-flood cooldown
                if time.time() - last_send_time < COOLDOWN:
                    continue
                _log(f"Voix detectee (RMS={level:.0f})")
                recording = True; frames = []; t_speech = 0.0; t_silence = 0.0
            frames.append(chunk.copy())
            t_speech += CHUNK_DURATION
            t_silence = 0.0
            if t_speech >= MAX_DURATION:
                _log("MAX_DURATION")
                try:
                    _transcribe_queue.put_nowait(frames[:])
                except queue.Full:
                    _log("Queue pleine — utterance ignoree")
                last_send_time = time.time()
                recording = False; frames = []; t_speech = 0.0; t_silence = 0.0
        else:
            if recording:
                frames.append(chunk.copy())
                t_silence += CHUNK_DURATION
                if t_silence >= SILENCE_AFTER:
                    if t_speech >= MIN_DURATION:
                        _log(f"Fin utterance ({t_speech:.1f}s)")
                        try:
                            _transcribe_queue.put_nowait(frames[:])
                        except queue.Full:
                            _log("Queue pleine — utterance ignoree")
                        last_send_time = time.time()
                    else:
                        _log(f"Trop court ({t_speech:.2f}s)")
                    recording = False; frames = []; t_speech = 0.0; t_silence = 0.0

# --- Entrypoint ---

if __name__ == "__main__":
    _enforce_singleton()

    for p in [r"C:\Python314\Lib\site-packages\nvidia\cublas\bin",
              r"C:\Python314\Lib\site-packages\nvidia\cudnn\bin"]:
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

    # Thread unique de transcription (pas de threads multiples)
    worker = threading.Thread(target=_transcription_worker, args=(model,), daemon=True)
    worker.start()

    with sd.InputStream(device=BIRD_DEVICE_ID, samplerate=SAMPLE_RATE,
                        channels=1, dtype="int16", blocksize=CHUNK_SAMPLES) as stream:
        threshold = calibrate(stream)
        try:
            listen_loop(model, threshold, stream)
        except KeyboardInterrupt:
            _log("Arret.")
