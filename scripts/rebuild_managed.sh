#!/usr/bin/env bash
# ==============================================================================
# Recompile Assembly-CSharp.dll with EmotionDriver and custom patches
# ==============================================================================
set -eo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANAGED_DIR="$PROJECT_DIR/build/MateEngineX_Data/Managed"
PAYLOAD_MANAGED="$PROJECT_DIR/dist/MateEngineX/Payload/MateEngineX_Data/Managed"
SRC_DIR="/tmp/decompiled_assembly"

if [ ! -d "$MANAGED_DIR" ]; then
    echo "[ERROR] Managed directory not found at $MANAGED_DIR" >&2
    exit 1
fi

echo "[1/3] Refreshing custom source files..."
cp "$PROJECT_DIR/Assets/MATE ENGINE - Scripts/AvatarHandlers/EmotionDriver.cs" "$SRC_DIR/"
cp "$PROJECT_DIR/Assets/ollama-unity/ChatOllama.cs" "$SRC_DIR/"

echo "[2/3] Compiling Assembly-CSharp.dll with dotnet..."
dotnet build "$SRC_DIR/Assembly-CSharp.csproj" -c Release > /dev/null

COMPILED_DLL="$SRC_DIR/bin/Release/netstandard2.1/Assembly-CSharp.dll"
if [ ! -f "$COMPILED_DLL" ]; then
    COMPILED_DLL="$SRC_DIR/bin/Debug/netstandard2.1/Assembly-CSharp.dll"
fi

if [ ! -f "$COMPILED_DLL" ]; then
    echo "[ERROR] Compiled DLL not found!" >&2
    exit 1
fi

echo "[3/3] Deploying updated Assembly-CSharp.dll into runtime payload..."
cp -f "$COMPILED_DLL" "$MANAGED_DIR/Assembly-CSharp.dll"
if [ -d "$PAYLOAD_MANAGED" ]; then
    cp -f "$COMPILED_DLL" "$PAYLOAD_MANAGED/Assembly-CSharp.dll"
fi

echo "Successfully recompiled and deployed Assembly-CSharp.dll."
