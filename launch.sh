#!/usr/bin/env bash
# ==============================================================================
# MateEngine Complete Update, Clean & Launch Script
#
# Sequence:
#   1. Kill any existing instances
#   2. Cleanup caches, temporary build files, and old builds
#   3. Rebuild native plugins and update the application
#   4. Set up compositor/display environment and launch the new build
# ==============================================================================

set -eo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "======================================================"
echo "          MateEngine Rebuild & Launch Sequence        "
echo "======================================================"

# ----------------------------------------------------
# 1. Kill any currently running instances
# ----------------------------------------------------
echo "[1/4] Checking and terminating running instances..."
if pgrep -fi "MateEngineX" > /dev/null 2>&1 || pgrep -x "mateengine" > /dev/null 2>&1; then
    echo "  -> Stopping active MateEngine processes..."
    pkill -f "MateEngineX" 2>/dev/null || true
    pkill -x "mateengine" 2>/dev/null || true
    pkill -f "mate_bridge.py" 2>/dev/null || true
    pkill -f "desktop_ambient_daemon.py" 2>/dev/null || true
    sleep 1
    if pgrep -fi "MateEngineX" > /dev/null 2>&1; then
        echo "  -> Force-killing remaining processes..."
        pkill -9 -f "MateEngineX" 2>/dev/null || true
    fi
    echo "  -> All previous instances stopped."
else
    echo "  -> No running MateEngine processes found."
fi

# ----------------------------------------------------
# 2. Cleanup caches, temporary files, and old build
# ----------------------------------------------------
echo "[2/4] Cleaning caches and removing old build artifacts..."
rm -rf "$PROJECT_DIR/Temp" "$PROJECT_DIR/Library/ScriptAssemblies" 2>/dev/null || true
rm -f "$PROJECT_DIR"/*.log 2>/dev/null || true

if [ -d "$PROJECT_DIR/build" ]; then
    echo "  -> Removing old build directory ($PROJECT_DIR/build)..."
    rm -rf "$PROJECT_DIR/build"
fi
mkdir -p "$PROJECT_DIR/build"
echo "  -> Clean build workspace initialized."

# ----------------------------------------------------
# 3. Rebuild native plugins & build/update application
# ----------------------------------------------------
echo "[3/4] Rebuilding plugins and updating application..."

# 3a. Rebuild StandaloneFileBrowser native library
if [ -d "$PROJECT_DIR/Plugins/StandaloneFileBrowser" ]; then
    echo "  -> Rebuilding native StandaloneFileBrowser plugin..."
    make -C "$PROJECT_DIR/Plugins/StandaloneFileBrowser" > /dev/null 2>&1 || true
    PLUGIN_TARGET="$PROJECT_DIR/Assets/MATE ENGINE - Packages/StandaloneFileBrowser/Plugins/Linux/x86_64"
    mkdir -p "$PLUGIN_TARGET"
    if [ -f "$PROJECT_DIR/Plugins/StandaloneFileBrowser/build/libStandaloneFileBrowser.so" ]; then
        cp -f "$PROJECT_DIR/Plugins/StandaloneFileBrowser/build/libStandaloneFileBrowser.so" "$PLUGIN_TARGET/"
        echo "  -> Updated native libStandaloneFileBrowser.so deployed."
    fi
fi

# 3b. Build with Unity Editor (if installed) or update runtime bundle
UNITY_BIN="${UNITY_PATH:-$HOME/Unity/Hub/Editor/6000.2.6f2/Editor/Unity}"
BUILD_EXE="$PROJECT_DIR/build/MateEngineX.x86_64"

if [ -x "$UNITY_BIN" ]; then
    echo "  -> Unity Editor found at $UNITY_BIN. Compiling fresh player..."
    "$UNITY_BIN" -batchmode -quit -nographics \
        -projectPath "$PROJECT_DIR" \
        -executeMethod CliBuilder.Build \
        --output "$BUILD_EXE"
    echo "  -> Unity build completed successfully."
elif [ -d "$PROJECT_DIR/dist/MateEngineX/Payload" ]; then
    echo "  -> Deploying updated runtime bundle into build directory..."
    cp -r "$PROJECT_DIR/dist/MateEngineX/Payload/." "$PROJECT_DIR/build/"
    cp -f "$PROJECT_DIR/mate_bridge.py" "$PROJECT_DIR/build/" 2>/dev/null || true
    cp -rf "$PROJECT_DIR/scripts" "$PROJECT_DIR/build/" 2>/dev/null || true
    if [ -f "$PROJECT_DIR/Plugins/StandaloneFileBrowser/build/libStandaloneFileBrowser.so" ]; then
        mkdir -p "$PROJECT_DIR/build/MateEngineX_Data/Plugins/x86_64"
        cp -f "$PROJECT_DIR/Plugins/StandaloneFileBrowser/build/libStandaloneFileBrowser.so" "$PROJECT_DIR/build/MateEngineX_Data/Plugins/x86_64/" 2>/dev/null || true
    fi
    echo "  -> Application bundle prepared at $PROJECT_DIR/build."
else
    echo "  [ERROR] Neither Unity Editor ($UNITY_BIN) nor dist/Payload was found!"
    exit 1
fi

chmod +x "$BUILD_EXE" 2>/dev/null || true

# ----------------------------------------------------
# 4. Environment setup and launch
# ----------------------------------------------------
echo "[4/4] Setting environment variables and launching MateEngine..."

export GDK_BACKEND=x11
if [[ "$XDG_SESSION_DESKTOP" == *"Hyprland"* ]] || [[ "$XDG_CURRENT_DESKTOP" == *"Hyprland"* ]]; then
    echo "  -> Hyprland detected: applying XWayland transparency variables."
    export XDG_BACKEND=x11
    export SDL_VIDEODRIVER=x11
fi

visual_id=""
if command -v glxinfo >/dev/null 2>&1; then
    visual_id=$(glxinfo 2>/dev/null | grep -i "32 tc  0  32  0 r  y .   8  8  8  8 .  .   0 24  8" | head -n1 | awk '{print $1}')
    if [ -z "$visual_id" ]; then
        visual_id=$(glxinfo 2>/dev/null | grep -i "32 tc  0  32  0 r  y" | head -n1 | awk '{print $1}')
    fi
fi

if [ -z "$visual_id" ] && command -v xdpyinfo >/dev/null 2>&1; then
    visual_id=$(xdpyinfo 2>/dev/null | grep -A 2 "visual id" | grep -B 5 "depth:.* .*32 planes" | grep "visual id" | awk '{print $3}' | head -n1)
fi

if [ -z "$visual_id" ] && command -v python3 >/dev/null 2>&1; then
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
fi

if [ -n "$visual_id" ]; then
    echo "  -> ARGB Visual ID configured: $visual_id"
    export SDL_VIDEO_X11_VISUALID="$visual_id"
fi

echo "  -> Starting Antigravity CLI Proxy Bridge..."
nohup python3 "$PROJECT_DIR/mate_bridge.py" > "$PROJECT_DIR/bridge.log" 2>&1 &

echo "  -> Starting Proactive Desktop Ambient Monitor..."
nohup python3 "$PROJECT_DIR/scripts/desktop_ambient_daemon.py" > "$PROJECT_DIR/scripts/ambient.log" 2>&1 &

cd "$PROJECT_DIR/build"

if [[ "$1" == "--foreground" ]] || [[ "$1" == "-f" ]]; then
    echo "  -> Starting in foreground mode..."
    exec ./MateEngineX.x86_64 "${@:2}"
else
    echo "  -> Starting in background mode..."
    nohup ./MateEngineX.x86_64 "$@" > "$PROJECT_DIR/mateengine.log" 2>&1 &
    PID=$!
    echo "  -> MateEngine running with PID: $PID"
    echo "  -> Log file: $PROJECT_DIR/mateengine.log"
fi

echo "======================================================"
echo "          MateEngine Launch Completed                 "
echo "======================================================"
