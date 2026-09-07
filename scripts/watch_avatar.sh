#!/usr/bin/env bash
# ==============================================================================
# MateEngine Live Avatar File Watcher (Instant Hot-Reload)
#
# Watches an avatar file or Avatars/ folder and automatically hot-reloads
# the desktop pet whenever a new model is exported or saved.
# Usage:
#   watch_avatar.sh [path/to/folder_or_vrm]
# ==============================================================================

set -eo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WATCH_TARGET="${1:-$PROJECT_DIR/Avatars}"
PREVIEW_SCRIPT="$PROJECT_DIR/scripts/preview_avatar.sh"

if ! command -v inotifywait >/dev/null 2>&1; then
    echo "[ERROR] inotifywait is required. Please install inotify-tools." >&2
    exit 1
fi

if [ ! -e "$WATCH_TARGET" ]; then
    mkdir -p "$WATCH_TARGET"
fi

echo "======================================================"
echo "          MateEngine Live Avatar Hot-Reload Watcher    "
echo "======================================================"
echo "  -> Watching: $WATCH_TARGET"
echo "  -> Any saved or exported .vrm will reload on screen in <1s!"
echo "  -> Press Ctrl+C to stop watching."
echo "======================================================"

# Initial load
LATEST_VRM=""
if [ -f "$WATCH_TARGET" ]; then
    LATEST_VRM="$WATCH_TARGET"
else
    LATEST_VRM=$(find "$WATCH_TARGET" -name "*.vrm" 2>/dev/null | head -n 1 || true)
fi

if [ -n "$LATEST_VRM" ] && [ -f "$LATEST_VRM" ]; then
    echo "[Watcher] Initializing with: $(basename "$LATEST_VRM")"
    "$PREVIEW_SCRIPT" "$LATEST_VRM"
fi

# Event loop
inotifywait -m -e close_write,moved_to,create --format "%w%f" "$WATCH_TARGET" | while read -r CHANGED_FILE; do
    if [[ "$CHANGED_FILE" == *.vrm ]] || [[ "$CHANGED_FILE" == *.me ]]; then
        echo ""
        echo "[Watcher] Detected change in: $CHANGED_FILE"
        sleep 0.3 # Debounce to let exporter complete file write
        echo "[Watcher] Reloading avatar on screen..."
        "$PREVIEW_SCRIPT" "$CHANGED_FILE"
        echo "[Watcher] Done. Waiting for next change..."
    fi
done
