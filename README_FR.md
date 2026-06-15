[English](README.md) · **Français**

# 🤖 Claudius — votre assistant Kinect IA

**Un compagnon de bureau construit à partir d'un Kinect de Xbox 360 qui vous écoute, vous répond à voix haute, hoche la tête, sent votre présence et peut même regarder votre bureau.**

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![C%23 / .NET](https://img.shields.io/badge/C%23-.NET%20Framework%204-512BD4?logo=csharp&logoColor=white)
![Whisper](https://img.shields.io/badge/STT-faster--whisper%20(CUDA)-00A98F)
![Piper](https://img.shields.io/badge/TTS-Piper%20blend-orange)
![Plateforme](https://img.shields.io/badge/Plateforme-Windows%2010%2F11-0078D6?logo=windows&logoColor=white)
![Version](https://img.shields.io/badge/version-v4.2-blue)

Claudius est un **assistant vocal physique et animatronique** détourné d'un **Kinect v1 de Xbox 360**. Dites son mot-clé : il écoute, réfléchit et répond à voix haute dans une voix unique mélangée — puis hoche, secoue ou « réfléchit » de la tête grâce au moteur d'inclinaison du Kinect. Il sait quand vous arrivez au bureau (détection de profondeur du Kinect), et sur demande il prend une photo avec la caméra du Kinect et vous décrit ce qu'il voit.

Il tourne entièrement comme un ensemble de services en arrière-plan sur votre PC, avec un **dashboard d'opérateur sans bordure** soigné pour tout surveiller et configurer en direct.

![Claudius — dashboard d'opérateur](docs/screenshot.png)

---

## ✨ Ce que Claudius sait faire

### 🎤 Il vous entend et répond à voix haute
- **Reconnaissance vocale** avec [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CUDA `float16` sur GPU, repli CPU `int8`). Le micro est choisi **par nom**, pas par index — brancher une manette ou un casque ne le fait donc jamais écouter le mauvais périphérique.
- **Wake word intelligent.** Le nom par défaut est `claudius`, mais vous pouvez lui apprendre une liste de noms séparés par des virgules — y compris des noms **inventés ou en plusieurs mots** comme `le Glaude`. Ils sont injectés dans le prompt de Whisper pour qu'il sache les transcrire. Dites le nom **seul** et il fait un *bip* qui ouvre une **fenêtre de 6 secondes** pour parler sans le répéter.
- **Mode anti-vidéo.** Pendant qu'une musique ou une vidéo sort de vos enceintes, il bascule en mode **strict** — un nom *exact* est exigé : une vidéo YouTube qui dit « Claude » ne le réveille pas, mais votre vraie voix si (pratique pour lui dire de couper la musique).
- **Streaming phrase par phrase.** Il commence à parler dès que la *première* phrase revient du LLM, pendant que le reste est encore généré et synthétisé — la latence perçue est à peu près divisée par deux.
- **Voix unique mélangée.** Deux voix Piper ([upmc / « Jessica »](https://github.com/rhasspy/piper) + SIWIS) sont mélangées spectralement à 50/50 au runtime, sur **CPU** (aussi rapide que CUDA sur ces modèles, et ça libère ~1 Go de VRAM).

### 🗣️ Commandes vocales locales (zéro latence API)
Tout un catalogue de commandes est détecté **localement, avant le moindre appel LLM** — instantané, gratuit et hors ligne. La liste complète est derrière le bouton **🎤 CMDS** du dashboard :

| Catégorie | Exemples |
|-----------|----------|
| ⏰ **Heure & date** | « quelle heure il est », « on est quel jour » |
| 🌦️ **Météo** | « quel temps il fait », « il fait combien dehors » (en direct, [Open-Meteo](https://open-meteo.com/), pour une ville configurable) |
| ⏲️ **Minuteurs & rappels** | « mets un timer de 10 minutes », « minuteur **pâtes** 8 minutes » (plusieurs minuteurs **nommés** en parallèle), « combien de temps il reste », « annule le minuteur pâtes », « rappelle-moi de sortir les poubelles dans 20 minutes » |
| 🔊 **Volume de la voix** | « parle plus fort / moins fort », « volume à 50 pour cent », « volume normal / max / min » (persistant) |
| 🔁 **Répète** | « répète », « qu'est-ce que tu as dit », « j'ai pas compris » |
| ⚡ **État système** | « comment tu te sens », « état système » → il dit son propre CPU / RAM / VRAM / uptime |
| 🎵 **Musique** | « pause la musique », « remets la musique », « piste suivante », « piste précédente » (pilote le lecteur Windows actif via les touches média) |
| 🧮 **Calculs & conversions** | « combien font 17 fois 23 », « 20 pour cent de 150 », « 5 miles en kilomètres », « 100 fahrenheit en celsius » (aussi pouces/cm, pieds/m, kilos/livres) |
| 😴 **Veille / réveil** | « bonne nuit », « tais-toi », « mode silence » → veille ; « Claudius réveille-toi », « debout » → seule phrase écoutée en veille |

Tout ce qui n'est *pas* une commande locale devient une conversation libre via le LLM.

### 😃 Il bouge la tête
Le moteur d'inclinaison du Kinect donne à Claudius un langage corporel, piloté par un petit daemon C# :
- **Gestes** : oui (hoche), non (secoue), bonjour, réflexion, plus un léger **clignement automatique** au repos.
- Il réagit au *contenu* de ses réponses — une réponse qui commence par « oui/absolument » hoche, « non/jamais » secoue, « bonjour/salut » salue, « hmm/intéressant » réfléchit.
- **Statut moteur honnête.** La pill MOTOR du dashboard reflète l'état *réel* du matériel (`daemon` / `legacy` / `error`) — fini les voyants verts au-dessus d'une tête figée. Un watchdog retente le moteur toutes les 5 minutes : si le Kinect revient (alim rebranchée par ex.), il repart tout seul.

### 👀 Il sent votre présence
Grâce au flux de **profondeur** du Kinect, Claudius sait si vous êtes au bureau et à peu près à quelle distance. Il peut vous saluer à votre arrivée (cooldown et heures calmes configurables) et reste silencieux quand vous êtes absent.

### 📷 Il regarde votre bureau (vision)
Dites « regarde », « qu'est-ce que tu vois », « c'est quoi ça » — Claudius prend une image de la caméra RGB du Kinect, l'encode et l'envoie à un modèle multimodal pour comprendre la scène. Un petit aperçu JPG est sauvegardé à côté du PNG complet.

### 🧠 Il se souvient — honnêtement
- **Mémoire locale longue durée.** Quand vous vous éloignez, les conversations récentes sont résumées automatiquement et stockées dans `memory.json` (plafonné), puis réinjectées dans les prompts suivants.
- **Hook « Cerveau » (Brain) optionnel.** Pointez-le vers un dossier de fiches Markdown et, quand vous posez une question sur un projet précis (« où j'en suis sur Eldritch / Odysseus / Aether… »), la fiche pertinente est injectée en lecture seule dans le prompt. La pill BRAIN du dashboard affiche le nombre de projets indexés et la fraîcheur de l'index.
- **Règles anti-invention.** Son fichier de personnalité (`claudius_context.txt`) interdit formellement d'inventer souvenirs, métiers, projets ou faits. S'il ne sait pas, il le dit — c'est la bonne réponse.

### 🖥️ Dashboard d'opérateur
Un panneau de contrôle temps réel sans bordure (voir capture) :
- **Pills de statut** — BRIDGE / VOICE / MOTOR / BRAIN / présence, toutes honnêtes.
- **Vu-mètre micro live** — la barre = le niveau en temps réel, le trait rouge = le seuil *effectif* (le seuil calibré, pas seulement le plancher que vous réglez).
- **⚡ Moniteur d'impact système** — CPU / RAM / VRAM cumulés de tous les process Claudius, avec le détail par process au survol (VRAM lue via les compteurs de perf Windows, car `nvidia-smi` est aveugle à la VRAM par process en mode WDDM).
- Panneaux **conversation & logs**, colorés et filtrés.
- **Barre de commande** — 💬 Parler (via le LLM), 📢 Faire dire (TTS brut, sans LLM), ⚙ Commande (`oui non hello think blink snap sleep wake`), plus des boutons de gestes rapides.
- **Thèmes & effets** — 17 thèmes intégrés (dont `ambulance 🚑`), plus des thèmes **custom nommés** (pastilles de couleurs, save / export / import JSON) et des effets de fond animés.
- **10 langues d'interface** — FR, EN, ES, DE, IT, PT, RU, JA, ZH, KO.
- Toute erreur JavaScript s'affiche en rouge dans la topbar — fini les pannes silencieuses.

---

## 🔧 Matériel nécessaire

| Élément | Notes |
|---------|-------|
| **Kinect v1 de Xbox 360** | Le Kinect d'origine (modèle 1414/1473). Nécessite l'**adaptateur alimentation 12 V + USB** du Kinect (celui livré avec le capteur seul ou le bloc « Kinect for Windows »). |
| **Kinect for Windows SDK 1.8** | Fournit les drivers caméra/profondeur/moteur (`Microsoft.Kinect.dll`, `Kinect10.dll`). [Téléchargement Microsoft](https://www.microsoft.com/en-us/download/details.aspx?id=40278). |
| **Un micro** | Le **réseau de 4 micros** intégré au Kinect marche très bien et vous entend à travers la pièce. N'importe quel micro USB convient aussi — il est choisi **par nom**, donc le modèle exact n'a pas d'importance. |
| **GPU NVIDIA** (recommandé) | CUDA accélère Whisper. Sans GPU, Whisper retombe sur CPU `int8` (plus lent). Le TTS Piper tourne sur CPU par design. |
| **Le moteur d'inclinaison** | Optionnel mais c'est la moitié du plaisir — les gestes et le fait de « regarder » l'utilisent. Tout le reste (voix, vision, présence) fonctionne sans ; le dashboard signale simplement le moteur comme indisponible. |

> Claudius vise **Windows 10 / 11**. Le code moteur/caméra/profondeur repose sur le SDK Kinect 1.8, exclusif à Windows.

---

## 📦 Installation & démarrage

> ℹ️ **Ce dépôt public fournit le code source, pas les binaires.** Les fichiers lourds ou spécifiques à la machine ne sont volontairement pas versionnés : le `KinectMotor.exe` compilé, l'optionnel `ClaudiusDashboard.exe`, les modèles de voix Piper (`piper/`), ainsi que votre config et vos clés locales. Les étapes ci-dessous vous mènent d'un clone vierge à un Claudius opérationnel.

### 1. Installer les dépendances
```bash
pip install flask faster-whisper sounddevice numpy scipy piper-tts pywebview psutil pycaw
```
Il vous faut aussi Python **3.10+** et le **Kinect SDK 1.8** installé.

### 2. Télécharger les voix Piper
La voix mélangée de Claudius utilise deux modèles Piper français. Placez-les sous `piper/` comme ceci (les noms de fichiers doivent correspondre à ce qu'attend `KinectBridge.py`) :
```
piper/
├── fr_FR-upmc-medium.onnx            (+ .onnx.json)
└── siwis/
    └── fr_FR-siwis-medium.onnx       (+ .onnx.json)
```
Les modèles sont disponibles dans le [catalogue de voix Piper](https://github.com/rhasspy/piper/blob/master/VOICES.md). Si le second modèle (SIWIS) manque, Claudius utilise simplement la première voix en solo. Si Piper lui-même ne charge pas, il retombe sur `KinectTTS.py` (SAPI Windows « Hortense », ou `edge-tts` « Henri »).

### 3. Compiler le daemon moteur
`KinectMotor.exe` se compile depuis `KinectMotor.cs` avec le compilateur C# du .NET Framework et l'assembly du Kinect SDK :
```bash
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe ^
  -r:"C:\Program Files\Microsoft SDKs\Kinect\v1.8\Assemblies\Microsoft.Kinect.dll" ^
  -r:System.Drawing.dll KinectMotor.cs
```

### 4. Ajouter vos clés API
Créez deux petits fichiers texte à la racine du projet (les deux sont git-ignorés) :
- `deepseek_key.txt` — votre clé DeepSeek (le provider voix par défaut)
- `api_key.txt` — votre clé Anthropic (utilisée pour la vision / les snaps)

Vous pouvez aussi renseigner les clés plus tard depuis le dashboard. (D'autres providers comme OpenRouter ou OpenAI sont également supportés — voir Configuration.)

### 5. Tout démarrer
Utilisez les `.bat` (ou, sur la machine de David, les raccourcis `.lnk` correspondants avec leurs icônes) :

| Script | Action |
|--------|--------|
| 🟢 `start_all.bat` | **Démarre tout** — Bridge + Dashboard (kill ciblé : ne touche QUE le Python de Claudius, jamais les autres scripts ni les serveurs MCP) |
| 🔴 `stop_claudius.bat` | **Arrête** Bridge / Voice / Motor (le dashboard reste) |
| 🟠 `restart_claudius.bat` | **Redémarre** Claudius |
| 🔵 `start_dashboard.bat` | Ouvre le **dashboard** seul |
| 🔷 `KinectBridge.bat` | Démarre le **Bridge** seul (sans dashboard) |

Le dashboard est accessible sur **http://localhost:5005** (lié à localhost uniquement).

### Optionnel : une fenêtre dashboard autonome
Vous pouvez construire une fenêtre de bureau sans bordure pour le dashboard avec PyInstaller :
```bash
python -m PyInstaller --noconfirm --onefile --noconsole --icon claudius.ico KinectDashboard.py
```
Le `ClaudiusDashboard.exe` obtenu ouvre une **fenêtre native sans bordure** (drag sur la barre du haut, double-clic pour maximiser, attrapez n'importe quel bord pour redimensionner ; boutons de fenêtre intégrés). Sa taille et sa position sont mémorisées — même après un kill brutal — et le HTML/JS sont chargés au runtime, donc vous pouvez retoucher l'UI sans reconstruire l'exe. Si le serveur du dashboard tourne déjà, lancer l'exe ouvre juste une nouvelle fenêtre sans dupliquer le serveur.

### Démarrage automatique au boot (optionnel)
Déposez un raccourci vers `start_all.bat` dans le dossier Démarrage de Windows pour que Claudius se réveille avec le PC :
```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
```
Pour le retirer : `Win+R` → `shell:startup` → supprimez le raccourci.

---

## ⚙️ Configuration

Tout se configure en direct depuis **Dashboard → OPTIONS**, et est persisté dans `claudius_settings.json` (créé à partir de réglages par défaut sensés au premier lancement). La plupart des réglages prennent effet immédiatement ; quelques-uns sont lus au boot — voir la note plus bas.

### Audio
- **Micro (par nom)** — à choisir dans la liste live des périphériques (`/api/devices`). Le choix par nom survit au glissement des index USB.
- **Seuil** — un *plancher* pour le niveau micro ; le vrai seuil est auto-calibré au bruit ambiant et montré en direct par le trait rouge du vu-mètre.
- **Vitesse TTS**, **volume des SFX**, **modèle Whisper** (`tiny` → `large` ; défaut `small`, `medium` recommandé si vous avez la VRAM) et les **mots-clés wake** (tags séparés par virgules).

### LLM / IA
Claudius parle via un LLM configurable et « voit » via un modèle multimodal. Réglez provider + modèle + clé pour chacun, plus température, max tokens et timeout :

| Provider | Modèles d'exemple | Usage typique |
|----------|-------------------|---------------|
| **deepseek** | `deepseek-v4-flash` (défaut) | Voix — rapide, pas cher, streamé |
| **anthropic** | `claude-haiku-4-5-20251001` | Vision (snap) — multimodal |
| **openrouter** | n'importe quel `provider/modele` | Accès universel |
| **openai** | `gpt-4o`, … | Compatible OpenAI |

> Les réponses vocales sont streamées phrase par phrase sur tout provider **compatible OpenAI** (DeepSeek, OpenRouter, OpenAI). Anthropic sert pour la vision et de repli non-streamé. Les clés viennent des champs du dashboard, ou des fichiers `deepseek_key.txt` / `api_key.txt` à la racine.

### Cerveau (optionnel)
Pointez **`brain_path`** vers un dossier de fiches Markdown (un `INDEX.md` à la racine et `projects/<nom>/STATE.md` par projet) pour activer le hook de connaissances en lecture seule.

### Profils & système
- **Profils** — sauvegarde / chargement de configurations complètes, plus un bouton **DEFAULT** (réglages d'usine).
- **Système** — présence on/off, cooldown des salutations, thème + couleurs custom + effets de fond (intensité / vitesse) et langue du dashboard.

> ⚠️ **Ce qui est lu quand :** `claudius_settings.json` est relu à chaque interaction (effet immédiat) **sauf** le micro, le modèle Whisper et les mots-clés wake, qui sont lus au démarrage du process **Voice**. Les changer nécessite un redémarrage — le bouton RESTART du dashboard (et le script de redémarrage) redémarrent volontairement Voice aussi.

---

## 🏗️ Architecture & pipeline

```
micro (choisi par NOM)
  └─► KinectVoice.py ── faster-whisper (CUDA) ── filtre wake-word (fuzzy / strict)
        └─► cmd.txt ──► KinectBridge.py  (le cerveau)
               ├─ commande utilitaire locale ? → claudius_utils.py  (réponse 0 latence)
               ├─ requête vision ?              → KinectMotor.exe snap → image
               └─ sinon → LLM
                     ├─ voix : DeepSeek / OpenRouter / OpenAI (streamé, compatible OpenAI)
                     ├─ vision : Anthropic (multimodal)
                     └─ + fiche [CERVEAU] optionnelle injectée en lecture seule
               └─► blend Piper (Jessica + SIWIS, CPU) ── claudius_blend.py
                     └─► lecture sounddevice
               └─► gestes ──► KinectMotor.exe (moteur d'inclinaison) / présence (profondeur)
```

Le système, c'est quelques process qui coopèrent via de petits fichiers dans le dossier du projet (locks, PID, statut, heartbeats), chacun faisant foi pour sa donnée :

| Fichier | Rôle |
|---------|------|
| **`KinectBridge.py`** | 🧠 Le cerveau. Orchestre tout : appels LLM (streamé + non streamé), le pipeline TTS Piper, les commandes moteur, les commandes utilitaires, le hook Cerveau, la mémoire longue durée, les watchdogs, les salutations de présence, la veille/le réveil. |
| **`KinectVoice.py`** | 🎤 Reconnaissance vocale. Résolution du micro par nom, faster-whisper, le moteur de wake-word (exact / noyau phonétique / phrase multi-mots, mode strict sous audio), l'alimentation du vu-mètre, les filtres anti-hallucination, le heartbeat. |
| **`KinectDashboard.py`** | 🖥️ API Flask + fenêtre native pywebview. Sert le dashboard, expose `/api/*` (stats, logs, transcript, settings, profils, devices, sysload, niveau micro, cmd, restart), relance le Bridge automatiquement s'il meurt. |
| **`claudius_dash.html`** | 🎨 L'UI du dashboard (chargée au runtime — éditable sans rebuild). |
| **`claudius_i18n.js`** | 🌍 Traductions du dashboard (10 langues). |
| **`dashboard-fx.js`** | ✨ Moteur d'effets de fond animés. |
| **`KinectMotor.cs` → `.exe`** | 🦾 Daemon Kinect C# : gestes du moteur d'inclinaison, détection de présence par profondeur, captures RGB. Remonte les échecs honnêtement (vrais HRESULT / codes de sortie). |
| **`claudius_utils.py`** | ⏱️ Commandes locales (heure, date, météo, minuteurs/rappels, volume, musique, calculs, conversions, veille, répète) + ré-accentuation FR pour le TTS + logging. |
| **`claudius_blend.py`** | 🎭 Le blend vocal spectral DTW (Jessica + SIWIS). |
| **`claudius_sfx.py`** | 🔊 Effets sonores synthétiques (boot / présence / écoute / wake / alarme), générés avec numpy et mis en cache en RAM. |
| **`KinectTTS.py`** | 🗣️ TTS de repli (Piper solo, SAPI Windows « Hortense », ou `edge-tts` « Henri »). |
| **`claudius_context.txt`** | 📋 La personnalité de Claudius + les règles strictes de « vérité » anti-invention. |
| `claudius_settings.json` | ⚙️ Config live (relue à chaque appel). *(git-ignoré)* |
| `claudius_profiles.json` | 👤 Profils de configuration sauvegardés. *(git-ignoré)* |
| `claudius_window.json` | 📐 Géométrie de la fenêtre du dashboard. *(git-ignoré)* |
| `memory.json` | 🧠 Mémoire locale longue durée (résumés de sessions). *(git-ignoré)* |
| `presence_config.txt` | 📏 Réglage de la présence par profondeur (min/max mm, seuil de pixels, scan/cooldown). |
| logs & heartbeats | `kinect.log` (partagé, auto-rotationné), `transcript.txt`, `presence.txt`, `motor_status.txt`, `voice_heartbeat.txt`, `voice_level.txt`, `*.pid`, `*.lock`. *(git-ignorés)* |

---

## 🧰 Stack technique

- **Python** (3.10+) — Bridge, Voice, Dashboard, utilitaires.
- **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** — reconnaissance vocale (CUDA `float16` / CPU `int8`).
- **[Piper TTS](https://github.com/rhasspy/piper)** — synthèse vocale neuronale, tournant sur CPU, avec un blend vocal spectral maison (numpy + scipy).
- **Flask** + **pywebview** — le serveur du dashboard et sa fenêtre native sans bordure.
- **sounddevice** + **numpy** — capture et lecture audio, et SFX synthétiques.
- **psutil** + **pycaw** — moniteur d'impact système et détection des sessions audio Windows.
- **C# / .NET Framework** + **Kinect for Windows SDK 1.8** — contrôle caméra, profondeur et moteur d'inclinaison.
- **API LLM** — DeepSeek, Anthropic, OpenRouter, OpenAI (streaming compatible OpenAI).

---

## 🩺 Dépannage / FAQ

**Claudius écoute un périphérique muet / le mauvais micro.**
Sélectionnez toujours le micro **par nom** dans le dashboard, jamais par index. Brancher une manette, un casque ou une webcam décale les index audio : un choix par index glisse silencieusement vers le mauvais périphérique. Le log de Voice affiche `Audio: <nom> (device N)` au démarrage pour vérifier.

**Le Kinect ne se connecte pas.**
Lisez le statut SDK dans `kinect.log` (`sensor: <statut>`) plutôt que de deviner :
- `NotPowered` → l'alimentation **12 V** du Kinect n'est pas branchée (l'USB seul ne suffit pas).
- `InsufficientBandwidth` → un port/contrôleur USB saturé — ou, parfois, un **driver caméra manquant**. Si le Gestionnaire de périphériques affiche un « Xbox NUI Camera » brut au lieu de « Kinect for Windows Camera », réinstallez les drivers du Kinect SDK 1.8.
- `Initializing` est **transitoire** — laissez-lui quelques secondes ; ne concluez jamais « pas de Kinect » à partir de cet état.
Un watchdog retente toutes les 5 minutes : réparer le port/l'alim laisse Claudius repartir sans redémarrage manuel.

**La pill moteur est rouge / la tête ne bouge pas.**
Cela signifie que la commande moteur a vraiment échoué (pas de Kinect, pas de 12 V, souci USB) — le statut est honnête. Vérifiez l'alimentation et le statut SDK ci-dessus.

**Le vu-mètre micro semble figé, ou le dashboard affiche une vieille version.**
Le dashboard lit son HTML/JS au runtime et envoie des en-têtes no-cache, mais WebView2 peut quand même cacher agressivement — relancez la fenêtre (l'exe ajoute un cache-buster à chaque lancement). Si vous avez édité un `.bat`, assurez-vous qu'il est enregistré en fins de ligne **Windows (CRLF)** ; en LF, `cmd` hache les lignes et des étapes sont sautées.

**Comment redémarrer proprement depuis un script ?**
Préférez le bouton **RESTART** du dashboard (ou `POST /api/restart`) : il relance le Bridge, et le watchdog ramène Voice ~30 s plus tard. Le `restart_claudius.bat` est prévu pour un double-clic.

**Une vidéo à l'écran le réveille-t-elle ?**
Tant que du vrai son sort de vos enceintes, Claudius exige le mot-clé **exact** : les vidéos qui ne font que *mentionner* le nom ne le déclenchent pas — mais vous, oui, à la voix.

**Combien ça coûte à faire tourner ?**
La voix passe par un provider bon marché par défaut (DeepSeek V4 Flash). En usage réel, mesuré bien en dessous de 1 €/mois. Empreinte sur la machine de David : environ **1,5 % CPU, ~2 Go RAM, ~0,75–1,4 Go VRAM** (Whisper ; Piper est sur CPU).

---

## 🙏 Crédits

- **Voix** : [Piper](https://github.com/rhasspy/piper) (`fr_FR-upmc` + `fr_FR-siwis`), mélangées au runtime.
- **Reconnaissance vocale** : [faster-whisper](https://github.com/SYSTRAN/faster-whisper).
- **Météo** : [Open-Meteo](https://open-meteo.com/).
- **Matériel/SDK** : Microsoft Kinect for Windows SDK 1.8.

Aucune licence formelle n'est encore attachée — si vous souhaitez réutiliser des parties de Claudius, n'hésitez pas à me contacter.

---

*Fait avec ❤️ par David — Kinect de Xbox 360 + Python + IA = un pote de bureau dont la tête hoche.*
