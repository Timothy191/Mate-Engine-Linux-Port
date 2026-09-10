#!/usr/bin/env python3
"""
desktop_ambient_daemon.py — Proactive Ambient Desktop Monitor for Mate-Engine

Monitors system health and hardware envelopes under Omarchy Linux constraints:
- NVIDIA RTX 500 Ada 4 GB VRAM ceiling (alerts if usage > 3500 MB)
- High system memory / swap pressure (alerts if RAM+swap used > 90%)
- Pushes proactive alerts to the desktop avatar via the bridge notify endpoint.
"""

import asyncio
import subprocess
import httpx
import os
import time

NOTIFY_URL = os.getenv("MATE_BRIDGE_URL", "http://127.0.0.1:11434") + "/notify"
CHECK_INTERVAL_SECONDS = 60
VRAM_WARNING_THRESHOLD_MB = 3500
MEMORY_PRESSURE_THRESHOLD = 0.90

async def push_notification(source: str, message: str):
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(NOTIFY_URL, json={"source": source, "message": message})
    except Exception:
        pass

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
    try:
        info = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                key, _, rest = line.partition(":")
                info[key.strip()] = int(rest.strip().split()[0])
        ram_total = info.get("MemTotal", 0) // 1024
        ram_avail = info.get("MemAvailable", 0) // 1024
        swap_total = info.get("SwapTotal", 0) // 1024
        swap_free = info.get("SwapFree", 0) // 1024
        ram_used = max(ram_total - ram_avail, 0)
        swap_used = max(swap_total - swap_free, 0)
        return ram_used, ram_total, swap_used, swap_total
    except Exception:
        return None

async def main():
    print("[ambient-daemon] Starting proactive desktop monitor...")
    last_vram_alert = 0.0
    last_mem_alert = 0.0

    while True:
        try:
            now = time.monotonic()

            used_vram, total_vram = get_vram_usage_mb()
            if used_vram and used_vram > VRAM_WARNING_THRESHOLD_MB:
                if now - last_vram_alert > 600:
                    alert_msg = f"VRAM Alert: Currently using {used_vram}MB / {total_vram}MB on RTX 500 Ada. Consider unloading heavy models!"
                    await push_notification("hardware-monitor", alert_msg)
                    last_vram_alert = now

            mem = get_memory_pressure()
            if mem:
                ram_used, ram_total, swap_used, swap_total = mem
                total_pool = ram_total + swap_total
                used_pool = ram_used + swap_used
                if total_pool > 0 and used_pool / total_pool > MEMORY_PRESSURE_THRESHOLD:
                    if now - last_mem_alert > 600:
                        alert_msg = (
                            f"Memory Alert: RAM+swap at {used_pool}MB / {total_pool}MB "
                            f"({used_pool * 100 // total_pool}%). RAM {ram_used}MB used, swap {swap_used}MB used."
                        )
                        await push_notification("hardware-monitor", alert_msg)
                        last_mem_alert = now

        except Exception as e:
            print(f"[ambient-daemon] Error in loop: {e}")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    asyncio.run(main())
