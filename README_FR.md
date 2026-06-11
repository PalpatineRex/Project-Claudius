[English](README.md) · **Français**

# 🤖 Claudius — Votre assistant Kinect IA

**Un compagnon de bureau qui vous écoute, vous répond et bouge la tête !**

Claudius est un assistant vocal physique construit à partir d'un **Kinect v1 de Xbox 360**. Il comprend vos questions, répond à voix haute et hoche la tête comme un vrai pote. Il sent votre présence, s'adapte, et peut même regarder votre bureau.

---

## 🚀 Démarrer Claudius

### Option 1 : Raccourcis (recommandé)
Dans le dossier, utilisez les **raccourcis `.lnk`** (avec les jolies icônes) ou les **`.bat`** directement :

| Raccourci | Action |
|-----------|--------|
| 🟢 `start_all` | **Démarre tout** : Bridge + Dashboard + Voice |
| 🔴 `stop_claudius` | **Arrête** Bridge/Voice/Motor (le dashboard reste) |
| 🟠 `restart_claudius` | **Redémarre** Claudius en entier |
| 🔵 `start_dashboard` | Ouvre le **Dashboard** seul |
| 🔷 `KinectBridge` | Démarre le **Bridge** seul (sans Dashboard) |

### Option 2 : L'exe du Dashboard

Double-cliquez **`ClaudiusDashboard.exe`** — une fenêtre native **sans barre de titre** s'ouvre (pas de navigateur : drag sur la barre du haut, double-clic pour maximiser, attrapez n'importe quel bord pour redimensionner, boutons fenêtre intégrés). Taille et position sont mémorisées — même après un kill. Si le dashboard tourne déjà, ça ouvre juste une nouvelle fenêtre.

---

## 🎯 Ce que Claudius sait faire

| Fonction | Description |
|----------|-------------|
| 🎤 **Reconnaissance vocale** | faster-whisper `medium` (CUDA) — micro choisi **par nom** (insensible au glissement des index USB). Astuce : le **réseau de micros du Kinect** vous entend à travers la pièce |
| ⏱️ **Streaming par phrase** | Il commence à parler dès que la PREMIÈRE phrase est générée (~3 s de latence perçue, contre ~6 avant) |
| 🧠 **Intelligence** | LLM universel — DeepSeek, Anthropic, OpenRouter, OpenAI (streaming sur les providers compatibles OpenAI) |
| 📚 **Hook Cerveau** | Injection optionnelle (lecture seule) de vos fiches projets dans le prompt (anti-invention) — la pill BRAIN affiche l'état |
| 🗣️ **Voix unique** | Blend spectral Jessica + SIWIS — tourne sur **CPU** (aussi rapide que CUDA sur ces modèles, libère ~1 Go de VRAM) |
| 😃 **Gestes** | Oui, non, hello, réflexion — la tête bouge, et le dashboard dit la VÉRITÉ sur la santé du moteur |
| 👀 **Présence** | Claudius sait si vous êtes là, et à quelle distance |
| 📷 **Vision** | « Regarde mon bureau » → il prend une photo et la décrit |
| ⏰ **Utilitaires** | Heure, date, météo, timer, rappels — zéro latence API |
| 🖥️ **Dashboard** | UI temps réel sans bordure : conversation, logs, **vu-mètre micro live**, **moniteur d'impact système** (CPU/RAM/VRAM), pills de statut honnêtes |
| 🎨 **Thèmes** | 16 présets (dont `ambulance 🚑`) + **thèmes custom nommés** (pastilles de couleurs, save/export/import JSON) + effets de fond animés |
| 🌍 **10 langues** | UI du dashboard en FR, EN, ES, DE, IT, PT, RU, JA, ZH, KO |

---

## ⚙️ Configuration LLM

Claudius supporte plusieurs providers. Configurez-les dans **Dashboard > OPTIONS > LLM/IA** :

| Provider | Modèles | Usage |
|----------|---------|-------|
| **deepseek** | `deepseek-v4-flash` (défaut), `deepseek-v4-pro` | Voix — rapide, pas cher, streamé |
| **anthropic** | `claude-haiku-4-5-20251001`, … | Vision (snap) — le seul multimodal garanti |
| **openrouter** | 500+ modèles (format : `provider/modele`) | Accès universel |
| **openai** | `gpt-4o`, etc. | Compatible |

Les clés API se règlent dans le dashboard ou via les fichiers `api_key.txt` (Anthropic) et `deepseek_key.txt` (DeepSeek) à la racine.

---

## 🖥️ Dashboard

- **Topbar** — pills de statut (BRIDGE / VOICE / MOTOR / **BRAIN n** / présence), **vu-mètre micro live** (la barre = le niveau, le trait rouge = le seuil EFFECTIF), **⚡ impact système** (CPU/RAM/VRAM des process Claudius, détail par process au survol), boutons fenêtre
- **Panneau conversation** — bulles de chat en direct David ↔ Claudius
- **Panneau logs** — logs du Bridge, filtrés et colorés
- **Barre de commande** — 💬 Parler (via le LLM) / 📢 Faire dire (TTS brut, sans LLM) / ⚙ Commande (`oui non hello think blink snap sleep wake`) + boutons gestes rapides
- **OPTIONS** — configuration complète :
  - Audio : volume SFX, **sélecteur de micro (par nom)**, seuil (plancher — le vu-mètre montre le vrai), vitesse TTS, modèle Whisper, **mots-clés wake (tags séparés par virgules)**
  - LLM : provider/modèle/clé pour voix et vision, température, tokens, timeout
  - Cerveau : dossier de votre base de connaissances (injection lecture seule)
  - Profils : sauvegarde/chargement de configurations complètes + bouton **DEFAULT** (réglages d'usine)
  - Système : présence, cooldown des salutations, **thème + couleurs custom + effets** (intensité/vitesse), langue
- Toute erreur JS s'affiche en rouge dans la topbar — fini les pannes silencieuses.

---

## 📦 Structure du projet

```
claudius/
├── start_all.bat              ⬅ Tout démarrer (kill ciblé — ne touche jamais les autres Python)
├── stop_claudius.bat          ⬅ Arrêt (Bridge/Voice/Motor)
├── restart_claudius.bat       ⬅ Redémarrage
├── start_dashboard.bat        ⬅ Dashboard seul
├── ClaudiusDashboard.exe      ⬅ Fenêtre dashboard native sans bordure
│
├── KinectBridge.py            🧠 Cerveau : LLM (streaming), pipeline TTS, moteur, utilitaires, hook Cerveau
├── KinectDashboard.py         🖥️ API Flask + fenêtre native (localhost:5005)
├── claudius_dash.html         🎨 UI du dashboard (chargée au runtime : éditable sans rebuild)
├── claudius_i18n.js           🌍 Traductions du dashboard (10 langues)
├── dashboard-fx.js            ✨ Moteur d'effets de fond (partagé avec le dashboard Odysseus)
├── KinectVoice.py             🎤 Reconnaissance vocale (faster-whisper, micro par nom, vu-mètre)
├── KinectMotor.exe            🦾 Daemon moteur Kinect (C#) — erreurs remontées honnêtement
├── KinectMotor.cs             🦾 Source du moteur
│
├── claudius_sfx.py            🔊 Effets sonores (numpy, en RAM)
├── claudius_utils.py          ⏱️ Commandes utilitaires (heure, météo, timers)
├── claudius_blend.py          🎭 Blend vocal (Jessica + SIWIS)
├── claudius_context.txt       📋 Personnalité de Claudius (avec règles anti-invention)
│
├── claudius_settings.json     ⚙️ Config live (relue par le Bridge à chaque appel)
├── claudius_profiles.json     👤 Profils sauvegardés
├── claudius_window.json       📐 Taille/position de la fenêtre
├── memory.json                🧠 Mémoire locale longue durée (résumés de sessions)
│
├── api_key.txt                🔑 Clé API Anthropic
├── deepseek_key.txt           🔑 Clé API DeepSeek
├── piper/                     🗣️ Modèles Piper TTS
└── README_FR.md               👋 Vous êtes ici
```

---

## 🔧 Prérequis

- **Python** 3.10+ (testé sur 3.14) avec pip
- **GPU NVIDIA** recommandé (CUDA pour Whisper — Piper tourne sur CPU par design)
- **Kinect v1 Xbox 360** + Kinect SDK 1.8
- **Micro** : le réseau de 4 micros du Kinect marche très bien à travers la pièce ; n'importe quel micro USB aussi (choisi par nom)
- **Packages Python** : flask, faster-whisper, sounddevice, numpy, scipy, piper-tts, pywebview, psutil, pycaw

## 📋 Infos système

- **Latence** : ~3 à 3,5 secondes perçues (fin de parole → début de réponse) grâce au streaming par phrase
- **Empreinte** : ~1,5 % CPU, ~2 Go RAM, ~750 Mo VRAM (whisper seul — Piper est en CPU)
- **Coût API** : moins de 1 €/mois avec DeepSeek V4 Flash
- **Pipeline** : micro (par nom) → faster-whisper medium → tags wake → Bridge → LLM en stream (+ contexte Cerveau optionnel) → blend Piper phrase par phrase (CPU) → sounddevice → KinectMotor

---

## 🔄 Démarrage automatique

Le raccourci `Claudius.lnk` dans le dossier Startup lance tout au boot de Windows :
```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Claudius.lnk
```
**Pour le retirer** : `Win+R` → `shell:startup` → supprimer `Claudius.lnk`

---

*Fait avec ❤️ par David — Kinect + Python + IA = magie*
