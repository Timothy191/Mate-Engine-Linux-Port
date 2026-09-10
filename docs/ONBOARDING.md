# 🚀 MateEngine Linux Port — Onboarding Guide

An unofficial Linux port of [MateEngine](https://github.com/shinyflvre/Mate-Engine): a
free desktop-pet application with custom VRM support. Built on **Unity 6000.2.6f2** with
a thin Python agent/bridge layer added by this port.

This document lists the **required actions** to get a working development/runtime
environment. The canonical runbook lives in `CLAUDE.md`; this file is the checklist form.

---

## 0. Target Environment (this machine)

- **OS:** Omarchy Linux (Arch), Hyprland/Wayland. Also tested on Ubuntu 24.04 LTS & Fedora 43+ (X11 + compositing).
- **GPUs:**
  - iGPU: Intel Arrow Lake-P (i915) — drives the Wayland compositor.
  - dGPU: NVIDIA RTX 500 Ada (4 GB VRAM, Driver 610.57.04, CUDA 13.3) — used for local AI.
- **Display:** Dual monitor (`eDP-1` 1920x1200, `HDMI-A-1` 1920x1080) @ 60 Hz. Bar reserves 36 px at top.
- **Hyprland floating rule** (already declared in `~/.config/hypr/hyprland.lua`):
  ```lua
  o.window({ class = ".*(?i)mateengine.*" }, { float = true })
  ```

> ⚠️ **VRAM budget:** 4 GB total. Local LLMs must stay ≤3B params, 4–5-bit quantized
> (`qwen2.5:3b`, `phi-3.5:mini`, `qwen2.5:0.5b`). Never run unquantized 7B+ directly.

---

## 1. System Library Prerequisites

### All distros (X11 + compositing + tray support)

- GTK3, glib2, libayatana-appindicator, libpulse / pipewire-pulse
- X11 libs: `libx11 libxext libxrender libxdamage libxcursor libxrandr libxcomposite`

### Install commands

```bash
# Debian/Ubuntu
sudo apt install --noconfirm --needed libpulse0 libgtk-3-0t64 libglib2.0-0t64 \
  libayatana-appindicator3-1 libx11-6 libxext6 libxrender1 libxdamage1 \
  libxcursor1 libxrandr2 libxcomposite1

# Fedora
sudo dnf install --noconfirm pulseaudio-libs gtk3 glib2 libX11 libXExt libXrender \
  libXrandr libXdamage libXcursor libXcomposite libayatana-appindicator-gtk3

# Arch
sudo pacman -S --noconfirm --needed libpulse gtk3 glib2 libx11 libxext libxrender \
  libxrandr libxdamage libxcursor libxcomposite libayatana-appindicator
```

### GNOME-only

Install the [AppIndicator and KStatusNotifierItem Support extension](https://extensions.gnome.org/extension/615/appindicator-support/)

---

## 2. Tooling Dependencies

| Tool                                | Why                                                                                               | Install                                                                                                                   |
| ----------------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **Unity Hub + Editor** `6000.2.6f2` | Builds the desktop-pet player via `CliBuilder.Build`. Pinned version — do not use another.        | Unity Hub → install `6000.2.6f2` to `~/Unity/Hub/Editor/6000.2.6f2/Editor/`. Verify `ProjectSettings/ProjectVersion.txt`. |
| **Python 3.10+**                    | Runs the Flask/FastAPI bridge, ambient daemon, tests, subagent dispatcher.                        | `python3` (system) + project venv at `.venv/`; install pinned packages with `python -m pip install -r requirements.txt`.  |
| **Node.js + npm**                   | Required for `pm2` (agent-stack daemon supervisor).                                               | `npm install -g pm2`                                                                                                      |
| **cmake / gcc / make**              | Compiles the **StandaloneFileBrowser** native plugin (`.so`, not checked in).                     | `pacman -S cmake gcc` / `apt install cmake build-essential`                                                               |
| **Rust (cargo)**                    | Builds `kdotool` (window geometry / input helper, not checked in).                                | `pacman -S rust` / `apt install cargo`                                                                                    |
| **Ollama**                          | Local LLM backend for in-app AI chat + fast-tier bridge banter. Must listen on `127.0.0.1:11435`. | `systemctl start ollama` (config `OLLAMA_REAL_URL`).                                                                      |
| **Antigravity CLI (`agy`)**         | Deep-tier agentic actions + subagent dispatch via `agent_dispatcher.py`.                          | Provided by the Antigravity agent framework on `$PATH`.                                                                   |
| **GGUF chat model**                 | In-app AI chat. File name is case-sensitive.                                                      | Place `llama-3.2-3b-instruct-q4_k_m.gguf` next to the executable.                                                         |

> **Non-Arch install:** run `./install.sh` (auto-detects Debian/Fedora). Arch users: `yay -S mateengine`.

---

## 3. Native Plugins — MUST be built by hand (not checked in)

These are intentionally excluded from git for security reasons. Build and deploy to two locations.

```bash
# 3a. StandaloneFileBrowser native plugin (.so)
make -C Plugins/StandaloneFileBrowser
# Deploy to BOTH the Unity project tree and the runtime build dir:
cp Plugins/StandaloneFileBrowser/build/libStandaloneFileBrowser.so \
   "Assets/MATE ENGINE - Packages/StandaloneFileBrowser/Plugins/Linux/x86_64/"
mkdir -p build/MateEngineX_Data/Plugins/x86_64
cp Plugins/StandaloneFileBrowser/build/libStandaloneFileBrowser.so \
   build/MateEngineX_Data/Plugins/
cp Plugins/StandaloneFileBrowser/build/libStandaloneFileBrowser.so \
   build/MateEngineX_Data/Plugins/x86_64/

# 3b. kdotool (Rust window-input helper)
cargo build --release --manifest-path Plugins/kdotool-main/Cargo.toml
cp Plugins/kdotool-main/target/release/kdotool build/
```

> `.gitignore` excludes `Assets/MATE ENGINE - Packages/StandaloneFileBrowser/Plugins/Linux/` and `build/`.

---

## 4. Runtime Build Options

### Option 1 — Unity Editor GUI (recommended / safest)

Open the project in Unity 6000.2.6f2, build the player, executable name **`MateEngineX.x86_64`**.
Output → `build/`.

### Option 2 — CLI build (debug only; may show abnormal behaviour)

```bash
./build.sh /path/to/output        # produces MateEngineX.x86_64
```

Requires `${UNITY_PATH:-$HOME/Unity/Hub/Editor/6000.2.6f2/Editor/Unity}`.

### Option 3 — No Unity Editor installed (runtime bundle only)

Extract the release tarball to the payload location `launch.sh` expects:

```bash
mkdir -p dist/MateEngineX/Payload
tar -xzf dist/MateEngineX_3.2.0_6.tar.gz -C dist/MateEngineX/Payload --strip-components=1
```

`launch.sh` auto-deploys `dist/MateEngineX/Payload/.` into `build/` when Unity is absent.

---

## 5. Agent Stack (pm2)

Two daemons, defined in `ecosystem.config.js`:

```bash
pm2 startOrReload ecosystem.config.js --update-env
pm2 save   # persist across logins
pm2 list   # should show mate-bridge + mate-ambient
```

| Daemon           | Role                                                                                                                                                         | Port              | Interpreter                             |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------- | --------------------------------------- |
| **mate-bridge**  | FastAPI ↔ MateEngine bridge. Routes Ollama chat, Antigravity (`agy`) agentic actions, `/see`/`/look` vision, notifications. Persists SQLite episodic memory. | `127.0.0.1:11434` | `.venv/bin/python` (fallback `python3`) |
| **mate-ambient** | 60 s health poll: VRAM via `nvidia-smi` (>3500 MB warning), RAM+swap (`>90%` warning). Uses async `httpx` (not `requests`) to push `POST /notify` to the bridge. | —                 | `python3`                               |

Logs → `logs/mate-bridge.{out,err}.log`, `logs/mate-ambient.{out,err}.log`.

> The bridge injects `num_ctx: 2048` on all forwarded Ollama payloads to protect the 4 GB VRAM ceiling.
> Screen capture uses `hyprctl` + `grim` and deliberately skips the `MateEngineX` window.

---

## 6. Launch the Desktop Pet

```bash
./launch.sh             # full sequence: kill → clean → rebuild plugins → pm2 → health → launch
```

`./scripts/preview_avatar.sh` switches the active avatar, reading/writing
`~/.config/unity3d/Shinymoon/MateEngineX/settings.json` (`selectedModelPath`).

---

## 7. Development & Iteration Workflow

```bash
# Hot-reload a new/changed VRM into the running pet (no Unity rebuild)
./scripts/preview_avatar.sh Avatars/Zome.vrm
./scripts/watch_avatar.sh          # watches Avatars/ for saves

# Recompile patched managed DLLs (EmotionDriver.cs / ChatOllama.cs)
# REQUIRES a decompiled Assembly-CSharp proj at /tmp/decompiled_assembly
./scripts/rebuild_managed.sh

# Dispatch an autonomous subagent (9-pillar spec)
python3 scripts/agent_dispatcher.py avatar-workflow-verifier '{"task_id":"..."}'
```

Run `python3 scripts/smoke_test.py` against a live bridge to exercise `/health`,
SQLite initialization, `/notify`, and streaming `/api/chat` routing.

### Subagents (`.agents/subagents/`)

Seven specs implementing the fast-turnaround VRM avatar pipeline. Each follows the **9 Core Agent Setup Pillars** (identity/routing, runtime envelope, tool sandbox, scope isolation, phased lifecycle, hard negatives, input/output contracts, error/recovery).

| Subagent                                 | Role                                                      |
| ---------------------------------------- | --------------------------------------------------------- |
| `avatar-pipeline-planner`                | Designs zero-rebuild hot-reload architecture (read-only). |
| `avatar-asset-fetcher`                   | Gathers reference assets/meshes (read-only).              |
| `avatar-rigging-researcher`              | 17-bone universal VRM humanoid rig analysis.              |
| `avatar-mesh-texture-researcher`         | Mesh + PBR/emissive material research.                    |
| `avatar-animation-blendshape-researcher` | Idle/anim/blendshape binding research.                    |
| `avatar-research-synthesizer`            | Assembles findings into a build spec.                     |
| `avatar-preview-implementer`             | Scoped writes: deploys `.vrm` + mutates `settings.json`.  |
| `avatar-workflow-verifier`               | Read-only validation of the running pipeline.             |

---

## 8. Key Paths & Constraints (quick reference)

- **Unity version (pinned):** `ProjectSettings/ProjectVersion.txt` → `6000.2.6f2`.
- **Unity expected location:** `~/Unity/Hub/Editor/6000.2.6f2/Editor/Unity`.
- **Bridge endpoint:** `http://127.0.0.1:11434` (override with `MATE_BRIDGE_HOST` and `MATE_BRIDGE_PORT`; defaults remain `127.0.0.1:11434`; Ollama upstream: `127.0.0.1:11435`).
- **AI chat GGUF:** `llama-3.2-3b-instruct-q4_k_m.gguf` beside the executable.
- **Ephemeral/runtime (gitignored):** `build/`, `dist/`, `logs/`, `data/mate_memory.db`, `.venv/`, `Library/`, `Temp/`, `target/`.
- **Do NOT "clean":** `AssetBundles/`, `Avatars/*.vrm`, `ExportedMods/`, `Thry/` are runtime/user content shipped with the repo.
- **Known limitations:** window snapping/dock-sitting don't work on XWayland; mods don't load correctly yet; Steam workshop/NAudio/UniWindowController were removed.

---

## 9. Onboarding Checklist (todo)

- [ ] Install system libraries (Section 1).
- [ ] Install Unity 6000.2.6f2 via Hub (Section 2).
- [ ] Create `.venv` and install `fastapi uvicorn httpx starlette` (Section 2).
- [ ] `npm install -g pm2` (Section 2).
- [ ] Install cmake/gcc + Rust cargo (Section 2).
- [ ] Start Ollama on `127.0.0.1:11435`; place GGUF chat model next to the build (Section 2).
- [ ] Build native plugins: `make -C Plugins/StandaloneFileBrowser` + `cargo build --release` in `Plugins/kdotool-main` (Section 3).
- [ ] Build the player: Unity Editor **or** `./build.sh` **or** prepare `dist/MateEngineX/Payload/` (Section 4).
- [ ] `pm2 startOrReload ecosystem.config.js` → confirm `mate-bridge` + `mate-ambient` running (Section 5).
- [ ] `./launch.sh` → confirm the desktop pet launches (Section 6).
- [ ] (Optional) Run `python3 scripts/agent_dispatcher.py avatar-workflow-verifier '{}'` (Section 7).
