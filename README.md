# 🤖 Project Claudius

**Tête animatronique Kinect Xbox 360 pilotée par IA — voix blend spectrale, zéro latence.**

Claudius est un compagnon de bureau physique : il écoute, réfléchit, répond à voix haute et bouge la tête. Construit à partir d'un Kinect Xbox 360 v1, piloté par Python et C#, avec reconnaissance vocale (faster-whisper CUDA), intelligence (Claude Haiku API) et synthèse vocale blend (Piper TTS dual-voice spectral).

> *"Alors mon Claudius, c'est quoi mon projet de jeu vidéo déjà ?"*
> *"From The Deep, un platformer style Ghouls'n Ghosts avec du WW2 et du cosmic horror."*

---

## 🎯 Fonctionnalités

- **Reconnaissance vocale** — faster-whisper small CUDA float16, VAD adaptatif, ~0.5s
- **Intelligence conversationnelle** — Claude Haiku API, mémoire 6 échanges, contexte enrichi dynamique
- **Synthèse vocale blend** — Piper TTS Jessica+SIWIS, blend spectral DTW (phase Jessica, magnitudes mixées, consonnes préservées), ~1.1s total
- **Re-accentuation FR** — Correction automatique des accents manquants avant TTS (clavier QWERTY-friendly)
- **Gestes physiques** — Moteur tilt Kinect : oui, non, blink, hello, think, reset
- **Auto-blink** — Clignement naturel toutes les 4-8s
- **Audio intelligent** — sounddevice cross-platform, mute auto quand vidéo/musique joue (pycaw)
- **Anti-hallucination** — Triple filtre : logprob, keywords, pré-filtre RMS
- **Mode veille** — sleep/wake via commande
- **Réactions sonores** — SFX synthétiques numpy (boot jingle, presence chime, listen beep, wake chime, alarm timer), cache RAM
- **Commandes utilitaires** — Heure, date, météo (Open-Meteo), timer, rappel — détection locale, zéro latence API
- **Transcript live** — Interface web temps réel sur `localhost:5005`
- **Chemins portables** — Env vars `CLAUDIUS_*`, tout fonctionne depuis n'importe quel dossier
- **Démarrage automatique** — Se lance au boot Windows

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      CLAUDIUS v3                                 │
├───────────────┬──────────────┬───────────────────┬───────────────┤
│  KinectVoice  │ KinectBridge │ Piper TTS Blend   │ KinectMotor   │
│  (Oreilles)   │  (Cerveau)   │    (Bouche)       │   (Corps)     │
├───────────────┼──────────────┼───────────────────┼───────────────┤
│ faster-whisper │ Claude Haiku │ Jessica+SIWIS     │ C# / SDK 1.8  │
│ small CUDA    │ API Anthropic│ DTW spectral      │ Moteur tilt   │
│ Bird UM1 mic  │ Contexte .txt│ Blend spectral    │ Motor lock    │
│ VAD adaptatif │ 6 échanges   │ Phase Jessica     │ Gestes auto   │
│ Halluc. filter│ Mémoire conv.│ HF preserve       │               │
│ pycaw monitor │ Re-accent FR │ Energy conserv.   │               │
└───────────────┴──────────────┴───────────────────┴───────────────┘
```

### Pipeline voix complet

```
Micro Bird UM1
    │
    ▼
KinectVoice.py
    ├─ VAD adaptatif : max(1000, ambiant × 1.5)
    ├─ faster-whisper small FR (CUDA float16, ~0.5s)
    ├─ Filtre hallucinations (logprob + keywords + 2 mots min)
    ├─ Audio monitor pycaw (mute auto si media joue)
    └─ Écrit VOICE:texte → cmd.txt
                │
                ▼
         KinectBridge.py
                ├─ think (geste Kinect immédiat)
                ├─ Claude Haiku API (~1-2s, contexte enrichi)
                ├─ Geste selon réponse [thread parallèle]
                └─ TTS Blend Pipeline :
                    ├─ Re-accentuation FR (tete → tête, etc.)
                    ├─ Synth parallèle Jessica + SIWIS (~1s, CUDA)
                    └─ Blend spectral v3d (~100ms) :
                        ├─ DTW cosine sur mel features 25ms
                        ├─ Warp continu np.interp
                        ├─ STFT vectorisée
                        ├─ Phase Jessica + magnitudes mixées
                        ├─ Gate silence + HF preserve consonnes
                        ├─ Détecteur de transitoires
                        └─ Conservation d'énergie par frame
                              │
                              ▼
                        sounddevice → Haut-parleurs (RAM, zéro fichier)
```

**Latence totale** : ~2.5-3.5s de fin de parole à début de réponse.

---

## 🔊 Blend Spectral — "Fusion DBZ"

Le système de voix utilise deux modèles Piper TTS (Jessica et SIWIS) fusionnés en temps réel via un algorithme de blend spectral custom :

1. **DTW spectral** — Alignement phonémique par features mel (13 bandes, segments 25ms) avec distance cosine. Pas du simple alignement par volume — on aligne les phonèmes.

2. **Warp continu** — Interpolation linéaire sample-par-sample via `np.interp`. SIWIS est déformée temporellement pour coller exactement à Jessica. Zéro artefacts de Gibbs (pas de FFT resample).

3. **Blend spectral** — STFT vectorisée, phase de Jessica + magnitudes mélangées. Élimine les battements de phase du blend temporel naïf.

4. **Gate silence** — Quand Jessica se tait (fin de mot), le ratio SIWIS tombe à zéro (courbe quadratique). Pas de bruit fantôme.

5. **HF preserve** — Les consonnes (>4kHz) sont dominées par Jessica pour la netteté. SIWIS ne contribue que sur les voyelles et les basses fréquences.

6. **Détecteur de transitoires** — Les frames avec changement rapide d'énergie (consonnes, plosives) forcent Jessica pure. Diction nette.

7. **Conservation d'énergie** — Le volume du blend est normalisé frame-par-frame pour ne jamais être plus faible que Jessica seule.

**Résultat** : une voix unique qui combine le timbre chaud de Jessica et la clarté de SIWIS, avec une diction nette et aucun artefact audible. Blend en ~100ms pour 4s d'audio.

---

## 📁 Structure du projet

```
Project-Claudius/
├── KinectBridge.py      — Cerveau : watcher, API Haiku, TTS blend, re-accent, auto-blink
├── KinectVoice.py       — Oreilles : VAD adaptatif + faster-whisper CUDA + filtres
├── KinectTTS.py         — Bouche standalone : Piper / pyttsx3 / edge-tts (fallback)
├── KinectMotor.cs       — Corps : C# SDK Kinect 1.8, moteur tilt + snap RGB
├── KinectTranscript.py  — Serveur Flask transcript temps réel (localhost:5005)
├── KinectBridge.bat     — Script de démarrage (Bridge + Voice + Transcript)
├── claudius_context.txt — Contexte enrichi pour Haiku (projets, personnalité)
├── voice_blend/         — WAV de référence et tests du blend
├── backup/              — Backups datés de chaque session
├── README.md
└── .gitignore
```

> **Non versionné** : `KinectMotor.exe`, `piper/` (~75MB modèles), `api_key.txt`, logs, PID files.

---

## ⚙️ Prérequis

| Composant | Détail |
|-----------|--------|
| **OS** | Windows 10/11 x64 |
| **Kinect** | Xbox 360 v1 + [SDK 1.8](https://www.microsoft.com/en-us/download/details.aspx?id=44561) |
| **Python** | 3.10+ (testé : 3.14) |
| **GPU** | NVIDIA RTX recommandé (CUDA pour Whisper + Piper) |
| **Micro** | USB externe recommandé (testé : Bird UM1) |
| **API** | Clé API Anthropic ([console.anthropic.com](https://console.anthropic.com)) |

### Dépendances Python

```bash
pip install faster-whisper sounddevice numpy scipy piper-tts onnxruntime-gpu pyttsx3 edge-tts flask pycaw comtypes
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 nvidia-cufft-cu12 nvidia-cuda-runtime-cu12
```

> Sans GPU : remplacer `onnxruntime-gpu` par `onnxruntime`. CPU ~5x plus lent.

---

## 🚀 Installation

### 1. Cloner et installer

```bash
git clone https://github.com/PalpatineRex/Project-Claudius.git
cd Project-Claudius
pip install -r requirements.txt  # si disponible
```

### 2. Clé API Anthropic

Créer `api_key.txt` dans le dossier du projet ou dans `C:\Kinect\` :

```
sk-ant-api03-xxxxxxxxxxxx
```

### 3. Voix Piper (Jessica + SIWIS)

Créer `piper/` et `piper/siwis/` puis télécharger :

**Jessica** (voix principale) :
- [fr_FR-upmc-medium.onnx](https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/upmc/medium/fr_FR-upmc-medium.onnx) → `piper/`
- [fr_FR-upmc-medium.onnx.json](https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/upmc/medium/fr_FR-upmc-medium.onnx.json) → `piper/`

**SIWIS** (voix blend) :
- [fr_FR-siwis-medium.onnx](https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx) → `piper/siwis/`
- [fr_FR-siwis-medium.onnx.json](https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json) → `piper/siwis/`

### 4. Compiler KinectMotor.exe

```cmd
csc.exe /platform:x86 /r:Microsoft.Kinect.dll /r:System.Drawing.dll KinectMotor.cs
```

### 5. Lancer

```bash
python KinectBridge.bat
# ou manuellement :
python KinectBridge.py &
python KinectVoice.py &
python KinectTranscript.py &
```

---

## 📊 Performances (RTX 3060, i5)

| Étape | Durée |
|-------|-------|
| Transcription Whisper small CUDA float16 | ~0.4-0.8s |
| Appel API Claude Haiku | ~1-2s |
| Synthèse Piper dual (Jessica+SIWIS parallèle) | ~1.0s |
| Blend spectral v3d | ~0.1s |
| **Latence totale** (fin parole → début réponse) | **~2.5-3.5s** |

| Ressource | Usage |
|-----------|-------|
| VRAM GPU | ~1.5 GB (Whisper + 2× Piper ONNX) |
| RAM totale | ~1.2 GB |
| Coût API mensuel (50 msg/jour) | ~0.40€ |

---

## 📜 Historique

| Version | Date | Changements |
|---------|------|-------------|
| **v3.5** | **2026-04-02** | **Ch8 Commandes utilitaires** : détection intent locale (heure/date/météo/timer/rappel) avant appel Haiku — zéro latence API. Open-Meteo (Lavelanet). Timers annulables (threading.Event). SFX alarm. Regex robustes tolérants Whisper. **Ch7 Réactions sonores** : 4 SFX synthétiques numpy+sounddevice (boot, presence, listen, wake), cache RAM. **Ch6 Mémoire longue** : résumé sessions via Haiku, memory.json, injection system prompt. |
| v3.3 | 2026-03-31 | **Ch5 Vision snap** : commande vocale → Haiku multimodal base64+texte. **Ch4 Présence Kinect** : daemon Motor C#, depth stream, greetings intelligents (bonjour/retour, cooldown 1h, 5min absence min). Watchdog Motor. | : DTW cosine mel features, warp continu, STFT vectorisée, phase Jessica + magnitudes mixées, gate silence, HF preserve consonnes, détecteur transitoires, conservation énergie. Re-accentuation FR. sounddevice cross-platform. scipy importé au boot. Volume normalisé 31000. |
| v2.5 | 2026-03-18 | Chemins portables (env vars CLAUDIUS_*), clé API fichier>env strip guillemets, CUDA auto-detect site.getsitepackages(), VAD adaptatif, pycaw audio monitor mute auto, system prompt cache mtime, log rotation 500. Premier blend Jessica+SIWIS (scipy.resample + spectral subtraction). |
| v2.0 | 2026-03-18 | faster-whisper small CUDA float16, singleton PID, queue anti-flood, triple filtre hallucination, contexte enrichi dynamique |
| v1.5 | 2026-03-12 | Migration Ollama → API Claude Haiku, Piper TTS Jessica GPU |
| v1.0 | 2026-03-11 | Pipeline voix complet : Whisper + Ollama + pyttsx3 + edge-tts. Gestes, auto-blink, sleep/wake |
| v0.5 | 2026-03-10 | Channel 1 : moteur Kinect, snap RGB, cmd.txt watcher |

---

## 🗺️ Roadmap

- [x] Watchdog Voice crash quand Bridge est relancé
- [x] Détection de présence (skeleton tracking / depth)
- [x] Vision — snap auto → LLM vision
- [x] Mémoire longue — résumé sessions
- [x] Réactions sonores — SFX synthétiques
- [x] Commandes utilitaires — heure, météo, timer, rappels
- [ ] Interface web dashboard
- [ ] Bras imprimés 3D (servos + résine)
- [ ] Voix custom (entraîner un modèle TTS perso)

---

## 📄 Licence

Projet personnel. Code source disponible à titre éducatif.

---

*Built with ❤️ by David — powered by a Kinect, some Python, and a lot of stubbornness.*
