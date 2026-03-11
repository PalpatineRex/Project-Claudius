"""
KinectVoice.py - Reconnaissance vocale pour Claudius
Ecoute UNIQUEMENT le micro Bird (device 1).
VAD avec calibration automatique du seuil bruit ambiant.
Transcription Whisper local (FR), resultat -> cmd.txt : VOICE:texte
"""
import sounddevice as sd
import numpy as np
import whisper
import time
import os
import re

BIRD_DEVICE_ID = 1
SAMPLE_RATE    = 16000
CHANNELS       = 1
CHUNK_DURATION = 0.1
CHUNK_SAMPLES  = int(SAMPLE_RATE * CHUNK_DURATION)

SILENCE_AFTER  = 1.2   # secondes de silence pour clore une utterance
MIN_DURATION   = 0.5   # duree minimale utterance
MAX_DURATION   = 15.0  # duree maximale utterance
NOISE_FACTOR   = 4.0   # seuil = ambiant * NOISE_FACTOR

CMD_FILE      = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\cmd.txt"
LOG_FILE      = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\kinect.log"
TTS_LOCK_FILE = r"C:\Users\PC\Downloads\Claude AI Workbench\kinect\tts_speaking.lock"
MODEL_SIZE    = "base"

# Patterns d hallucination Whisper a filtrer
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
    """Retourne True si le texte est probablement une hallucination Whisper."""
    for pat in HALLUCINATION_PATTERNS:
        if re.match(pat, text, re.IGNORECASE):
            return True
    if text.count("...") >= 2 or text.count("…") >= 2:
        return True
    cleaned = re.sub(r"[^\w]", "", text)
    if len(cleaned) < 3:
        return True
    return False

def transcribe(frames, model):
    """Concatene les frames et transcrit avec Whisper."""
    audio = np.concatenate(frames, axis=0).flatten()
    audio_f32 = audio.astype(np.float32) / 32768.0
    result = model.transcribe(
        audio_f32,
        language="fr",
        fp16=False,
        temperature=0.0,
        no_speech_threshold=0.6,
        logprob_threshold=-1.0
    )
    return result["text"].strip()

def send_voice(text):
    """Envoie VOICE:texte dans cmd.txt si valide, canal libre, et Claudius ne parle pas."""
    if not text or is_hallucination(text):
        _log("Hallucination filtree: " + repr(text[:40]))
        return
    if os.path.exists(TTS_LOCK_FILE):
        _log("Claudius parle — utterance ignoree: " + text[:40])
        return
    if os.path.exists(CMD_FILE):
        _log("cmd.txt occupe, ignore: " + text[:40])
        return
    try:
        with open(CMD_FILE, "w", encoding="utf-8") as f:
            f.write("VOICE:" + text)
        _log(">>> " + text)
    except Exception as e:
        _log("ERR send: " + str(e))

def calibrate(stream, duration=2.0):
    """Mesure le bruit ambiant et retourne le seuil RMS recommande."""
    _log("Calibration (" + str(duration) + "s) — silence svp...")
    samples = int(duration / CHUNK_DURATION)
    levels = []
    for _ in range(samples):
        chunk, _ = stream.read(CHUNK_SAMPLES)
        levels.append(rms(chunk))
    ambient = float(np.mean(levels))
    threshold = max(ambient * NOISE_FACTOR, 50.0)
    _log("Ambiant: " + f"{ambient:.1f}" + " -> seuil: " + f"{threshold:.1f}")
    return threshold

def listen_loop(model, threshold, stream):
    """Boucle d ecoute. Prend le stream deja ouvert (partage avec calibrate)."""
    _log("Ecoute active — seuil RMS=" + f"{threshold:.1f}")
    recording    = False
    frames       = []
    silence_time = 0.0
    speech_time  = 0.0
    while True:
        chunk, _ = stream.read(CHUNK_SAMPLES)
        level = rms(chunk)
        if level > threshold:
            if not recording:
                _log("Voix detectee (RMS=" + f"{level:.0f}" + ")")
                recording    = True
                frames       = []
                speech_time  = 0.0
                silence_time = 0.0
            frames.append(chunk.copy())
            speech_time  += CHUNK_DURATION
            silence_time  = 0.0
            if speech_time >= MAX_DURATION:
                _log("MAX_DURATION, transcription forcee")
                send_voice(transcribe(frames, model))
                recording    = False
                frames       = []
                speech_time  = 0.0
                silence_time = 0.0
        else:
            if recording:
                frames.append(chunk.copy())
                silence_time += CHUNK_DURATION
                if silence_time >= SILENCE_AFTER:
                    if speech_time >= MIN_DURATION:
                        _log("Fin utterance (" + f"{speech_time:.1f}" + "s)")
                        send_voice(transcribe(frames, model))
                    else:
                        _log("Trop court (" + f"{speech_time:.2f}" + "s)")
                    recording    = False
                    frames       = []
                    silence_time = 0.0
                    speech_time  = 0.0

if __name__ == "__main__":
    _log("Chargement Whisper '" + MODEL_SIZE + "'...")
    model = whisper.load_model(MODEL_SIZE)
    _log("Modele pret.")
    with sd.InputStream(device=BIRD_DEVICE_ID, samplerate=SAMPLE_RATE,
                        channels=CHANNELS, dtype="int16",
                        blocksize=CHUNK_SAMPLES) as stream:
        threshold = calibrate(stream)
        try:
            listen_loop(model, threshold, stream)
        except KeyboardInterrupt:
            _log("Arret KinectVoice.")
