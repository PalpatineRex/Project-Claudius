**English** · [Français](README_FR.md)

# 🤖 Claudius — your Kinect AI assistant

**A desk companion built from an Xbox 360 Kinect that listens to you, talks back, nods its head, senses your presence, and can even look at your desk.**

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![C%23 / .NET](https://img.shields.io/badge/C%23-.NET%20Framework%204-512BD4?logo=csharp&logoColor=white)
![Whisper](https://img.shields.io/badge/STT-faster--whisper%20(CUDA)-00A98F)
![Piper](https://img.shields.io/badge/TTS-Piper%20blend-orange)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6?logo=windows&logoColor=white)
![Version](https://img.shields.io/badge/version-v4.2-blue)

Claudius is a **physical, animatronic voice assistant** repurposed from an **Xbox 360 Kinect v1**. Say his wake word and he listens, thinks, and answers out loud in a unique blended voice — then nods, shakes, or "thinks" with the Kinect's tilt motor. He knows when you walk up to the desk (Kinect depth sensing), and on request he snaps a photo from the Kinect camera and tells you what he sees.

He runs entirely as a set of background services on your PC, with a polished **frameless operator dashboard** to watch and configure everything live.

![Claudius — operator dashboard](docs/screenshot.png)

---

## ✨ What Claudius can do

### 🎤 Hears you and answers out loud
- **Speech recognition** with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CUDA `float16` on GPU, CPU `int8` fallback). The microphone is selected **by name**, not by index — so plugging in a gamepad or headset never makes him listen to the wrong device.
- **Smart wake word.** The default name is `claudius`, but you can teach him a comma-separated list of names — including **made-up or multi-word ones** like `le Glaude`. They're injected into Whisper's prompt so it can actually transcribe them. Say the name **alone** and he chimes (*beep*) and gives you a **6-second window** to speak without repeating it.
- **Anti-TV mode.** While music or a video is playing through your speakers, he switches to **strict** matching — an *exact* name is required, so a YouTube video that says "Claude" can't wake him, but your real voice still can (handy for telling him to pause the music).
- **Sentence-by-sentence streaming.** He starts speaking as soon as the *first* sentence comes back from the LLM, while the rest is still being generated and synthesized — roughly halving the perceived latency.
- **Unique blended voice.** Two Piper voices ([upmc / "Jessica"](https://github.com/rhasspy/piper) + SIWIS) are spectrally blended 50/50 at runtime, on **CPU** (as fast as CUDA on these models, and it frees ~1 GB of VRAM).

### 🗣️ Local voice commands (zero API latency)
A whole catalogue of commands is detected **locally, before any LLM call** — instant, free, and offline. The full list lives behind the **🎤 CMDS** button in the dashboard:

| Category | Examples |
|----------|----------|
| ⏰ **Time & date** | "what time is it", "what day are we" |
| 🌦️ **Weather** | "what's the weather like", "how cold is it outside" (live, [Open-Meteo](https://open-meteo.com/), for a town you configure) |
| ⏲️ **Timers & reminders** | "set a 10-minute timer", "**pasta** timer 8 minutes" (multiple **named** timers in parallel), "how much time is left", "cancel the pasta timer", "remind me to take out the bins in 20 minutes" |
| 🔊 **Voice volume** | "speak louder / quieter", "volume to 50 percent", "volume normal / max / min" (persisted) |
| 🔁 **Repeat** | "repeat", "what did you say", "I didn't catch that" |
| ⚡ **System state** | "how do you feel", "system status" → speaks his own CPU / RAM / VRAM / uptime |
| 🎵 **Music** | "pause the music", "play", "next track", "previous track" (drives the active Windows media player via media keys) |
| 🧮 **Maths & conversions** | "what's 17 times 23", "20 percent of 150", "5 miles in kilometres", "100 fahrenheit in celsius" (also inches/cm, feet/m, kilos/pounds) |
| 😴 **Sleep / wake** | "good night", "be quiet", "silence mode" → sleeps; "Claudius wake up", "get up" → the only phrase heard while asleep |

Anything that *isn't* a local command becomes a free-form conversation through the LLM.

### 😃 Moves its head
The Kinect's tilt motor gives Claudius body language, driven by a small C# daemon:
- **Gestures**: yes (nod), no (shake), hello, thinking, plus a subtle **auto-blink** at rest.
- He reacts to the *content* of his replies — an answer starting with "yes/absolutely" nods, "no/never" shakes, "hello/hi" waves, "hmm/interesting" thinks.
- **Honest motor status.** The dashboard's MOTOR pill reflects the *real* hardware state (`daemon` / `legacy` / `error`) — no more green lights over a frozen head. A watchdog retries the motor every 5 minutes, so if the Kinect comes back (e.g. power reconnected), it recovers on its own.

### 👀 Senses presence
Using the Kinect's **depth** stream, Claudius knows whether you're at the desk and roughly how far away. He can greet you when you arrive (configurable cooldown and quiet hours), and stays quiet when you're away.

### 📷 Looks at your desk (vision)
Say "look", "what do you see", "what's this" — Claudius snaps a frame from the Kinect RGB camera, encodes it, and sends it to a multimodal model to understand the scene. A small JPG preview is saved alongside the full PNG.

### 🧠 Remembers — truthfully
- **Local long-term memory.** When you step away, recent conversations are auto-summarized and stored in `memory.json` (capped), then fed back into future prompts.
- **Optional "Brain" hook.** Point him at a folder of Markdown notes and, when you ask about a specific project ("where am I on Eldritch / Odysseus / Aether…"), the relevant note is injected read-only into the prompt. The dashboard's BRAIN pill shows how many projects are indexed and how fresh the index is.
- **Anti-hallucination rules.** His personality file (`claudius_context.txt`) hard-forbids inventing memories, jobs, projects or facts. If he doesn't know, he says so — that's the correct answer.

### 🖥️ Operator dashboard
A real-time, frameless control panel (see screenshot):
- **Status pills** — BRIDGE / VOICE / MOTOR / BRAIN / presence, all honest.
- **Live mic VU-meter** — the bar is the real-time level, the red tick is the *effective* threshold (the calibrated one, not just the floor you set).
- **⚡ System-impact monitor** — cumulative CPU / RAM / VRAM of all Claudius processes, with per-process detail on hover (VRAM read from Windows performance counters, since `nvidia-smi` is blind to per-process VRAM in WDDM mode).
- **Conversation & logs** panels, color-coded and filtered.
- **Command bar** — 💬 Talk (through the LLM), 📢 Make him say (raw TTS, no LLM), ⚙ Command (`oui non hello think blink snap sleep wake`), plus quick gesture buttons.
- **Themes & FX** — 17 built-in themes (including `ambulance 🚑`), plus named **custom** themes (color pickers, save / export / import JSON) and animated background effects.
- **10 dashboard languages** — FR, EN, ES, DE, IT, PT, RU, JA, ZH, KO.
- Any JavaScript error surfaces in red in the topbar — no silent failures.

---

## 🔧 Hardware needed

| Item | Notes |
|------|-------|
| **Xbox 360 Kinect v1** | The original Kinect (model 1414/1473). Needs the Kinect's **12 V power + USB adapter** (the one that came with the standalone sensor or the "Kinect for Windows" PSU). |
| **Kinect for Windows SDK 1.8** | Provides the camera/depth/motor drivers (`Microsoft.Kinect.dll`, `Kinect10.dll`). [Download from Microsoft](https://www.microsoft.com/en-us/download/details.aspx?id=40278). |
| **A microphone** | The Kinect's built-in **4-mic array** works great and hears you across the room. Any USB mic works too — it's picked **by name**, so the exact model doesn't matter. |
| **NVIDIA GPU** (recommended) | CUDA accelerates Whisper. Without one, Whisper falls back to CPU `int8` (slower). Piper TTS runs on CPU by design. |
| **The tilt motor** | Optional but it's half the fun — gestures and "looking around" use it. Everything else (voice, vision, presence) works without it; the dashboard just reports the motor as unavailable. |

> Claudius targets **Windows 10 / 11**. The motor/camera/depth code is built on the Windows-only Kinect SDK 1.8.

---

## 📦 Installing & running

> ℹ️ **This public repo ships source code, not binaries.** Large or machine-specific files are intentionally not committed: the compiled `KinectMotor.exe`, the optional `ClaudiusDashboard.exe`, the Piper voice models (`piper/`), and your local config and keys. The steps below get you from a fresh clone to a running Claudius.

### 1. Get the dependencies
```bash
pip install flask faster-whisper sounddevice numpy scipy piper-tts pywebview psutil pycaw
```
You'll also need Python **3.10+** and the **Kinect SDK 1.8** installed.

### 2. Download the Piper voices
Claudius's blended voice uses two French Piper models. Place them under `piper/` like so (filenames must match what `KinectBridge.py` expects):
```
piper/
├── fr_FR-upmc-medium.onnx            (+ .onnx.json)
└── siwis/
    └── fr_FR-siwis-medium.onnx       (+ .onnx.json)
```
Models are available from the [Piper voices catalogue](https://github.com/rhasspy/piper/blob/master/VOICES.md). If the second (SIWIS) model is missing, Claudius simply uses the first voice solo. If Piper itself can't load, it falls back to `KinectTTS.py` (Windows SAPI "Hortense", or `edge-tts` "Henri").

### 3. Compile the motor daemon
`KinectMotor.exe` is built from `KinectMotor.cs` with the .NET Framework C# compiler and the Kinect SDK assembly:
```bash
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe ^
  -r:"C:\Program Files\Microsoft SDKs\Kinect\v1.8\Assemblies\Microsoft.Kinect.dll" ^
  -r:System.Drawing.dll KinectMotor.cs
```

### 4. Add your API keys
Create two small text files at the project root (both are git-ignored):
- `deepseek_key.txt` — your DeepSeek key (the default voice provider)
- `api_key.txt` — your Anthropic key (used for vision / snaps)

You can also set keys later from the dashboard. (Other providers like OpenRouter or OpenAI are supported too — see Configuration.)

### 5. Start everything
Use the `.bat` files (or, on David's machine, the matching `.lnk` shortcuts with icons):

| Script | Action |
|--------|--------|
| 🟢 `start_all.bat` | **Starts everything** — Bridge + Dashboard (targeted process kill: it only ever touches Claudius's own Python, never other scripts or MCP servers) |
| 🔴 `stop_claudius.bat` | **Stops** Bridge / Voice / Motor (the dashboard stays up) |
| 🟠 `restart_claudius.bat` | **Restarts** Claudius |
| 🔵 `start_dashboard.bat` | Opens the **dashboard** alone |
| 🔷 `KinectBridge.bat` | Starts the **Bridge** alone (no dashboard) |

The dashboard lives at **http://localhost:5005** (bound to localhost only).

### Optional: a standalone dashboard window
You can build a frameless desktop window for the dashboard with PyInstaller:
```bash
python -m PyInstaller --noconfirm --onefile --noconsole --icon claudius.ico KinectDashboard.py
```
The resulting `ClaudiusDashboard.exe` opens a **native frameless window** (drag the top bar, double-click to maximize, grab any edge to resize; window buttons are built in). Its size and position are remembered — even after a hard kill — and the HTML/JS are loaded at runtime, so you can tweak the UI without rebuilding the exe. If the dashboard server is already running, launching the exe just opens a new window without duplicating the server.

### Auto-start at boot (optional)
Drop a shortcut to `start_all.bat` in your Windows Startup folder so Claudius wakes up with the PC:
```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
```
To remove it: `Win+R` → `shell:startup` → delete the shortcut.

---

## ⚙️ Configuration

Everything is configured live from **Dashboard → OPTIONS**, and persisted to `claudius_settings.json` (created from sensible defaults on first run). Most settings take effect immediately; a few are read at boot — see the note below.

### Audio
- **Microphone (by name)** — pick from the live device list (`/api/devices`). Selecting by name survives USB index drift.
- **Threshold** — a *floor* for the mic level; the real threshold is auto-calibrated to ambient noise and shown live by the VU-meter's red tick.
- **TTS speed**, **SFX volume**, **Whisper model** (`tiny` → `large`; default `small`, `medium` recommended if you have the VRAM), and the **wake words** (comma-separated tags).

### LLM / AI
Claudius speaks through a configurable LLM and "sees" through a multimodal one. Set provider + model + key for each, plus temperature, max tokens and timeout:

| Provider | Example models | Typical use |
|----------|----------------|-------------|
| **deepseek** | `deepseek-v4-flash` (default) | Voice — fast, cheap, streamed |
| **anthropic** | `claude-haiku-4-5-20251001` | Vision (snap) — multimodal |
| **openrouter** | any `provider/model` | Universal access |
| **openai** | `gpt-4o`, … | OpenAI-compatible |

> Voice replies stream sentence-by-sentence on any **OpenAI-compatible** provider (DeepSeek, OpenRouter, OpenAI). Anthropic is used for vision and as a non-streaming fallback. Keys come from the dashboard fields, or from `deepseek_key.txt` / `api_key.txt` at the project root.

### Brain (optional)
Point **`brain_path`** at a folder of Markdown notes (an `INDEX.md` at the root and `projects/<name>/STATE.md` per project) to enable the read-only knowledge hook.

### Profiles & system
- **Profiles** — save / load complete configurations, plus a **DEFAULT** button (factory settings).
- **System** — presence on/off, greeting cooldown, theme + custom colors + background FX (intensity / speed), and dashboard language.

> ⚠️ **What's read when:** `claudius_settings.json` is re-read on every interaction (instant effect) **except** the microphone, Whisper model and wake words, which are read when the **Voice** process starts. Changing those needs a restart — the dashboard's RESTART button (and the restart script) deliberately restart Voice too.

---

## 🏗️ Architecture & pipeline

```
mic (selected by NAME)
  └─► KinectVoice.py ── faster-whisper (CUDA) ── wake-word filter (fuzzy / strict)
        └─► cmd.txt ──► KinectBridge.py  (the brain)
               ├─ local utility command?  → claudius_utils.py  (0-latency reply)
               ├─ vision request?          → KinectMotor.exe snap → image
               └─ otherwise → LLM
                     ├─ voice: DeepSeek / OpenRouter / OpenAI (streamed, OpenAI-compatible)
                     ├─ vision: Anthropic (multimodal)
                     └─ + optional [BRAIN] note injected read-only
               └─► Piper blend (Jessica + SIWIS, CPU) ── claudius_blend.py
                     └─► sounddevice playback
               └─► gestures ──► KinectMotor.exe (tilt motor) / presence (depth)
```

The system is a few cooperating processes talking through small files in the project folder (locks, PIDs, status, heartbeats), each as the single source of truth:

| File | Role |
|------|------|
| **`KinectBridge.py`** | 🧠 The brain. Orchestrates everything: LLM calls (streaming + non-streaming), the Piper TTS pipeline, motor commands, the utility commands, the Brain hook, long-term memory, watchdogs, presence greetings, sleep/wake. |
| **`KinectVoice.py`** | 🎤 Speech recognition. Mic-by-name resolver, faster-whisper, the wake-word engine (exact / phonetic-core / multi-word phrase, strict mode under audio), the VU-meter feed, anti-hallucination filters, heartbeat. |
| **`KinectDashboard.py`** | 🖥️ Flask API + native pywebview window. Serves the dashboard, exposes `/api/*` (stats, logs, transcript, settings, profiles, devices, sysload, mic level, cmd, restart), auto-restarts the Bridge if it dies. |
| **`claudius_dash.html`** | 🎨 The dashboard UI (loaded at runtime — edit without rebuilding). |
| **`claudius_i18n.js`** | 🌍 Dashboard translations (10 languages). |
| **`dashboard-fx.js`** | ✨ Animated background-FX engine. |
| **`KinectMotor.cs` → `.exe`** | 🦾 C# Kinect daemon: tilt-motor gestures, depth-based presence detection, RGB snapshots. Reports failures honestly (real HRESULT / exit codes). |
| **`claudius_utils.py`** | ⏱️ Local commands (time, date, weather, timers/reminders, volume, music, maths, conversions, sleep, repeat) + French re-accentuation for the TTS + logging. |
| **`claudius_blend.py`** | 🎭 The spectral DTW voice-blend (Jessica + SIWIS). |
| **`claudius_sfx.py`** | 🔊 Synthetic sound effects (boot / presence / listen / wake / alarm), generated with numpy and cached in RAM. |
| **`KinectTTS.py`** | 🗣️ Fallback TTS (Piper solo, Windows SAPI "Hortense", or `edge-tts` "Henri"). |
| **`claudius_context.txt`** | 📋 Claudius's personality + the strict anti-hallucination "truth" rules. |
| `claudius_settings.json` | ⚙️ Live config (re-read on every call). *(git-ignored)* |
| `claudius_profiles.json` | 👤 Saved configuration profiles. *(git-ignored)* |
| `claudius_window.json` | 📐 Dashboard window geometry. *(git-ignored)* |
| `memory.json` | 🧠 Local long-term memory (session summaries). *(git-ignored)* |
| `presence_config.txt` | 📏 Depth presence tuning (min/max mm, pixel threshold, scan/cooldown). |
| logs & heartbeats | `kinect.log` (shared, auto-rotated), `transcript.txt`, `presence.txt`, `motor_status.txt`, `voice_heartbeat.txt`, `voice_level.txt`, `*.pid`, `*.lock`. *(git-ignored)* |

---

## 🧰 Tech stack

- **Python** (3.10+) — Bridge, Voice, Dashboard, utilities.
- **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** — speech recognition (CUDA `float16` / CPU `int8`).
- **[Piper TTS](https://github.com/rhasspy/piper)** — neural text-to-speech, run on CPU, with a custom spectral voice blend (numpy + scipy).
- **Flask** + **pywebview** — the dashboard server and its native frameless window.
- **sounddevice** + **numpy** — audio capture, playback and synthetic SFX.
- **psutil** + **pycaw** — system-impact monitoring and Windows audio-session sensing.
- **C# / .NET Framework** + **Kinect for Windows SDK 1.8** — camera, depth and tilt-motor control.
- **LLM APIs** — DeepSeek, Anthropic, OpenRouter, OpenAI (OpenAI-compatible streaming).

---

## 🩺 Troubleshooting / FAQ

**Claudius hears a muted device / the wrong mic.**
Always select the microphone **by name** in the dashboard, never by index. Plugging in a gamepad, headset or webcam shifts the audio indices, so an index-based pick silently moves to the wrong device. The Voice log prints `Audio: <name> (device N)` at startup so you can confirm.

**The Kinect won't connect.**
Read the SDK status in `kinect.log` (`sensor: <status>`) instead of guessing:
- `NotPowered` → the Kinect's **12 V** power isn't connected (USB alone isn't enough).
- `InsufficientBandwidth` → a saturated USB port/controller — or, occasionally, a **missing camera driver**. If Device Manager shows a raw "Xbox NUI Camera" instead of "Kinect for Windows Camera", reinstall the Kinect SDK 1.8 drivers.
- `Initializing` is **transient** — give it a few seconds; never conclude "no Kinect" from it.
A watchdog retries every 5 minutes, so fixing the port/power lets Claudius recover without a manual restart.

**The motor pill is red / the head doesn't move.**
That means the motor command genuinely failed (no Kinect, no 12 V, USB issue) — the status is honest. Check power and the SDK status above.

**The mic VU-meter looks stuck, or the dashboard shows an old version.**
The dashboard reads its HTML/JS at runtime and sends no-cache headers, but WebView2 can still cache aggressively — relaunch the window (the exe appends a cache-buster on each launch). If you edited a `.bat` file, make sure it's saved with **Windows (CRLF)** line endings; with LF endings `cmd` mangles the lines and steps get skipped.

**How do I restart cleanly from a script?**
Prefer the dashboard's **RESTART** button (or `POST /api/restart`): it restarts the Bridge, and the watchdog brings Voice back ~30 s later. The `restart_claudius.bat` is meant for a double-click.

**Does a video on my screen wake him up?**
While real sound is coming out of your speakers, Claudius requires the **exact** wake word, so videos that merely *mention* the name won't trigger him — but you still can, by voice.

**How much does it cost to run?**
Voice runs through a cheap provider by default (DeepSeek V4 Flash). Real-world usage measured well under €1/month. Footprint on David's machine: roughly **1.5 % CPU, ~2 GB RAM, ~0.75–1.4 GB VRAM** (Whisper; Piper is CPU).

---

## 🙏 Credits

- **Voices**: [Piper](https://github.com/rhasspy/piper) (`fr_FR-upmc` + `fr_FR-siwis`), blended at runtime.
- **Speech recognition**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper).
- **Weather**: [Open-Meteo](https://open-meteo.com/).
- **Hardware/SDK**: Microsoft Kinect for Windows SDK 1.8.

No formal license is attached yet — if you'd like to reuse parts of Claudius, please reach out.

---

*Built with ❤️ by David — Xbox 360 Kinect + Python + AI = a desk buddy with a head that nods.*
