# 🤖 Project Claudius

**Tête animatronique Kinect Xbox 360 pilotée par IA — 100% local, zéro cloud (sauf LLM).**

Claudius est un compagnon de bureau physique : il écoute, réfléchit, répond à voix haute et bouge la tête. Construit à partir d'un Kinect Xbox 360 v1, piloté par Python et C#, avec reconnaissance vocale (Whisper), intelligence (Claude Haiku API) et synthèse vocale (Piper TTS).

> *"Alors mon Claudius, c'est quoi mon projet de jeu vidéo déjà ?"*
> *"From The Deep, un platformer style Ghouls'n Ghosts avec du WW2 et du cosmic horror."*

---

## 🎯 Fonctionnalités

- **Reconnaissance vocale** — Whisper (faster-whisper) GPU CUDA, transcription en ~0.5s
- **Intelligence conversationnelle** — Claude Haiku API avec mémoire contextuelle (6 échanges) et contexte enrichi dynamique
- **Synthèse vocale** — Piper TTS voix Jessica (fr_FR-upmc-medium), GPU ONNX, ~0.3-0.7s
- **Gestes physiques** — Moteur tilt Kinect : oui, non, blink, hello, think, reset
- **Auto-blink** — Clignement naturel toutes les 4-8s quand inactif
- **Anti-hallucination** — Triple filtre : keywords, logprob, pré-filtre RMS
- **Mode veille** — sleep/wake via commande
- **Transcript live** — Interface web temps réel sur `localhost:5005`
- **Contexte enrichi** — Fichier `claudius_context.txt` rechargé dynamiquement à chaque message
- **Démarrage automatique** — Se lance au boot Windows via .bat dans Startup

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      CLAUDIUS v2                             │
├───────────────┬──────────────┬──────────────┬────────────────┤
│  KinectVoice  │ KinectBridge │   Piper TTS  │  KinectMotor   │
│  (Oreilles)   │  (Cerveau)   │   (Bouche)   │    (Corps)     │
├───────────────┼──────────────┼──────────────┼────────────────┤
│ faster-whisper │ Claude Haiku │ Piper Jessica│ C# / SDK 1.8   │
│ small CUDA    │ API Anthropic│ GPU ONNX     │ Moteur tilt    │
│ Bird UM1 mic  │ Contexte .txt│ winsound WAV │ Motor lock     │
│ VAD RMS 800   │ 6 échanges   │ Fallback     │ Gestes auto    │
│ Triple filtre │ Mémoire conv.│ pyttsx3 local│                │
└───────────────┴──────────────┴──────────────┴────────────────┘
```

### Pipeline voix complet

```
Micro Bird UM1
    │
    ▼
KinectVoice.py (singleton, PID lock)
    ├─ Seuil RMS fixe = 800 (ambiant ~300-500)
    ├─ Queue unique (1 worker, anti-flood cooldown 2s)
    ├─ Pré-filtre RMS moyen (skip si < seuil × 0.7)
    ├─ faster-whisper small FR (CUDA float16, ~0.5s)
    ├─ Filtre logprob < -0.7 → rejet
    ├─ Filtre keywords hallucination (amara, sous-titres, etc.)
    └─ Écrit VOICE:texte → cmd.txt
                │
                ▼
         KinectBridge.py (singleton, PID lock)
                ├─ think (geste Kinect immédiat)
                ├─ Claude Haiku API (~1-2s, contexte enrichi)
                ├─ Geste selon réponse [thread parallèle]
                │     oui / non / hello / think
                └─ Piper Jessica TTS (~0.3-0.7s GPU)
                              │
                              ▼
                        Haut-parleurs (winsound)
```

**Latence totale** : ~3-4s de fin de parole à début de réponse TTS.

---

## 📁 Structure du projet

```
Project-Claudius/
├── KinectBridge.py      — Cerveau : watcher cmd.txt, API Haiku, auto-blink, Piper TTS
├── KinectVoice.py       — Oreilles : VAD RMS + faster-whisper CUDA + triple filtre
├── KinectTTS.py         — Bouche standalone : Piper / pyttsx3 / edge-tts (fallback)
├── KinectMotor.cs       — Corps : C# SDK Kinect 1.8, moteur tilt + snap RGB
├── KinectTranscript.py  — Serveur Flask transcript temps réel (localhost:5005)
├── KinectBridge.bat     — Script de démarrage (Bridge + Voice + Transcript)
├── claudius_context.txt — Contexte enrichi pour Haiku (projets, préférences, etc.)
├── README.md
└── .gitignore
```

> **Non versionné** : `KinectMotor.exe` (compilé localement), `C:\Kinect\piper\` (modèles ~75MB), `api_key.txt`, logs, PID files.

---

## ⚙️ Prérequis

| Composant | Détail |
|-----------|--------|
| **OS** | Windows 10/11 x64 |
| **Kinect** | Xbox 360 v1 + [Kinect for Windows SDK 1.8](https://www.microsoft.com/en-us/download/details.aspx?id=44561) |
| **Python** | 3.10+ (testé : 3.14) |
| **GPU** | NVIDIA RTX recommandé (CUDA pour Whisper + Piper ONNX) |
| **Micro** | USB externe recommandé (testé : Bird UM1, device index 1) |
| **API** | Clé API Anthropic ([console.anthropic.com](https://console.anthropic.com)) |

### Dépendances Python

```bash
pip install faster-whisper sounddevice numpy piper-tts onnxruntime-gpu pyttsx3 edge-tts flask
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12    # DLLs CUDA pour faster-whisper GPU
```

> Sans GPU NVIDIA : remplacer `onnxruntime-gpu` par `onnxruntime` et `faster-whisper` utilisera le CPU (plus lent, ~5s vs ~0.5s).

---

## 🚀 Installation

### 1. Cloner le repo

```bash
git clone https://github.com/PalpatineRex/Project-Claudius.git
cd Project-Claudius
```

### 2. Configurer la clé API

Créer le fichier `C:\Kinect\api_key.txt` contenant uniquement votre clé API Anthropic :

```
sk-ant-api03-xxxxxxxxxxxx
```

> La clé n'est jamais commitée (dans `.gitignore`). Coût estimé : ~1-2€/mois avec Haiku.

### 3. Télécharger la voix Piper Jessica

Créer `C:\Kinect\piper\` et télécharger :

- [fr_FR-upmc-medium.onnx](https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/upmc/medium/fr_FR-upmc-medium.onnx)
- [fr_FR-upmc-medium.onnx.json](https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/upmc/medium/fr_FR-upmc-medium.onnx.json)

### 4. Compiler KinectMotor.exe

Depuis un dossier contenant `Microsoft.Kinect.dll` (SDK 1.8) :

```cmd
csc.exe /platform:x86 /r:Microsoft.Kinect.dll /r:System.Drawing.dll KinectMotor.cs
```

Copier le binaire dans `C:\Kinect\KinectMotor.exe`.

### 5. Déployer

```
C:\Kinect\
├── KinectBridge.py
├── KinectVoice.py
├── KinectTTS.py
├── KinectTranscript.py
├── KinectMotor.exe
├── KinectBridge.bat
├── api_key.txt
├── claudius_context.txt
└── piper\
    ├── fr_FR-upmc-medium.onnx
    └── fr_FR-upmc-medium.onnx.json
```

### 6. Démarrage automatique Windows

Copier `KinectBridge.bat` dans :

```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
```

Claudius démarrera automatiquement à chaque boot. Le `.bat` lance dans l'ordre :
1. `KinectBridge.py` — cerveau + TTS (attend Piper ~4-6s)
2. `KinectVoice.py` — reconnaissance vocale (charge Whisper ~2s)
3. `KinectTranscript.py` — serveur web transcript

### 7. Configuration du micro

Dans `KinectVoice.py`, ajuster `BIRD_DEVICE_ID` à l'index de votre micro USB :

```python
BIRD_DEVICE_ID = 1   # 0 = micro par défaut, 1 = premier USB externe
```

Pour lister les devices disponibles :

```python
import sounddevice as sd; print(sd.query_devices())
```

---

## 🎙️ Commandes

Claudius écoute en permanence via le micro. Il répond vocalement et avec des gestes.

### Commandes texte (via cmd.txt)

| Commande | Effet |
|----------|-------|
| `oui` | Hochement de tête vertical |
| `non` | Mouvement négatif |
| `blink` | Clignement |
| `hello` | Salut (deux inclinaisons) |
| `think` | Réflexion (bascule lente) |
| `reset` | Position neutre |
| `snap` | Capture photo RGB |
| `sleep` | Mode veille (arrête écoute + blink) |
| `wake` | Réveil |
| `VOICE:texte` | Envoie du texte au LLM comme si dit à voix haute |

---

## 🧠 Contexte enrichi

Le fichier `claudius_context.txt` est injecté comme system prompt à chaque appel API. Il contient les projets en cours, les préférences, et les instructions de personnalité de Claudius.

**Rechargement dynamique** : le fichier est relu à chaque message. Si vous le modifiez pendant que Claudius tourne, le prochain échange utilisera le nouveau contexte sans redémarrage.

Exemple de contenu :

```
## Projets en cours
### Project Claudius (ce projet)
Tête animatronique Kinect Xbox 360 pilotée par IA.
Statut: voix v2 fonctionnelle, CUDA GPU OK.

### From The Deep (jeu vidéo)
Platformer Ghouls'n Ghosts, thème WW2 + Cosmic Horror, Godot 4.6.

## Préférences de David
- Réponses courtes, 1-2 phrases max
- Français uniquement
- Pas de markdown
```

---

## 🛡️ Anti-hallucination (triple filtre)

Whisper hallucine fréquemment sur du bruit ambiant (répète "Sous-titres réalisés par Amara.org", "Merci d'avoir regardé", etc.). Claudius utilise 3 couches de filtrage :

1. **Pré-filtre RMS** — Si l'énergie moyenne de l'utterance est < 70% du seuil, pas de transcription du tout
2. **Filtre keywords** — Liste de mots-clés hallucination connus (amara, sous-titres, abonnez, etc.)
3. **Filtre logprob** — Si `avg_logprob < -0.7`, Whisper n'est pas confiant → rejet

En plus :
- **Cooldown 2s** entre deux envois (anti-flood)
- **Queue unique** à 1 worker (pas de threads multiples de transcription)
- **Singleton PID** (une seule instance de Voice/Bridge peut tourner)

---

## 📊 Performances mesurées (RTX 3060, i5)

| Étape | Durée |
|-------|-------|
| Transcription Whisper small CUDA float16 | ~0.4-0.8s |
| Appel API Claude Haiku | ~1-2s |
| Synthèse Piper Jessica GPU | ~0.3-0.7s |
| Playback winsound | durée audio |
| **Latence totale** (fin parole → début réponse) | **~3-4s** |

| Ressource | Usage |
|-----------|-------|
| RAM KinectVoice (Whisper small) | ~810 MB |
| RAM KinectBridge (Piper) | ~270 MB |
| RAM KinectTranscript (Flask) | ~38 MB |
| VRAM GPU | ~1.5 GB (Whisper + Piper ONNX) |
| Coût API mensuel (50 msg/jour) | ~0.40€ |

---

## 🔧 Dépannage

**Claudius ne m'entend pas**
- Vérifier `BIRD_DEVICE_ID` dans KinectVoice.py
- Vérifier que le seuil RMS n'est pas trop haut (logs : `Ambiant: XXX -> seuil: 800`)
- Si ambiant > 600, augmenter `FIXED_THRESHOLD`

**Hallucinations Whisper**
- Ajouter les mots-clés récurrents dans `HALLUCINATION_KEYWORDS`
- Baisser `log_prob_threshold` dans `transcribe()` si trop de faux positifs passent

**Plusieurs instances Python zombies**
- Les singletons PID tuent automatiquement les anciennes instances au relancement
- Vérifier avec : `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Select ProcessId, CommandLine`

**Pas de GPU / CUDA**
- Installer : `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`
- Vérifier : `python -c "import ctranslate2; print(ctranslate2.get_supported_compute_types('cuda'))"`
- Fallback CPU automatique si CUDA indisponible

**Piper TTS lent (~7s)**
- Installer `onnxruntime-gpu` (remplace `onnxruntime`)
- Vérifier : `python -c "import onnxruntime; print(onnxruntime.get_available_providers())"`
- Doit afficher `CUDAExecutionProvider`

**Erreur API Claude**
- Vérifier `C:\Kinect\api_key.txt` (clé valide, pas d'espaces)
- Logs : chercher `ERR claude:` dans `kinect.log`

---

## 📜 Historique

| Version | Date | Changements |
|---------|------|-------------|
| v2.0 | 2026-03-18 | Singleton PID, queue anti-flood, triple filtre hallucination, pré-filtre RMS, contexte enrichi dynamique, audit complet, nettoyage repo |
| v1.5 | 2026-03-12 | Migration Ollama → API Claude Haiku, Piper TTS Jessica GPU, clé API hors versioning, mémoire conversationnelle 6 échanges |
| v1.0 | 2026-03-11 | Pipeline voix complet : Whisper + Ollama llama3.2:3b + pyttsx3 Hortense + edge-tts Neural. Gestes, auto-blink, sleep/wake |
| v0.5 | 2026-03-10 | Channel 1 : moteur Kinect, snap RGB, cmd.txt watcher |
| v0.1 | 2026-03-09 | Premier contact Kinect, drivers, tests SDK |

---

## 🗺️ Roadmap

- [ ] **Détection de présence** — Skeleton tracking / depth pour détecter si quelqu'un est devant le Kinect
- [ ] **Geste WAVE** — Détecter un geste de salut → Claudius salue automatiquement
- [ ] **Vision** — Snap automatique → décrire ce qu'il voit via LLM vision
- [ ] **Interface web dashboard** — Logs temps réel, contrôle, état depuis n'importe quel appareil du réseau
- [ ] **Bras imprimés 3D** — Servos + pièces résine pour des gestes plus expressifs
- [ ] **Voix custom** — Entraîner un modèle TTS sur une voix personnalisée

---

## 📄 Licence

Projet personnel. Code source disponible à titre éducatif.

---

*Built with ❤️ by David — powered by a Kinect, some Python, and a lot of stubbornness.*
