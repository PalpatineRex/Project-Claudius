# Project Claudius

Une tête animatronique Kinect Xbox 360 pilotée par IA locale.  
Conçu par David, développé avec Claude (Anthropic).

## Architecture

```
KinectBridge.py   — Cerveau central : moteur, blink, watcher, Ollama
KinectVoice.py    — Oreilles : VAD + transcription Whisper
KinectTTS.py      — Bouche : synthèse vocale pyttsx3 / edge-tts Neural
KinectMotor.exe   — Corps : C# compilé, pilote le moteur Kinect via SDK managé
```

## Pipeline voix complet

```
Micro Bird UM1
    → KinectVoice (VAD RMS + Whisper base FR)
        → cmd.txt : VOICE:texte
            → KinectBridge
                → think (geste Kinect)
                → Ollama llama3.2:3b local (~3.5s)
                → geste selon réponse (oui/non/hello/think) [parallèle]
                → KinectTTS (pyttsx3 Hortense FR ou edge-tts Henri Neural)
```

## Prérequis

- Windows 10/11 x64
- Kinect Xbox 360 v1 + SDK Kinect for Windows 1.8
- Python 3.x (testé sur 3.14)
- [Ollama](https://ollama.ai) avec `llama3.2:3b` : `ollama pull llama3.2:3b`
- Microphone USB (testé : BIRD UM1, device index 1)

### Dépendances Python

```
pip install openai-whisper sounddevice numpy edge-tts pyttsx3
```

## Installation

### 1. Compiler KinectMotor.exe

```cmd
csc.exe /platform:x86 /r:Microsoft.Kinect.dll /r:System.Drawing.dll KinectMotor.cs
```

Copier le binaire dans `C:\Kinect\KinectMotor.exe`.

### 2. Déployer les scripts Python

```
C:\Kinect\
    KinectBridge.py
    KinectVoice.py
    KinectTTS.py
    KinectMotor.exe
```

### 3. Démarrage automatique Windows

Créer `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\KinectBridge.bat` :

```bat
@echo off
start "" /MIN "C:\Python314\pythonw.exe" "C:\Kinect\KinectBridge.py"
timeout /t 3 /nobreak >nul
start "" /MIN "C:\Python314\pythonw.exe" "C:\Kinect\KinectVoice.py"
```

## Commandes manuelles

Écrire dans `cmd.txt` (workbench) :

| Commande | Effet |
|----------|-------|
| `blink` | Cligne des yeux |
| `oui` | Acquiescement vertical |
| `non` | Négation horizontal |
| `hello` | Salutation |
| `think` | Réflexion |
| `reset` | Recentrage à 0° |
| `snap` | Photo RGB → KinectSnap-DATE.png |
| `VOICE:texte` | Traitement voix direct (sans micro) |

## Configuration

Dans `KinectBridge.py` :
- `OLLAMA_MDL` — modèle LLM (défaut: `llama3.2:3b`)
- Changer `_tts_wait(reply)` → `_tts_wait(reply, neural=True)` pour voix Henri Neural

Dans `KinectVoice.py` :
- `BIRD_DEVICE_ID` — index device micro
- `NOISE_FACTOR` — sensibilité VAD (défaut: 4.0)
- `SILENCE_AFTER` — délai fin utterance en secondes (défaut: 1.2)

Dans `KinectTTS.py` :
- `VOICE_INDEX` — 0=Hortense FR, 1=Zira EN, 2=David EN

## Roadmap

- [x] N0 — Présence, blink idle, gestes, snap, démarrage auto
- [x] N1 — Reconnaissance vocale + réponse Ollama local  
- [ ] N2 — États présence via skeleton tracking (AWAY / PRESENT / FOCUS)
- [ ] N3 — Gestes utilisateur détectés (WAVE, bras levé)
- [ ] N4 — Vision ponctuelle (snap → LLM Vision → description)
- [ ] N5 — Bras imprimés 3D (resin printer)

## Logs

Tous les événements → `kinect.log` dans le workbench.
