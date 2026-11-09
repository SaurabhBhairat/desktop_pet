# Baby Dragon

A small 3D purple baby dragon that lives on your Windows desktop. It wanders, flies, sleeps, shows moods
(happy, sad, sleepy...), follows your mouse with its eyes, and you can talk to it. Everything runs
**locally and offline**: speech recognition (Whisper), the chat brain (Qwen through Ollama) and the voice.

## Features
- Transparent always-on-top 3D dragon (PySide6 + three.js) that moves on its own
- Needs and moods: it gets tired, lonely and happy depending on how you treat it
- Talk to it: double-click the dragon (or press ENTER in the console)
- System tray icon, hide/show hotkeys, quits itself after an hour hidden to save battery
- Settings panel (right-click > Settings...): Talk / Type / Both, mouse look and chase, quiet hours,
  how often it starts a chat

## Hotkeys
| Keys | What it does |
|------|--------------|
| Ctrl + Alt + A | show the dragon (or start it, with the Windows shortcut key) |
| Ctrl + Alt + C | hide the dragon |

## Install (Windows 10/11)
1. Install Python 3.10+ and [Ollama](https://ollama.com).
2. In this folder:
   ```
   python -m venv voice_env
   .\voice_env\Scripts\python.exe -m pip install -r requirements.txt
   ollama pull qwen2.5:1.5b
   ```
3. **Add your own dragon model.** The 3D model is not included. Put a `.glb` file at
   `assets\models\baby_dragon_idle.glb`. An optional front-view picture of the dragon can be turned into a skin:
   ```
   .\voice_env\Scripts\python.exe make_texture.py "C:\path\to\dragon_picture.png"
   ```
4. Start it:
   ```
   .\voice_env\Scripts\python.exe run_dragon.py
   ```
   or double-click `Start Dragon (no window).bat`.

The Whisper speech model downloads itself on first use.

## Project layout
- `run_dragon.py` - starts the window and the voice assistant
- `voice/dragon_window.py` - the transparent window, 3D rendering, tray and hotkeys
- `voice/dragon_brain.py` - needs, moods and decisions
- `voice/dragon_settings.py` - the settings panel
- `voice/assistant_voice.py` and friends - microphone, speech-to-text, Qwen, text-to-speech
- `make_texture.py` - builds the skin from a picture

## Credits
Dragon model generated with [Meshy](https://www.meshy.ai) (credit required on the free plan).
