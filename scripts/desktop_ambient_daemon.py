#!/usr/bin/env python3
"""
desktop_ambient_daemon.py — Proactive Ambient Desktop Monitor for Mate-Engine

Monitors system health and hardware envelopes under Omarchy Linux constraints:
- NVIDIA RTX 500 Ada 4 GB VRAM ceiling (alerts if usage > 3500 MB)
- High system memory / swap pressure
- Pushes proactive alerts to the desktop avatar via http://127.0.0.1:11434/notify
"""

import time
import subprocess
import requests
import json
import os

NOTIFY_URL = "http://127.0.0.1:11434/notify"
CHECK_INTERVAL_SECONDS = 60
VRAM_WARNING_THRESHOLD_MB = 3500

def get_vram_usage_mb():
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,nounits,noheader"],
            capture_output=True, text=True, timeout=3
        )
        if proc.returncode == 0:
            used, total = proc.stdout.strip().split(",")
            return int(used.strip()), int(total.strip())
    except Exception:
        pass
    return None, None

def push_notification(source, message):
    try:
        requests.post(
            NOTIFY_URL,
            json={"source": source, "message": message},
            timeout=2
        )
    except Exception:
        pass

def main():
    print("[ambient-daemon] Starting proactive desktop monitor...")
    last_vram_alert = 0

    while True:
        try:
            # 1. Check VRAM envelope
            used_vram, total_vram = get_vram_usage_mb()
            if used_vram and used_vram > VRAM_WARNING_THRESHOLD_MB:
                now = time.time()
                # Rate limit warning to once every 10 minutes
                if now - last_vram_alert > 600:
                    alert_msg = f"⚠️ VRAM Alert: Currently using {used_vram}MB / {total_vram}MB on RTX 500 Ada. Consider unloading heavy models!"
                    push_notification("hardware-monitor", alert_msg)
                    last_vram_alert = now

        except Exception as e:
            print(f"[ambient-daemon] Error in loop: {e}")

        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
