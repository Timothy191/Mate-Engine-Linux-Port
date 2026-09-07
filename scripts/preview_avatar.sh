#!/usr/bin/env bash
# ==============================================================================
# MateEngine Instant Avatar Preview
#
# Switches avatar and refreshes on-screen desktop pet instantly with 0 rebuild delay.
# Usage:
#   preview_avatar.sh [path/to/avatar.vrm] [--foreground|-f]
# ==============================================================================

set -eo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="$HOME/.config/unity3d/Shinymoon/MateEngineX/settings.json"
BUILD_EXE="$PROJECT_DIR/build/MateEngineX.x86_64"

# 1. Resolve Target Model
TARGET_MODEL="$1"
FOREGROUND=false

if [[ "$1" == "--foreground" ]] || [[ "$1" == "-f" ]]; then
    TARGET_MODEL=""
    FOREGROUND=true
elif [[ "$2" == "--foreground" ]] || [[ "$2" == "-f" ]]; then
    FOREGROUND=true
fi

if [ -z "$TARGET_MODEL" ]; then
    if [ -f "$PROJECT_DIR/Avatars/current_model.vrm" ]; then
        TARGET_MODEL="$PROJECT_DIR/Avatars/current_model.vrm"
    else
        # Find first VRM in Avatars or sample directory
        TARGET_MODEL=$(find "$PROJECT_DIR/Avatars" -name "*.vrm" 2>/dev/null | head -n 1)
        if [ -z "$TARGET_MODEL" ]; then
            TARGET_MODEL="$PROJECT_DIR/Assets/MATE ENGINE - Avatar/Zome.vrm"
        fi
    fi
fi

if [ ! -f "$TARGET_MODEL" ]; then
    echo "[ERROR] Avatar model file not found: $TARGET_MODEL" >&2
    exit 1
fi

ABS_MODEL_PATH="$(realpath "$TARGET_MODEL")"
echo "======================================================"
echo "          MateEngine Instant Avatar Preview           "
echo "======================================================"
echo "  -> Target Model: $ABS_MODEL_PATH"

# 2. Update settings.json with selectedModelPath
python3 -c "
import json, os, sys
cfg_path = os.path.expanduser('$CONFIG_FILE')
os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
data = {}
if os.path.exists(cfg_path):
    try:
        with open(cfg_path, 'r') as f:
            data = json.load(f)
    except Exception:
        data = {}
data['selectedModelPath'] = sys.argv[1]
with open(cfg_path, 'w') as f:
    json.dump(data, f, indent=2)
" "$ABS_MODEL_PATH"
echo "  -> settings.json updated (selectedModelPath set)."

# 3. Ensure Build Executable Exists (copy once from Payload if missing)
if [ ! -f "$BUILD_EXE" ]; then
    echo "  -> Initializing build directory from precompiled payload..."
    mkdir -p "$PROJECT_DIR/build"
    cp -r "$PROJECT_DIR/dist/MateEngineX/Payload/." "$PROJECT_DIR/build/"
    chmod +x "$BUILD_EXE"
fi

# 4. Stop Any Active Instance
if pgrep -fi "MateEngineX" > /dev/null 2>&1; then
    echo "  -> Cycling active instance..."
    pkill -f "MateEngineX" 2>/dev/null || true
    for i in {1..10}; do
        if ! pgrep -fi "MateEngineX" > /dev/null 2>&1; then break; fi
        sleep 0.1
    done
    if pgrep -fi "MateEngineX" > /dev/null 2>&1; then
        pkill -9 -f "MateEngineX" 2>/dev/null || true
    fi
fi

# 5. Environment & Visual ID Setup for Transparency
export GDK_BACKEND=x11
if [[ "$XDG_SESSION_DESKTOP" == *"Hyprland"* ]] || [[ "$XDG_CURRENT_DESKTOP" == *"Hyprland"* ]]; then
    export XDG_BACKEND=x11
    export SDL_VIDEODRIVER=x11
fi

visual_id=$(python3 -c "
import ctypes
from ctypes import *
class XVisualInfo(Structure):
    _fields_ = [('visual', c_void_p), ('visualid', c_ulong), ('screen', c_int), ('depth', c_int)]
try:
    x11 = cdll.LoadLibrary('libX11.so.6')
    x11.XOpenDisplay.restype = c_void_p
    disp = x11.XOpenDisplay(None)
    if disp:
        t = XVisualInfo(depth=32)
        n = c_int(0)
        x11.XGetVisualInfo.restype = POINTER(XVisualInfo)
        vl = x11.XGetVisualInfo(c_void_p(disp), 4, byref(t), byref(n))
        if vl and n.value > 0:
            print(f'0x{vl[0].visualid:x}')
except Exception:
    pass
" 2>/dev/null || true)

if [ -n "$visual_id" ]; then
    export SDL_VIDEO_X11_VISUALID="$visual_id"
fi

# 6. Launch Instantly
cd "$PROJECT_DIR/build"
if [ "$FOREGROUND" = true ]; then
    echo "  -> Launching in foreground mode..."
    exec ./MateEngineX.x86_64
else
    nohup ./MateEngineX.x86_64 > "$PROJECT_DIR/mateengine.log" 2>&1 &
    PID=$!
    disown $PID 2>/dev/null || true
    echo "  -> Avatar live on screen! (PID: $PID)"
    echo "  -> Instant reload time: < 1 second"
fi
