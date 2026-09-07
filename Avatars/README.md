# 🎭 MateEngine Avatar Rapid-Iteration Pipeline

This workspace provides a **Zero-Rebuild** hot-reloading pipeline for developing, testing, and previewing VRM avatars instantly on Linux (Hyprland/Wayland & X11).

---

## ⚡ Instant Model Preview (< 1 second)

Whenever you have a `.vrm` file ready to test, run:

```bash
mateengine-preview path/to/your_model.vrm
```

Or pick one of the bundled models:
```bash
mateengine-preview Avatars/Aldina.vrm
mateengine-preview Avatars/Lazuli.vrm
mateengine-preview Avatars/Zome.vrm
```

This bypasses the slow multi-minute Unity project rebuild:
1. Immediately writes your model path into `settings.json`
2. Preserves transparent XWayland/Hyprland window compositing
3. Renders your updated model on your desktop in **under 1.2 seconds**.

---

## 🔄 Live Auto-Reload Watcher (Hot-Reload on Save)

If you are sculpting, rigging, texturing, or modifying blendshapes in **Blender**, **VRoid Studio**, or **Blockbench**:

1. Run the live watcher:
   ```bash
   mateengine-watch
   ```
   *(Or specify a folder: `mateengine-watch /path/to/export/folder`)*

2. Export your model as `.vrm` into `Avatars/` (e.g. `Avatars/my_model.vrm`).
3. **The moment your exporter finishes writing the file, MateEngine automatically refreshes your on-screen desktop pet!**

---

## 🛠 Model Requirements & Tips
* **Formats Supported**: `.vrm` (VRM 0.x and VRM 1.0), `.me` (custom AssetBundles).
* **Bones & Tracking**: Ensure the model humanoid rig has Head, Neck, Chest, Spine, and Eyes mapped if you want mouse tracking and idle glances.
* **Blendshapes**: Standard VRM expressions (`Joy`, `Angry`, `Sorrow`, `Fun`, `Surprised`, `Blink`, `A`, `I`, `U`, `E`, `O`) are dynamically mapped by MateEngine's `BlendshapeManager`.
* **Audio & Dancing**: Custom models will automatically dance to system music when dance mode is triggered!
