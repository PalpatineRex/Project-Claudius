# 🤖 Claudius — Votre assistant Kinect IA

**Un compagnon de bureau qui vous écoute, vous répond et bouge la tête !**

Claudius est un assistant vocal physique construit à partir d'un **Kinect Xbox 360 v1**. Il comprend vos questions, y répond à voix haute, et hoche la tête comme un vrai pote. Il reconnaît votre présence, s'adapte à votre humeur, et peut même regarder votre bureau.

---

## 🚀 Comment lancer Claudius ?

### Option 1 : Raccourcis (recommandé)
Dans le dossier, utilisez les **raccourcis .lnk** (avec les belles icônes) ou les **.bat** directement :

| Raccourci | Action |
|-----------|--------|
| 🟢 `start_all` | **Lance tout** : Bridge + Dashboard + Voice |
| 🔴 `stop_claudius` | **Arrête** Bridge/Voice/Motor (dashboard reste actif) |
| 🟠 `restart_claudius` | **Redémarre** Claudius complet |
| 🔵 `start_dashboard` | Ouvre le **Dashboard** seul |
| 🔷 `KinectBridge` | Lance le **Bridge** seul (sans Dashboard) |

### Option 2 : Dashboard exe

Double-cliquez sur **`ClaudiusDashboard.exe`** — une fenêtre standalone s'ouvre directement (pas de navigateur). Si le dashboard tourne déjà, ça ouvre juste une nouvelle fenêtre sans dupliquer le serveur. La taille et position de la fenêtre sont mémorisées.

### Que fait chaque script ?

- **`start_all.bat`** → Démarre KinectBridge (cerveau) + KinectDashboard (interface web `http://localhost:5005`)
- **`stop_claudius.bat`** → Arrête Bridge + Voice + Motor. Le dashboard reste actif pour voir les statuts (OFF). Un restart depuis le dashboard ou un `start_all` relance tout.
- **`restart_claudius.bat`** → Stop puis Start complet.
- **`start_dashboard.bat`** → Dashboard seul (si le Bridge tourne déjà).

---

## 🎯 Ce que Claudius sait faire

| Fonction | Description |
|----------|-------------|
| 🎤 **Reconnaissance vocale** | Vous parlez, Claudius comprend (micro USB recommandé) |
| 🧠 **Intelligence** | LLM universel — DeepSeek, Anthropic, OpenRouter, OpenAI |
| 🗣️ **Voix blend** | Voix unique (Jessica + SIWIS fusionnées), ~1s pour répondre |
| 😃 **Gestes** | Oui, non, bonjour, réfléchir — la tête Kinect bouge |
| 👀 **Présence** | Claudius sait si vous êtes là, à quelle distance |
| 📷 **Vision** | "Regarde mon bureau" → Claudius prend une photo et décrit |
| ⏰ **Utilitaires** | Heure, date, météo, minuteur, rappels — 0 latence API |
| 🖥️ **Dashboard** | Interface temps réel : conversation, logs, contrôles, 10 thèmes |
| 🌍 **Bilingue** | Interface dashboard FR/EN |

---

## ⚙️ Configuration LLM

Claudius supporte plusieurs providers LLM. Configurez-les dans le **Dashboard > OPTIONS > LLM/IA** :

| Provider | Modèles | Usage |
|----------|---------|-------|
| **deepseek** | `deepseek-v4-flash` (défaut), `deepseek-v4-pro` | Voix — rapide et pas cher |
| **anthropic** | `claude-haiku-4-5-20251001`, `claude-sonnet-4-20250514` | Vision (snap) — seul multimodal garanti |
| **openrouter** | 500+ modèles (format: `provider/modele`) | Accès universel |
| **openai** | `gpt-4o`, etc. | Compatible |

Les clés API se configurent dans le dashboard ou via les fichiers `api_key.txt` (Anthropic) et `deepseek_key.txt` (DeepSeek) à la racine du dossier.

---

## 🖥️ Dashboard

Le dashboard offre une vue temps réel sur Claudius :

- **Panneau conversation** — Transcription live David ↔ Claudius
- **Panneau logs** — Logs Bridge filtrés et colorés par type
- **Contrôles** — Envoi de commandes, restart Bridge
- **OPTIONS** — Configuration complète :
  - Audio : volume SFX, seuil micro, vitesse TTS, modèle Whisper, wake word
  - LLM : provider/modèle/clé pour voix et vision, température, tokens, timeout
  - Profils : sauvegarde/chargement de configurations complètes
  - Système : présence, cooldown, thème (10 thèmes), langue (FR/EN)

### Thèmes disponibles
Dark, Light, Midnight, Matrix, Ember, Cyberpunk, Ocean, Nord, Solar, Synthwave

---

## 📦 Structure du projet

```
claudius/
├── start_all.bat              ⬅ Lance tout
├── stop_claudius.bat          ⬅ Arrête (Bridge/Voice/Motor)
├── restart_claudius.bat       ⬅ Redémarre
├── start_dashboard.bat        ⬅ Dashboard seul
├── ClaudiusDashboard.exe      ⬅ Dashboard standalone (fenêtre native)
│
├── KinectBridge.py            🧠 Cerveau : LLM, voix, moteur, utilitaires
├── KinectDashboard.py         🖥️ Interface web (localhost:5005)
├── KinectVoice.py             🎤 Reconnaissance vocale (faster-whisper)
├── KinectMotor.exe            🦾 Moteur Kinect (C# daemon)
├── KinectMotor.cs             🦾 Source du moteur
│
├── claudius_sfx.py            🔊 Effets sonores (numpy, en RAM)
├── claudius_utils.py          ⏱️ Commandes utilitaires (heure, météo, timers)
├── claudius_blend.py          🎭 Fusion vocale (Jessica + SIWIS)
├── claudius_context.txt       📋 Contexte personnalité de Claudius
│
├── claudius_settings.json     ⚙️ Configuration live (lu par Bridge à chaque appel)
├── claudius_profiles.json     👤 Profils sauvegardés
├── claudius_window.json       📐 Taille/position fenêtre dashboard
├── memory.json                🧠 Mémoire long terme (50 entrées)
│
├── api_key.txt                🔑 Clé API Anthropic
├── deepseek_key.txt           🔑 Clé API DeepSeek
├── piper/                     🗣️ Modèles TTS Piper
└── README.md                  👋 Vous êtes ici
```

---

## 🔧 Prérequis

- **Python** 3.10+ (testé 3.14) avec pip
- **NVIDIA GPU** recommandé (CUDA pour Whisper + voix)
- **Kinect Xbox 360 v1** + Kinect SDK 1.8
- **Micro USB** (Bird UM1 recommandé)
- **Packages Python** : flask, faster-whisper, sounddevice, numpy, scipy, piper-tts

## 📋 Info système

- **Latence** : ~2.5 à 3.5 secondes (fin de parole → début de réponse)
- **Coût API** : ~0.70€/mois avec DeepSeek V4 Flash
- **Pipeline** : Bird UM1 → faster-whisper → wake word → Bridge → LLM → Piper TTS blend → sounddevice → KinectMotor

---

## 🔄 Démarrage automatique

Le raccourci `Claudius.lnk` dans le dossier Démarrage lance tout au boot Windows :
```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Claudius.lnk
```
**Pour le retirer** : `Win+R` → `shell:startup` → supprimez `Claudius.lnk`

---

*Build avec ❤️ par David — Kinect + Python + IA = magie*
