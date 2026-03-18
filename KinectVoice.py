"""
KinectVoice.py - Reconnaissance vocale pour Claudius
faster-whisper (ctranslate2) - GPU float16 si dispo, sinon CPU int8
Ecoute UNIQUEMENT le micro Bird (device 1).
"""
import sounddevice as sd
import numpy as np
import time, os, re
from faster_whisper import WhisperModel

BIRD_DEVICE_ID = 1
SAMPLE_RATE    = 16000
CHANNELS       = 1
CHUNK_DURATION = 0.1
CHUNK_SAMPLES  = int(SAMPLE_RATE * CHUNK_DURATION)

SILENCE_AFTER  = 1.0
MIN_DURATION   = 0.8
MAX_DURATION   = 8.0
NOISE_FACTOR   = 3.5
FIXED_THRESHOLD = 350   # seuil fixe calibre sur RMS voix David (~400-550)
MODEL_SIZE     = "small"

CMD_FILE        = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\cmd.txt"
LOG_FILE        = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\kinect.log"
TRANSCRIPT_FILE = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\transcript.txt"
TTS_LOCK_FILE   = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\tts_speaking.lock"
SLEEP_FILE      = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\claudius_sleep.lock"

HALLUCINATION_PATTERNS = [
    r"^\s*[\.\s\u2026]+\s*$",
    r"^[\s\W]+$",
    r"^(merci|sous-titres|sous titres|transcription|abonne|amara|traduction|sous-titre).{0,60}$",
    r"^\s*$",
    r".*(amara\.org|sous-titr|wikimedia|creative commons).*",
]

def _log(msg):
    line = "[VOICE " + time.strftime("%H:%M:%S") + "] " + msg
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def _write_transcript(speaker, text):
    """Ecrit dans transcript.txt pour affichage temps reel."""
    try:
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {speaker}: {text}\n"
        with open(TRANSCRIPT_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass

def rms(chunk):
    return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))

def is_hallucination(text):
    for pat in HALLUCINATION_PATTERNS:
        if re.match(pat, text, re.IGNORECASE):
            return True
    if text.count("...") >= 2 or text.count("…") >= 2:
        return True
    if len(re.sub(r"[^\w]", "", text)) < 3:
        return True
    mots_reels = [m for m in re.findall(r"[a-zA-ZÀ-ÿ]{2,}", text)]
    if len(mots_reels) < 2:
        return True
    return False

def transcribe(frames, model):
    audio = np.concatenate(frames, axis=0).flatten().astype(np.float32) / 32768.0
    segments, info = model.transcribe(
        audio,
        language="fr",
        beam_size=5,
        vad_filter=False,
    )
    text = " ".join(seg.text for seg in segments).strip()
    return text

def send_voice(text):
    if not text or is_hallucination(text):
        _log("Hallucination filtree: " + repr(text[:40])); return
    if os.path.exists(SLEEP_FILE):
        _log("Veille — utterance ignoree"); return
    if os.path.exists(TTS_LOCK_FILE):
        _log("Claudius parle — utterance ignoree: " + text[:40]); return
    if os.path.exists(CMD_FILE):
        _log("cmd.txt occupe, ignore"); return
    _write_transcript("David", text)
    try:
        with open(CMD_FILE, "w", encoding="utf-8") as f:
            f.write("VOICE:" + text)
        _log(">>> " + text)
    except Exception as e:
        _log("ERR send: " + str(e))

def calibrate(stream, duration=2.0):
    _log("Calibration (" + str(duration) + "s) — silence svp...")
    samples = int(duration / CHUNK_DURATION)
    levels  = [rms(stream.read(CHUNK_SAMPLES)[0]) for _ in range(samples)]
    ambient   = float(np.mean(levels))
    threshold = ambient * NOISE_FACTOR
    if FIXED_THRESHOLD > 0:
        threshold = FIXED_THRESHOLD
        _log("Ambiant: " + f"{ambient:.1f}" + " -> seuil FIXE: " + f"{threshold:.1f}")
    else:
        threshold = max(threshold, 50.0)
        _log("Ambiant: " + f"{ambient:.1f}" + " -> seuil auto: " + f"{threshold:.1f}")
    return threshold

def listen_loop(model, threshold, stream):
    _log("Ecoute active — seuil RMS=" + f"{threshold:.1f}")
    recording    = False
    frames       = []
    silence_time = 0.0
    speech_time  = 0.0
    while True:
        chunk, _ = stream.read(CHUNK_SAMPLES)
        level     = rms(chunk)
        if level > threshold:
            if os.path.exists(TTS_LOCK_FILE):
                recording = False; frames = []; speech_time = 0.0; silence_time = 0.0
                continue
            if not recording:
                _log("Voix detectee (RMS=" + f"{level:.0f}" + ")")
                recording = True; frames = []; speech_time = 0.0; silence_time = 0.0
            frames.append(chunk.copy())
            speech_time += CHUNK_DURATION; silence_time = 0.0
            if speech_time >= MAX_DURATION:
                _log("MAX_DURATION, transcription forcee")
                t0 = time.time()
                txt = transcribe(frames, model)
                _log(f"Transcrit en {time.time()-t0:.2f}s")
                send_voice(txt)
                recording = False; frames = []; speech_time = 0.0; silence_time = 0.0
        else:
            if recording:
                frames.append(chunk.copy())
                silence_time += CHUNK_DURATION
                if silence_time >= SILENCE_AFTER:
                    if speech_time >= MIN_DURATION:
                        _log("Fin utterance (" + f"{speech_time:.1f}" + "s)")
                        t0 = time.time()
                        txt = transcribe(frames, model)
                        _log(f"Transcrit en {time.time()-t0:.2f}s")
                        send_voice(txt)
                    else:
                        _log("Trop court (" + f"{speech_time:.2f}" + "s)")
                    recording = False; frames = []; silence_time = 0.0; speech_time = 0.0

if __name__ == "__main__":
    # Ajouter DLLs CUDA nvidia au PATH pour ctranslate2
    import sys
    _cuda_paths = [
        r"C:\Python314\Lib\site-packages\nvidia\cublas\bin",
        r"C:\Python314\Lib\site-packages\nvidia\cudnn\bin",
        r"C:\Python314\Lib\site-packages\nvidia\cuda_runtime\bin",
    ]
    os.environ["PATH"] = ";".join(_cuda_paths) + ";" + os.environ.get("PATH", "")

    # Tenter GPU, fallback CPU
    try:
        import ctranslate2
        ctranslate2.get_supported_compute_types("cuda")  # probe
        device, compute = "cuda", "float16"
    except Exception:
        device, compute = "cpu", "int8"
    _log(f"Chargement faster-whisper '{MODEL_SIZE}' ({device} {compute})...")
    model = WhisperModel(MODEL_SIZE, device=device, compute_type=compute)
    _log(f"Modele pret. [{device.upper()} {compute}]")
    with sd.InputStream(device=BIRD_DEVICE_ID, samplerate=SAMPLE_RATE,
                        channels=CHANNELS, dtype="int16",
                        blocksize=CHUNK_SAMPLES) as stream:
        threshold = calibrate(stream)
        try:
            listen_loop(model, threshold, stream)
        except KeyboardInterrupt:
            _log("Arret KinectVoice.")
