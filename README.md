**English** · [Français](README_FR.md)

# 🤖 Claudius — Your Kinect AI assistant

**A desk companion that listens to you, talks back, and nods its head!**

Claudius is a physical voice assistant built from an **Xbox 360 Kinect v1**. It understands your questions, answers out loud, and nods like a real buddy. It senses your presence, adapts to your mood, and can even look at your desk.

---

## 🚀 How to start Claudius

### Option 1: Shortcuts (recommended)
In the folder, use the **`.lnk` shortcuts** (with the nice icons) or the **`.bat`** files directly:

| Shortcut | Action |
|-----------|--------|
| 🟢 `start_all` | **Starts everything**: Bridge + Dashboard + Voice |
| 🔴 `stop_claudius` | **Stops** Bridge/Voice/Motor (dashboard stays up) |
| 🟠 `restart_claudius` | **Restarts** the full Claudius |
| 🔵 `start_dashboard` | Opens the **Dashboard** alone |
| 🔷 `KinectBridge` | Starts the **Bridge** alone (no Dashboard) |

### Option 2: Dashboard exe

Double-click **`ClaudiusDashboard.exe`** — a standalone window opens directly (no browser). If the dashboard is already running, it just opens a new window without duplicating the server. Window size and position are remembered.

### What each script does

- **`start_all.bat`** → Starts KinectBridge (the brain) + KinectDashboard (web UI `http://localhost:5005`)
- **`stop_claudius.bat`** → Stops Bridge + Voice + Motor. The dashboard stays up to show statuses (OFF). A restart from the dashboard or a `start_all` brings everything back.
- **`restart_claudius.bat`** → Full Stop then Start.
- **`start_dashboard.bat`** → Dashboard only (if the Bridge is already running).

---

## 🎯 What Claudius can do

| Feature | Description |
|----------|-------------|
| 🎤 **Speech recognition** | You speak, Claudius understands (USB mic recommended) |
| 🧠 **Intelligence** | Universal LLM — DeepSeek, Anthropic, OpenRouter, OpenAI |
| 🗣️ **Blended voice** | A unique voice (Jessica + SIWIS merged), ~1s to reply |
| 😃 **Gestures** | Yes, no, hello, thinking — the Kinect head moves |
| 👀 **Presence** | Claudius knows if you're there, and how far away |
| 📷 **Vision** | "Look at my desk" → Claudius takes a photo and describes it |
| ⏰ **Utilities** | Time, date, weather, timer, reminders — zero API latency |
| 🖥️ **Dashboard** | Real-time interface: conversation, logs, controls, 10 themes |
| 🌍 **Bilingual** | Dashboard UI in FR/EN |

---

## ⚙️ LLM configuration

Claudius supports several LLM providers. Configure them in **Dashboard > OPTIONS > LLM/AI**:

| Provider | Models | Usage |
|----------|---------|-------|
| **deepseek** | `deepseek-v4-flash` (default), `deepseek-v4-pro` | Voice — fast and cheap |
| **anthropic** | `claude-haiku-4-5-20251001`, `claude-sonnet-4-20250514` | Vision (snap) — the only guaranteed multimodal |
| **openrouter** | 500+ models (format: `provider/model`) | Universal access |
| **openai** | `gpt-4o`, etc. | Compatible |

API keys are set in the dashboard or via the `api_key.txt` (Anthropic) and `deepseek_key.txt` (DeepSeek) files at the folder root.

---

## 🖥️ Dashboard

The dashboard gives a real-time view of Claudius:

- **Conversation panel** — Live transcript David ↔ Claudius
- **Logs panel** — Bridge logs, filtered and color-coded by type
- **Controls** — Send commands, restart the Bridge
- **OPTIONS** — Full configuration:
  - Audio: SFX volume, mic threshold, TTS speed, Whisper model, wake word
  - LLM: provider/model/key for voice and vision, temperature, tokens, timeout
  - Profiles: save/load complete configurations
  - System: presence, cooldown, theme (10 themes), language (FR/EN)

### Available themes
Dark, Light, Midnight, Matrix, Ember, Cyberpunk, Ocean, Nord, Solar, Synthwave

---

## 📦 Project structure

```
claudius/
├── start_all.bat              ⬅ Start everything
├── stop_claudius.bat          ⬅ Stop (Bridge/Voice/Motor)
├── restart_claudius.bat       ⬅ Restart
├── start_dashboard.bat        ⬅ Dashboard only
├── ClaudiusDashboard.exe      ⬅ Standalone dashboard (native window)
│
├── KinectBridge.py            🧠 Brain: LLM, voice, motor, utilities
├── KinectDashboard.py         🖥️ Web UI (localhost:5005)
├── KinectVoice.py             🎤 Speech recognition (faster-whisper)
├── KinectMotor.exe            🦾 Kinect motor (C# daemon)
├── KinectMotor.cs             🦾 Motor source
│
├── claudius_sfx.py            🔊 Sound effects (numpy, in RAM)
├── claudius_utils.py          ⏱️ Utility commands (time, weather, timers)
├── claudius_blend.py          🎭 Voice blending (Jessica + SIWIS)
├── claudius_context.txt       📋 Claudius personality context
│
├── claudius_settings.json     ⚙️ Live config (read by Bridge on every call)
├── claudius_profiles.json     👤 Saved profiles
├── claudius_window.json       📐 Dashboard window size/position
├── memory.json                🧠 Long-term memory (50 entries)
│
├── api_key.txt                🔑 Anthropic API key
├── deepseek_key.txt           🔑 DeepSeek API key
├── piper/                     🗣️ Piper TTS models
└── README.md                  👋 You are here
```

---

## 🔧 Requirements

- **Python** 3.10+ (tested on 3.14) with pip
- **NVIDIA GPU** recommended (CUDA for Whisper + voice)
- **Xbox 360 Kinect v1** + Kinect SDK 1.8
- **USB mic** (Bird UM1 recommended)
- **Python packages**: flask, faster-whisper, sounddevice, numpy, scipy, piper-tts

## 📋 System info

- **Latency**: ~2.5 to 3.5 seconds (end of speech → start of reply)
- **API cost**: ~€0.70/month with DeepSeek V4 Flash
- **Pipeline**: Bird UM1 → faster-whisper → wake word → Bridge → LLM → Piper TTS blend → sounddevice → KinectMotor

---

## 🔄 Auto-start

The `Claudius.lnk` shortcut in the Startup folder launches everything at Windows boot:
```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Claudius.lnk
```
**To remove it**: `Win+R` → `shell:startup` → delete `Claudius.lnk`

---

*Built with ❤️ by David — Kinect + Python + AI = magic*
