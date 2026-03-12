"""
KinectVoice.py - Reconnaissance vocale pour Claudius
Ecoute UNIQUEMENT le micro Bird (device 1).
VAD avec calibration automatique + filtre hallucinations Whisper.
Transcription Whisper base FR (fp16 si GPU dispo).
Resultat -> cmd.txt : VOICE:texte
"""
import sounddevice as sd
import numpy as np
import whisper
import time, os, re, torch

BIRD_DEVICE_ID = 1
SAMPLE_RATE    = 16000
CHANNELS       = 1
CHUNK_DURATION = 0.1
CHUNK_SAMPLES  = int(SAMPLE_RATE * CHUNK_DURATION)

SILENCE_AFTER  = 1.2    # secondes de silence pour clore une utterance
MIN_DURATION   = 0.5    # duree minimale utterance
MAX_DURATION   = 15.0   # duree maximale
NOISE_FACTOR   = 4.0    # seuil = ambiant * NOISE_FACTOR
MODEL_SIZE     = "small"

CMD_FILE      = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\cmd.txt"
LOG_FILE      = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\kinect.log"
TTS_LOCK_FILE = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\tts_speaking.lock"
SLEEP_FILE    = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\claudius_sleep.lock"

HALLUCINATION_PATTERNS = [
    r"^\s*[\.\s\u2026]+\s*$",
    r"^[\s\W]+$",
    r"^(merci|sous-titres|sous titres|transcription|abonne).{0,30}$",
    r"^\s*$",
]

def _log(msg):
    line = "[VOICE " + time.strftime("%H:%M:%S") + "] " + msg
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
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
    return False

def transcribe(frames, model, use_fp16):
    audio = np.concatenate(frames, axis=0).flatten().astype(np.float32) / 32768.0
    result = model.transcribe(
        audio,
        language="fr",
        fp16=use_fp16,
        temperature=0.0,
        no_speech_threshold=0.6,
        logprob_threshold=-1.0
    )
    return result["text"].strip()

def send_voice(text):
    if not text or is_hallucination(text):
        _log("Hallucination filtree: " + repr(text[:40])); return
    if os.path.exists(SLEEP_FILE):
        _log("Veille — utterance ignoree"); return
    if os.path.exists(TTS_LOCK_FILE):
        _log("Claudius parle — utterance ignoree: " + text[:40]); return
    if os.path.exists(CMD_FILE):
        _log("cmd.txt occupe, ignore"); return
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
    threshold = max(ambient * NOISE_FACTOR, 50.0)
    _log("Ambiant: " + f"{ambient:.1f}" + " -> seuil: " + f"{threshold:.1f}")
    return threshold

def listen_loop(model, threshold, stream, use_fp16):
    _log("Ecoute active — seuil RMS=" + f"{threshold:.1f}" + (" [fp16]" if use_fp16 else " [fp32]"))
    recording    = False
    frames       = []
    silence_time = 0.0
    speech_time  = 0.0
    while True:
        chunk, _ = stream.read(CHUNK_SAMPLES)
        level     = rms(chunk)
        if level > threshold:
            if not recording:
                _log("Voix detectee (RMS=" + f"{level:.0f}" + ")")
                recording = True; frames = []; speech_time = 0.0; silence_time = 0.0
            frames.append(chunk.copy())
            speech_time += CHUNK_DURATION; silence_time = 0.0
            if speech_time >= MAX_DURATION:
                _log("MAX_DURATION, transcription forcee")
                send_voice(transcribe(frames, model, use_fp16))
                recording = False; frames = []; speech_time = 0.0; silence_time = 0.0
        else:
            if recording:
                frames.append(chunk.copy())
                silence_time += CHUNK_DURATION
                if silence_time >= SILENCE_AFTER:
                    if speech_time >= MIN_DURATION:
                        _log("Fin utterance (" + f"{speech_time:.1f}" + "s)")
                        send_voice(transcribe(frames, model, use_fp16))
                    else:
                        _log("Trop court (" + f"{speech_time:.2f}" + "s)")
                    recording = False; frames = []; silence_time = 0.0; speech_time = 0.0

if __name__ == "__main__":
    use_fp16 = torch.cuda.is_available()
    _log("Chargement Whisper '" + MODEL_SIZE + "' (" + ("GPU fp16" if use_fp16 else "CPU fp32") + ")...")
    model = whisper.load_model(MODEL_SIZE)
    _log("Modele pret.")
    with sd.InputStream(device=BIRD_DEVICE_ID, samplerate=SAMPLE_RATE,
                        channels=CHANNELS, dtype="int16",
                        blocksize=CHUNK_SAMPLES) as stream:
        threshold = calibrate(stream)
        try:
            listen_loop(model, threshold, stream, use_fp16)
        except KeyboardInterrupt:
            _log("Arret KinectVoice.")
