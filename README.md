# 🤖 Project Claudius

> *Une tête animatronique Kinect Xbox 360 pilotée par IA locale — sans cloud, sans abonnement.*

Conçu et construit par **David**, développé en collaboration avec **Claude (Anthropic)**.  
Claudius écoute, réfléchit, parle et bouge — entièrement en local sur une RTX 3060.

![Status](https://img.shields.io/badge/status-v1%20live-brightgreen)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)
![Python](https://img.shields.io/badge/python-3.14-blue)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## 📸 Ce que c'est

Claudius est une **tête Kinect Xbox 360** posée sur un écran, transformée en agent conversationnel physique :

- 🎙️ Il **entend** via un micro USB (Bird UM1) avec détection d'activité vocale
- 🧠 Il **comprend** grâce à Whisper (transcription FR locale)
- 💬 Il **réfléchit** avec Ollama + llama3.2:3b (LLM local, ~3.5s chaud)
- 🗣️ Il **parle** avec Piper TTS voix Jessica (fr_FR-upmc-medium, ~1.2s)
- 👀 Il **réagit** physiquement : blink automatique, acquiescement, négation, salutation

Zéro cloud. Zéro abonnement. Tout tourne sur la machine.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLAUDIUS v1                          │
├──────────────┬──────────────┬──────────────┬────────────────┤
│ KinectVoice  │ KinectBridge │  KinectTTS   │  KinectMotor   │
│  (Oreilles)  │  (Cerveau)   │   (Bouche)   │    (Corps)     │
├──────────────┼──────────────┼──────────────┼────────────────┤
│ VAD RMS      │ cmd.txt poll │ Piper Jessica│ C# / SDK 1.8   │
│ Whisper base │ Ollama local │ pyttsx3 FR   │ Moteur tilt    │
│ Bird UM1     │ Auto-blink   │ edge-tts NG  │ Motor lock     │
└──────────────┴──────────────┴──────────────┴────────────────┘
```


### Pipeline voix complet

```
Micro Bird UM1
    │
    ▼
KinectVoice.py
    ├─ Calibration RMS ambiant au boot (2s)
    ├─ VAD RMS temps réel (seuil × 4.0)
    ├─ Whisper base FR (GPU/CPU)
    ├─ Filtre hallucinations ("... ... ...", ponctuation seule)
    └─ Écrit : VOICE:texte → cmd.txt
                │
                ▼
         KinectBridge.py
                ├─ think (geste Kinect immédiat)
                ├─ Ollama llama3.2:3b local (~3.5s chaud)
                ├─ Geste selon réponse [thread parallèle]
                │     oui / non / hello / think
                └─ KinectTTS.py (Piper Jessica ~1.2s)
                              │
                              ▼
                        Haut-parleurs
```

**Latence totale** : ~6s de fin de parole à début de réponse TTS.

---

## 📁 Structure du projet

```
Project-Claudius/
├── KinectBridge.py      — Cerveau : watcher cmd.txt, Ollama, auto-blink, Piper TTS
├── KinectVoice.py       — Oreilles : VAD RMS + Whisper base FR
├── KinectTTS.py         — Bouche : Piper Jessica / pyttsx3 / edge-tts Neural
├── KinectMotor.cs       — Corps : C# SDK Kinect, moteur tilt + snap RGB
├── README.md
└── .gitignore
```

> **Note :** `KinectMotor.exe` (compilé) et `C:\Kinect\piper\` (modèles TTS ~75MB) ne sont **pas** dans le repo — voir installation.

---

## ⚙️ Prérequis

| Composant | Détail |
|-----------|--------|
| OS | Windows 10/11 x64 |
| Kinect | Xbox 360 v1 (Kinect for Windows SDK 1.8) |
| Python | 3.x (testé : 3.14) |
| GPU | Recommandé RTX (Ollama GPU + onnxruntime-gpu) |
| Micro | USB (testé : Bird UM1, device index 1) |
| Ollama | [ollama.ai](https://ollama.ai) avec `llama3.2:3b` |

### Dépendances Python

```bash
pip install openai-whisper sounddevice numpy edge-tts pyttsx3 piper-tts onnxruntime-gpu
```

> `onnxruntime-gpu` accélère Piper TTS (1.2s/synth vs 7s CPU).  
> Si pas de GPU NVIDIA, utiliser `onnxruntime` standard.


---

## 🚀 Installation

### 1. Cloner le repo

```bash
git clone https://github.com/PalpatineRex/Project-Claudius.git
cd Project-Claudius
```

### 2. Installer Ollama + modèle LLM

```bash
# Installer Ollama : https://ollama.ai
ollama pull llama3.2:3b
```

### 3. Télécharger la voix Piper Jessica

```python
# Créer C:\Kinect\piper\ puis télécharger :
# https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/upmc/medium/fr_FR-upmc-medium.onnx
# https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/upmc/medium/fr_FR-upmc-medium.onnx.json
```

### 4. Compiler KinectMotor.exe

Depuis un dossier contenant `Microsoft.Kinect.dll` (SDK 1.8) :

```cmd
csc.exe /platform:x86 /r:Microsoft.Kinect.dll /r:System.Drawing.dll KinectMotor.cs
```

Copier le binaire dans `C:\Kinect\KinectMotor.exe`.

### 5. Déployer les scripts Python

```
C:\Kinect\
├── KinectBridge.py
├── KinectVoice.py
├── KinectTTS.py
├── KinectMotor.exe
└── piper\
    ├── fr_FR-upmc-medium.onnx
    └── fr_FR-upmc-medium.onnx.json
```

### 6. Démarrage automatique Windows

Créer `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\KinectBridge.bat` :

```bat
@echo off
start "" /MIN "C:\Python314\pythonw.exe" "C:\Kinect\KinectBridge.py"
timeout /t 3 /nobreak >nul
start "" /MIN "C:\Python314\pythonw.exe" "C:\Kinect\KinectVoice.py"
```

Claudius démarrera automatiquement à chaque boot Windows.

---

## 🎮 Commandes manuelles

Écrire dans `cmd.txt` (workbench) pour déclencher une action immédiate :

| Commande | Effet |
|----------|-------|
| `blink` | Cligne des yeux (blink moteur) |
| `oui` | Acquiescement vertical |
| `non` | Négation horizontale |
| `hello` | Salutation |
| `think` | Réflexion (mouvement pensif) |
| `reset` | Recentrage à 0° |
| `snap` | Photo RGB → `KinectSnap-DATE.png` |
| `VOICE:texte` | Injection directe dans le pipeline voix (sans micro) |


---

## 🔧 Configuration

### KinectBridge.py

```python
OLLAMA_MDL       = "llama3.2:3b"          # Modèle LLM local
PIPER_MODEL      = r"C:\Kinect\piper\..."  # Voix Jessica
```

Pour changer de voix TTS : modifier `_tts_wait(reply)` → `_tts_wait(reply, neural=True)` (Henri Neural, nécessite internet).

### KinectVoice.py

```python
BIRD_DEVICE_ID = 1      # Index sounddevice du micro
NOISE_FACTOR   = 4.0    # Multiplicateur seuil VAD (augmenter si bruit)
SILENCE_AFTER  = 1.2    # Délai silence fin utterance (secondes)
MODEL_SIZE     = "base" # Modèle Whisper : tiny/base/small/medium
```

### KinectTTS.py

```python
VOICE_INDEX = 0  # pyttsx3 fallback : 0=Hortense FR, 1=Zira EN, 2=David EN
```

---

## 📊 Performances mesurées

| Composant | Latence | Matériel |
|-----------|---------|----------|
| VAD + Whisper base | ~1.5s | RTX 3060 |
| Ollama llama3.2:3b (chaud) | ~3.5s | RTX 3060 |
| Ollama llama3.2:3b (froid) | ~14s | RTX 3060 |
| Piper Jessica (chaud, onnxruntime-gpu) | ~1.2s | RTX 3060 |
| Piper Jessica (froid, chargement) | ~15s | RTX 3060 |
| **Total parole → TTS** | **~6s** | RTX 3060 |

> Warm-up automatique au boot : Ollama + Piper chargés en parallèle, prêts en ~15s.

---

## 🗺️ Roadmap — What's coming

### ✅ Chapitre 0 — Corps & Présence
- Moteur Kinect tilt (haut/bas/gauche/droite)
- Auto-blink aléatoire (4–8s)
- Gestes : oui, non, hello, think, reset
- Snap RGB avec timeout et retry
- Démarrage automatique Windows (Startup)
- Canal cmd.txt pour injection de commandes

### ✅ Chapitre 1 — Voix & Intelligence
- Reconnaissance vocale Whisper base FR (offline)
- VAD RMS avec calibration automatique au boot
- Filtre anti-hallucinations Whisper
- LLM local Ollama llama3.2:3b (~3.5s chaud)
- TTS Piper Jessica fr_FR (~1.2s, offline)
- Warm-up Ollama + Piper au démarrage
- Geste automatique selon le contenu de la réponse

### 🔲 Chapitre 2 — Mémoire conversationnelle
- Historique des 5 derniers échanges dans le contexte Ollama
- Personnalité persistante (Claudius se souvient de la conversation)
- Résumé automatique si contexte trop long

### 🔲 Chapitre 3 — États de présence
- Skeleton tracking Kinect : détecter si quelqu'un est devant
- États : `AWAY` / `PRESENT` / `FOCUS`
- Blink plus lent en mode AWAY, regard vers l'utilisateur en FOCUS
- Salutation automatique à l'approche

### 🔲 Chapitre 4 — Gestes utilisateur
- Détection WAVE (salutation entrante)
- Bras levé = signal d'attention
- Réactions motrices aux gestes détectés

### 🔲 Chapitre 5 — Vision ponctuelle
- `snap` → LLM Vision (LLaVA ou autre via Ollama)
- Claudius décrit ce qu'il voit ("Je vois un homme assis devant un écran...")
- Déclenchable par commande vocale ("qu'est-ce que tu vois ?")

### 🔲 Chapitre 6 — Corps physique
- Bras articulés imprimés en résine (Elegoo Mars)
- Servos pilotés par Arduino ou second canal Kinect
- Gestes bras synchronisés avec la parole

### 💡 Futures idées
- Voix custom entraînée sur un acteur FR (Coqui TTS / RVC)
- Interface web locale pour logs et contrôle réseau
- Mémoire long-terme (résumé de journée → fichier texte lu au boot)
- Détection d'émotions via audio (ton de voix)
- Intégration domotique (MQTT / Home Assistant)


---

## 🐛 Dépannage

### Whisper hallucine ("Merci d'avoir regardé", "... ... ...")
→ Filtre intégré dans `KinectVoice.py`. Augmenter `NOISE_FACTOR` si l'ambiant est bruyant.

### Piper trop lent au démarrage (~15s)
→ Normal, chargement du modèle ONNX. Ensuite ~1.2s/synth. Ne pas tuer le process.

### Ollama ne répond pas
→ Vérifier qu'Ollama tourne : `ollama list`. Relancer : `ollama serve`.

### Kinect non détecté
→ Vérifier SDK 1.8 installé. Brancher **avant** le démarrage de `KinectMotor.exe`.

### Micro non reconnu
→ Lister les devices : `python -c "import sounddevice; print(sounddevice.query_devices())"`.  
   Mettre à jour `BIRD_DEVICE_ID` dans `KinectVoice.py`.

### Tuer les process Python (avant redéploiement)
```cmd
taskkill /F /IM pythonw.exe
```

---

## 📝 Logs

Tous les événements sont loggés dans `kinect.log` (workbench) :

```
[21:17:45] KinectBridge démarrage...
[21:17:57] Chargement Piper Jessica...
[21:18:12] Piper prêt en 14.9s
[21:18:12] Ollama prêt: Bonjour ! Comment puis-je vous aider ?
[VOICE 21:18:18] Écoute active — seuil RMS=180.9
[21:20:31] VOICE reçu: Claudius, présente-toi
[21:20:38] VOICE -> Ollama: Claudius, présente-toi
[21:21:00] VOICE reply: Bonjour, je suis Claudius...
[21:21:07] Piper synth: 1.24s
```

---

## 🧑‍💻 Développement

### Workbench

Le développement se fait dans :
```
C:\Users\PC\Downloads\Claude AI Workbench\kinect\
```

Les fichiers validés sont ensuite copiés dans `C:\Kinect\` (production).

### Workflow de déploiement

```cmd
# 1. Tuer les process en cours
taskkill /F /IM pythonw.exe

# 2. Copier vers production
copy KinectBridge.py C:\Kinect\
copy KinectVoice.py  C:\Kinect\
copy KinectTTS.py    C:\Kinect\

# 3. Relancer
start /MIN C:\Python314\pythonw.exe C:\Kinect\KinectBridge.py
timeout /t 3
start /MIN C:\Python314\pythonw.exe C:\Kinect\KinectVoice.py
```

### Commit

```cmd
cd "C:\Users\PC\Downloads\Claude AI Workbench\kinect"
git add KinectBridge.py KinectVoice.py KinectTTS.py README.md
git commit -m "feat: description du changement"
git push
```

---

## 📜 Licence

MIT — Fais-en ce que tu veux. Un crédit sympa est toujours apprécié.

---

*Claudius v1 — Chapitre 1 complété le 11 mars 2026.*  
*Construit avec ❤️ sur Windows 10, une RTX 3060, et une Kinect rescapée d'une cave.*
