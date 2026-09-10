# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An unofficial Linux port of [MateEngine](https://github.com/shinyflvre/Mate-Engine) — a free desktop-pet application with custom VRM support. It is a **Unity 6000.2.6f2** project (desktop pet renders as a transparent window over the desktop, X11/XWayland) plus a thin **Python agent/bridge layer** added by this port (`mate_bridge.py`, `scripts/`, `ecosystem.config.js`). The app talks to the bridge over HTTP; the bridge talks to local AI (Ollama on the NVIDIA GPU, or the Antigravity CLI `agy`).

Unity version is pinned: `ProjectSettings/ProjectVersion.txt` → **6000.2.6f2**. Don't open/rebuild with a different Editor.

## Language

- **Use only English** in all code, comments, commit messages, documentation, and responses. The upstream README ships a Simplified Chinese section; do not reproduce or respond in Chinese.

## Common commands

```bash
# Build the player via CLI (Option 2 in README; the "safe" path is Unity Editor GUI, build name MateEngineX.x86_64)
./build.sh /path/to/output            # requires ~/Unity/Hub/Editor/6000.2.6f2/Editor/Unity; runs CliBuilder.Build

# Native plugin — MUST be compiled by hand (security); .so is not checked in
make -C Plugins/StandaloneFileBrowser
#    then copy libStandaloneFileBrowser.so → Assets/MATE ENGINE - Packages/StandaloneFileBrowser/Plugins/Linux/x86_64/
#   (kdotool is a Rust crate: cargo build --release in Plugins/kdotool-main)

# Full rebuild + launch sequence (kill → clean → rebuild plugins → launch built player)
./launch.sh

# Agent stack (pm2): Flask bridge + ambient health daemon
pm2 startOrReload ecosystem.config.js   # apps: mate-bridge, mate-ambient; logs in logs/
pm2 logs mate-bridge                    # pm2 restart mate-bridge / pm2 stop mate-bridge …

# System install (non-Arch): ./install.sh ; uninstall: ./install.sh --uninstall
# Arch users: yay -S mateengine

# Avatar iteration (no full Unity rebuild — hot-reload into the running build)
./scripts/preview_avatar.sh [model.vrm] [--foreground|-f]   # switch avatar + refresh pet
./scripts/watch_avatar.sh [dir-or-vrm]                       # inotify hot-reload on save
./scripts/rebuild_managed.sh                                 # recompile Assembly-CSharp.dll (see below)
```

There is **no automated test suite** in this repo. "Verification" happens through the read-only `avatar-workflow-verifier` subagent spec (`scripts/agent_dispatcher.py avatar-workflow-verifier …`) and by launching `build/MateEngineX.x86_64` after a build.

## Architecture

### Unity app (the desktop pet)

The whole game is in `Assets/`, organized into `MATE ENGINE - *` modules (Scripts, Scenes, Avatar, Sounds, Props, Mod SDK, Shaders, System Tray, …). Notable third-party systems: VRM/VRM10 + UniGLTF (custom avatars), `ollama-unity` and `LLMUnity` (in-app AI chat), DiscordRPC, uWindowCapture, DynamicBone, UMotionEditor, lilToon/Mochie shaders, AddressableAssets (localization). The Linux port centers on `Assets/MATE ENGINE - Scripts/VRMLoader`, `Settings/` (persisted to `~/.config/unity3d/Shinymoon/MateEngineX/settings.json`, read by `scripts/preview_avatar.sh`), and `AvatarHandlers/EmotionDriver.cs` (recompiled out-of-band by `rebuild_managed.sh`).

Build output lands in `build/` and is packaged to `dist/` (both gitignored; they exist only locally).

### Python bridge / agent layer (the Linux port)

- **`mate_bridge.py`** — Flask app on `127.0.0.1:11434` (override with `MATE_BRIDGE_HOST` and `MATE_BRIDGE_PORT`; defaults remain `127.0.0.1:11434`) with a catch-all streaming route. Hybrid intent routing: _fast tier_ for casual banter/greetings streams from local **Ollama on `127.0.0.1:11435`** (`OLLAMA_REAL_URL`); _deep tier_ for actionable/`/system`/`/see`/coding forwards to the **Antigravity CLI (`agy`)** with the last 6 SQLite turns injected for context and a timeout so no `agy` orphan survives. Also `POST /notify` (used by the ambient daemon) and proactive re-delivery of undelivered notifications. Persists `conversation_turns` + `system_notifications` to `data/mate_memory.db` (SQLite, gitignored, recreated on start). Screen capture uses `hyprctl` + `grim` and deliberately skips the MateEngineX window when targeting the active app (Hyprland/Omarchy host).
- **`scripts/desktop_ambient_daemon.py`** — 60s health poll (VRAM via `nvidia-smi`, memory/swap via `/proc/meminfo`); pushes `POST http://127.0.0.1:11434/notify` when over budget (VRAM >3500 MB on the 4 GB RTX 500 Ada; RAM+swap >90%).
- **`requirements.txt`** — pins the Python dependencies used by the bridge and agent scripts.
- **`scripts/smoke_test.py`** — lightweight smoke tests for a live bridge; run with `python3 scripts/smoke_test.py`.
- **`scripts/agent_dispatcher.py`** — `dispatch_agent(agent_name, input_payload, timeout_seconds=90)`. Resolves an agent spec from, in order: `.agents/subagents/<name>.md` → `.agents/<name>.md` → `~/.agents/agents/<name>/agent.md` → `~/.agents/agents/<name>.md`, then runs it gated by that spec's declared model/temperature/tool permissions.
- **`.agents/subagents/`** — seven specs implementing the **fast-turnaround VRM avatar pipeline** (planner, rigging, mesh/texture, animation/blendshape researchers, synthesizer, implementer, verifier). Written per the 9 Core Agent Setup Pillars; scoped to not touch `.git/`, `build/`, `Library/`.
- **`ecosystem.config.js`** — pm2 definitions for the two daemons above.

### Key constraints

- **4 GB VRAM** (RTX 500 Ada): local LLMs must stay ≤3B, 4–5-bit quantized (e.g. `qwen2.5:3b`). The AI chat GGUF (`llama-3.2-3b-instruct-q4_k_m.gguf`) must sit next to the executable.
- Native plugins are **built by hand** (StandaloneFileBrowser `.so`, kdotool binary) — never checked in.
- `rebuild_managed.sh` needs a decompiled `Assembly-CSharp` dotnet project already present at `/tmp/decompiled_assembly` (out-of-band setup) — it patches `EmotionDriver.cs`/`ChatOllama.cs`, builds with `dotnet`, and deploys the DLL into `build/` and `dist/` payloads.
- XWayland limitations: window snapping and dock-sitting don't work. Mods do not load correctly yet.
- `AssetBundles/`, `Avatars/*.vrm`, `ExportedMods/`, and `Thry/` are runtime/user content shipped with the repo, not build artifacts — don't "clean" them.
- **Runtime payload fallback**: When Unity Editor 6000.2.6f2 is absent, extract the release tarball (`MateEngineX_3.2.0_6.tar.gz`) to `dist/MateEngineX/Payload/` — `launch.sh` automatically deploys it into `build/`.
- **Plugin layout**: Deploy `libStandaloneFileBrowser.so` into both `build/MateEngineX_Data/Plugins/` and `.../Plugins/x86_64/`.
- **Hyprland floating rule**: Declared in `~/.config/hypr/hyprland.lua` as `o.window({ class = ".*(?i)mateengine.*" }, { float = true })` so the desktop pet never tiles.
