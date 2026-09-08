#!/usr/bin/env python3
"""
desktop_ambient_daemon.py — Proactive Ambient Desktop Monitor for Mate-Engine

Monitors system health and hardware envelopes under Omarchy Linux constraints:
- NVIDIA RTX 500 Ada 4 GB VRAM ceiling (alerts if usage > 3500 MB)
- High system memory / swap pressure (alerts if RAM+swap used > 90%)
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
MEMORY_PRESSURE_THRESHOLD = 0.90  # (RAM used + swap used) / (RAM total + swap total)

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

def get_memory_pressure():
    """Returns (ram_used_mb, ram_total_mb, swap_used_mb, swap_total_mb) from /proc/meminfo."""
    try:
        info = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                key, _, rest = line.partition(":")
                info[key.strip()] = int(rest.strip().split()[0])  # kB
        ram_total = info.get("MemTotal", 0) // 1024
        ram_avail = info.get("MemAvailable", 0) // 1024
        swap_total = info.get("SwapTotal", 0) // 1024
        swap_free = info.get("SwapFree", 0) // 1024
        ram_used = max(ram_total - ram_avail, 0)
        swap_used = max(swap_total - swap_free, 0)
        return ram_used, ram_total, swap_used, swap_total
    except Exception:
        return None

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
    last_mem_alert = 0

    while True:
        try:
            now = time.time()

            # 1. Check VRAM envelope
            used_vram, total_vram = get_vram_usage_mb()
            if used_vram and used_vram > VRAM_WARNING_THRESHOLD_MB:
                # Rate limit warning to once every 10 minutes
                if now - last_vram_alert > 600:
                    alert_msg = f"⚠️ VRAM Alert: Currently using {used_vram}MB / {total_vram}MB on RTX 500 Ada. Consider unloading heavy models!"
                    push_notification("hardware-monitor", alert_msg)
                    last_vram_alert = now

            # 2. Check RAM + swap pressure
            mem = get_memory_pressure()
            if mem:
                ram_used, ram_total, swap_used, swap_total = mem
                total_pool = ram_total + swap_total
                used_pool = ram_used + swap_used
                if total_pool > 0 and used_pool / total_pool > MEMORY_PRESSURE_THRESHOLD:
                    if now - last_mem_alert > 600:
                        alert_msg = (
                            f"⚠️ Memory Alert: RAM+swap at {used_pool}MB / {total_pool}MB "
                            f"({used_pool * 100 // total_pool}%). RAM {ram_used}MB used, swap {swap_used}MB used."
                        )
                        push_notification("hardware-monitor", alert_msg)
                        last_mem_alert = now

        except Exception as e:
            print(f"[ambient-daemon] Error in loop: {e}")

        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
