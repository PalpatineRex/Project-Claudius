"""
KinectVoice.py - Reconnaissance vocale Claudius
faster-whisper GPU float16 / CPU int8 fallback
Bird UM1 device 1
"""
import sounddevice as sd
import numpy as np
import time, os, re, threading
from faster_whisper import WhisperModel

BIRD_DEVICE_ID  = 1
SAMPLE_RATE     = 16000
CHUNK_DURATION  = 0.1
CHUNK_SAMPLES   = int(SAMPLE_RATE * CHUNK_DURATION)

SILENCE_AFTER   = 1.5
MIN_DURATION    = 0.8
MAX_DURATION    = 8.0
FIXED_THRESHOLD = 600   # seuil fixe — ajuster si trop de faux positifs/negatifs
NOISE_FACTOR    = 1.5   # utilise seulement si FIXED_THRESHOLD = 0
MODEL_SIZE      = "small"

CMD_FILE        = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\cmd.txt"
LOG_FILE        = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\kinect.log"
TRANSCRIPT_FILE = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\transcript.txt"
TTS_LOCK_FILE   = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\tts_speaking.lock"
SLEEP_FILE      = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\claudius_sleep.lock"

# Mots-cles hallucination Whisper — simples, robustes, sans regex complexe
HALLUCINATION_KEYWORDS = [
    "amara", "sous-titr", "sous titr", "wikimedia", "creative commons",
    "merci d'avoir regard", "merci d avoir regard",
    "n'oubliez pas", "abonnez", "likez", "partagez",
    "youtube.com", "twitter.com", "facebook.com",
]

# Verrou global : 1 seule transcription active a la fois
_processing = threading.Lock()
_send_lock  = threading.Lock()


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
    """Normalise apostrophes et met en minuscule pour comparaison."""
    return text.lower().replace("\u2019", "'").replace("\u2018", "'").replace("\u2032", "'")

def is_hallucination(text):
    t = text.strip()
    if not t:
        return True
    tc = _clean(t)
    for kw in HALLUCINATION_KEYWORDS:
        if kw in tc:
            return True
    # Vide ou ponctuation seule
    if len(re.sub(r"[^\w]", "", t)) < 3:
        return True
    # Moins de 2 vrais mots
    if len(re.findall(r"[a-zA-Z\u00C0-\u024F]{2,}", t)) < 2:
        return True
    return False

def transcribe(frames, model):
    audio = np.concatenate(frames).flatten().astype(np.float32) / 32768.0
    segments, _ = model.transcribe(
        audio,
        language="fr",
        beam_size=5,
        vad_filter=False,
        no_speech_threshold=0.6,
        log_prob_threshold=-1.0,
        compression_ratio_threshold=2.4,
    )
    return " ".join(s.text for s in segments).strip()

def send_voice(text):
    if is_hallucination(text):
        _log(f"Hallucination: {repr(text[:60])}"); return
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

def process_utterance(frames, model):
    """Tourne dans un thread. _processing lock garantit 1 seul traitement a la fois."""
    if not _processing.acquire(blocking=False):
        _log("Traitement en cours — utterance ignoree")
        return
    try:
        t0 = time.time()
        txt = transcribe(frames, model)
        _log(f"Transcrit en {time.time()-t0:.2f}s")
        send_voice(txt)
    finally:
        _processing.release()

def calibrate(stream, duration=2.0):
    _log(f"Calibration {duration}s — silence svp...")
    levels = [rms(stream.read(CHUNK_SAMPLES)[0]) for _ in range(int(duration / CHUNK_DURATION))]
    ambient = float(np.mean(levels))
    threshold = FIXED_THRESHOLD if FIXED_THRESHOLD > 0 else max(ambient * NOISE_FACTOR, 200.0)
    _log(f"Ambiant: {ambient:.0f} -> seuil: {threshold:.0f}")
    return threshold

def listen_loop(model, threshold, stream):
    _log(f"Ecoute active — seuil RMS={threshold:.0f}")
    recording = False
    frames    = []
    t_silence = 0.0
    t_speech  = 0.0

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
                _log(f"Voix detectee (RMS={level:.0f})")
                recording = True; frames = []; t_speech = 0.0; t_silence = 0.0
            frames.append(chunk.copy())
            t_speech += CHUNK_DURATION
            t_silence = 0.0
            if t_speech >= MAX_DURATION:
                _log("MAX_DURATION")
                threading.Thread(target=process_utterance, args=(frames[:], model), daemon=True).start()
                recording = False; frames = []; t_speech = 0.0; t_silence = 0.0
        else:
            if recording:
                frames.append(chunk.copy())
                t_silence += CHUNK_DURATION
                if t_silence >= SILENCE_AFTER:
                    if t_speech >= MIN_DURATION:
                        _log(f"Fin utterance ({t_speech:.1f}s)")
                        threading.Thread(target=process_utterance, args=(frames[:], model), daemon=True).start()
                    else:
                        _log(f"Trop court ({t_speech:.2f}s)")
                    recording = False; frames = []; t_speech = 0.0; t_silence = 0.0

if __name__ == "__main__":
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
    model = WhisperModel(MODEL_SIZE, device=device, compute_type=compute)
    _log(f"Modele pret. [{device.upper()} {compute}]")
    with sd.InputStream(device=BIRD_DEVICE_ID, samplerate=SAMPLE_RATE,
                        channels=1, dtype="int16", blocksize=CHUNK_SAMPLES) as stream:
        threshold = calibrate(stream)
        try:
            listen_loop(model, threshold, stream)
        except KeyboardInterrupt:
            _log("Arret.")
