"""
mate_bridge.py — Hardened Antigravity ↔ MateEngine Hybrid Multi-Agent Bridge

Architectural Amendments:
  1. Hybrid Multi-Tier Intent Routing:
     - Fast Tier (<300ms): Casual banter/greetings route to local GPU Ollama on 11435.
     - Deep Tier (Agentic): Actionable directives, /system, /see, and coding route to Antigravity CLI.
  2. Episodic Context Injection (Anti-Amnesia):
     - Injects the last 6 conversation turns from SQLite into the Antigravity prompt payload.
  3. Smart Non-Avatar Hyprland Grounding:
     - Automatically skips MateEngineX when capturing screen; targets the actual active application.
  4. Proactive Alert Delivery:
     - Undelivered system notifications in SQLite are automatically prepended to the speech stream.
  5. Process Timeouts & Graceful Termination:
     - Prevents orphaned agy processes using strict execution boundaries.
"""

import json
import os
import sqlite3
import subprocess
import time
import requests
from flask import Flask, request, Response, stream_with_context

app = Flask(__name__)
OLLAMA_REAL_URL = "http://127.0.0.1:11435"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "mate_memory.db")

# ─────────────────────────────────────────────────────────────
# 1. SQLite Persistent Episodic Memory & Notification Storage
# ─────────────────────────────────────────────────────────────
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                role TEXT NOT NULL,
                content TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS system_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                source TEXT,
                message TEXT,
                delivered INTEGER DEFAULT 0
            )
        """)
        conn.commit()

init_db()

def log_memory(role, content):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO conversation_turns (role, content) VALUES (?, ?)", (role, content))
            conn.commit()
    except Exception as e:
        print(f"[bridge:memory] DB log error: {e}")

def get_recent_context(limit=6):
    """Fetches recent conversation turns to cure turn-by-turn amnesia."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT role, content FROM conversation_turns ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            if not rows:
                return ""
            # Invert to chronological order
            ordered = reversed(rows)
            formatted = ["--- RECENT CONVERSATION CONTEXT ---"]
            for role, text in ordered:
                snippet = text.strip().replace("\n", " ")
                if len(snippet) > 150:
                    snippet = snippet[:147] + "..."
                formatted.append(f"{role}: {snippet}")
            formatted.append("--- END OF CONTEXT ---\n")
            return "\n".join(formatted)
    except Exception as e:
        print(f"[bridge:memory] Failed to retrieve context: {e}")
        return ""

def fetch_and_mark_undelivered_notifications():
    """Retrieves queued notifications to speak them out to the user."""
    alerts = []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT id, source, message FROM system_notifications WHERE delivered = 0 ORDER BY id ASC"
            ).fetchall()
            for nid, src, msg in rows:
                alerts.append(f"📢 [Alert from {src}]: {msg}")
                conn.execute("UPDATE system_notifications SET delivered = 1 WHERE id = ?", (nid,))
            conn.commit()
    except Exception as e:
        print(f"[bridge:notify] Error fetching notifications: {e}")
    return alerts

# ─────────────────────────────────────────────────────────────
# 2. Smart Hyprland Desktop Grounding (Filtering Out Avatar)
# ─────────────────────────────────────────────────────────────
def capture_desktop_window():
    """
    Intelligently captures the active workspace or target application window,
    explicitly avoiding self-capture of MateEngineX.
    """
    capture_path = "/tmp/mate_screen_capture.png"
    target_title = "Desktop Workspace"

    try:
        # Check all clients on Hyprland to find the top active window that is NOT MateEngine
        clients_proc = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=2)
        if clients_proc.returncode == 0 and clients_proc.stdout.strip():
            clients = json.loads(clients_proc.stdout)
            # Find focused window or top window on active workspace
            valid_windows = [
                c for c in clients 
                if "mateengine" not in c.get("class", "").lower() 
                and "mateengine" not in c.get("title", "").lower()
                and c.get("size", [0, 0])[0] > 100
            ]
            
            # Prefer focused window if not MateEngine
            focused = next((c for c in valid_windows if c.get("focusHistoryID", 1) == 0), None)
            if not focused and valid_windows:
                # Fallback to the most recently focused non-avatar window
                valid_windows.sort(key=lambda c: c.get("focusHistoryID", 999))
                focused = valid_windows[0]

            if focused:
                geom = f"{focused['at'][0]},{focused['at'][1]} {focused['size'][0]}x{focused['size'][1]}"
                subprocess.run(["grim", "-g", geom, capture_path], check=True, timeout=5)
                return capture_path, focused.get("title", focused.get("class", "Target Window"))

    except Exception as e:
        print(f"[bridge:vision] Smart client detection fallback: {e}")

    # Fallback to full active monitor screenshot
    try:
        subprocess.run(["grim", capture_path], check=True, timeout=5)
        return capture_path, target_title
    except Exception as e:
        print(f"[bridge:vision] Full capture failed: {e}")
        return None, None

# ─────────────────────────────────────────────────────────────
# 3. Hybrid Intent Classifier
# ─────────────────────────────────────────────────────────────
ACTION_TRIGGERS = [
    "/", "system", "terminal", "bash", "shell", "run ", "execute", "install",
    "check my", "fix ", "debug", "create file", "edit file", "look at",
    "what is on my screen", "git ", "build", "compile", "clean", "organize",
    "find file", "search code", "inspect", "vram", "gpu", "monitor", "daemon"
]

def is_action_or_deep_task(user_msg):
    """
    Classifies whether a message requires deep agentic execution (Antigravity)
    or is casual conversational banter (Fast Local Ollama).
    """
    msg = user_msg.strip().lower()
    if msg.startswith(("/", "!", "$")):
        return True
    return any(trigger in msg for trigger in ACTION_TRIGGERS)

# ─────────────────────────────────────────────────────────────
# 4. Antigravity Deep Agentic Streaming Engine
# ─────────────────────────────────────────────────────────────
def stream_agy_response(prompt, request_data, prefix_note=None, emotion_tag="[emotion:thinking]"):
    model = request_data.get("model", "qwen2.5:0.5b")
    full_response = []

    def chunk(content, done=False):
        return json.dumps({
            "model": model,
            "message": {"role": "assistant", "content": content},
            "done": done,
        }) + "\n"

    # Deliver any pending proactive notifications first!
    pending_alerts = fetch_and_mark_undelivered_notifications()
    if pending_alerts:
        yield chunk("[emotion:alert] " + "\n".join(pending_alerts) + "\n\n")

    if emotion_tag:
        yield chunk(f"{emotion_tag} ")

    if prefix_note:
        yield chunk(f"{prefix_note}\n\n")

    # Assemble contextual prompt curing amnesia
    context_prefix = get_recent_context(limit=6)
    full_agent_prompt = f"{context_prefix}User Directive:\n{prompt}" if context_prefix else prompt

    process = None
    try:
        process = subprocess.Popen(
            ["agy", "-p", full_agent_prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        for line in process.stdout:
            full_response.append(line)
            yield chunk(line)

        process.wait(timeout=120)

        if process.returncode != 0:
            err_msg = f"\n\n[emotion:sorrow] ⚠️ agy exited with code {process.returncode}"
            full_response.append(err_msg)
            yield chunk(err_msg)

    except subprocess.TimeoutExpired:
        if process:
            process.kill()
        err_msg = "\n\n[emotion:sorrow] ⚠️ Operation timed out after 120 seconds."
        full_response.append(err_msg)
        yield chunk(err_msg)
    except FileNotFoundError:
        raise
    except Exception as e:
        err_msg = f"\n\n[emotion:sorrow] ⚠️ Bridge execution error: {str(e)}"
        full_response.append(err_msg)
        yield chunk(err_msg)

    # Persist assistant turn to SQLite
    log_memory("assistant", "".join(full_response))
    yield chunk("", done=True)

# ─────────────────────────────────────────────────────────────
# 5. Fast Local GPU Ollama Forwarding (<300ms Latency)
# ─────────────────────────────────────────────────────────────
def stream_fast_local_ollama(path, request_data):
    """Proxies casual banter directly to local RTX 500 Ada Ollama with emotion markup."""
    try:
        # Prepend pending notifications if any
        pending_alerts = fetch_and_mark_undelivered_notifications()
        
        resp = requests.post(
            f"{OLLAMA_REAL_URL}/{path}",
            json=request_data,
            stream=True,
            timeout=30
        )

        def generate():
            full_text = []
            if pending_alerts:
                yield json.dumps({
                    "model": request_data.get("model", "qwen2.5:0.5b"),
                    "message": {"role": "assistant", "content": "[emotion:alert] " + "\n".join(pending_alerts) + "\n\n"},
                    "done": False
                }) + "\n"

            for raw_chunk in resp.iter_lines():
                if raw_chunk:
                    line = raw_chunk.decode("utf-8")
                    try:
                        parsed = json.loads(line)
                        content = parsed.get("message", {}).get("content", "")
                        if content:
                            full_text.append(content)
                    except Exception:
                        pass
                    yield line + "\n"

            if full_text:
                log_memory("assistant", "".join(full_text))

        return Response(stream_with_context(generate()), mimetype="application/x-ndjson")

    except Exception as e:
        print(f"[bridge:local] Local Ollama error, falling back to agy: {e}")
        user_msg = request_data.get("messages", [{}])[-1].get("content", "")
        return Response(stream_with_context(stream_agy_response(user_msg, request_data)), mimetype="application/x-ndjson")

# ─────────────────────────────────────────────────────────────
# 6. HTTP Webhooks & API Routing
# ─────────────────────────────────────────────────────────────
@app.route("/notify", methods=["POST"])
def receive_notification():
    """Webhook for ambient daemons and orca-cli events."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        message = data.get("message", "System notification received.")
        source = data.get("source", "system-daemon")
        
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO system_notifications (source, message, delivered) VALUES (?, ?, 0)", (source, message))
            conn.commit()
            
        print(f"[bridge:notify] Queued proactive alert from [{source}]: {message}")
        return json.dumps({"status": "SUCCESS", "message": "Notification queued for delivery"}), 200
    except Exception as e:
        return json.dumps({"status": "ERROR", "error": str(e)}), 500

@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE"])
@app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def catch_all(path):
    if request.method == "POST" and path in ("api/chat", "api/generate"):
        try:
            data = request.get_json(force=True, silent=True) or {}
            messages = data.get("messages", [])
            prompt = data.get("prompt", "")

            user_msg = ""
            if messages:
                user_msg = messages[-1].get("content", "").strip()
            elif prompt:
                user_msg = prompt.strip()

            if user_msg:
                log_memory("user", user_msg)

            # Route A: Visual Perception (/see or /look)
            if user_msg.startswith(("/see", "/look")) or "look at my screen" in user_msg.lower():
                clean_query = user_msg.replace("/see", "").replace("/look", "").strip() or "Inspect and explain what you see in this window."
                img_path, win_title = capture_desktop_window()
                
                if img_path:
                    vision_prompt = (
                        f"The user asked: '{clean_query}'.\n"
                        f"I captured a screenshot of their target application ('{win_title}') at {img_path}.\n"
                        f"Inspect this image and provide a direct, concise answer."
                    )
                    return Response(
                        stream_with_context(stream_agy_response(
                            vision_prompt, data,
                            prefix_note=f"👁️ Inspecting window: [{win_title}]",
                            emotion_tag="[emotion:thinking]"
                        )),
                        mimetype="application/x-ndjson",
                    )

            # Route B: Explicit System / Agent Actions
            if user_msg.startswith(("/system ", "/agy ", "!")):
                cmd = user_msg.split(" ", 1)[1] if " " in user_msg else user_msg[1:]
                return Response(
                    stream_with_context(stream_agy_response(
                        cmd, data,
                        prefix_note=f"⚙️ Executing system action:\n> {cmd}",
                        emotion_tag="[emotion:thinking]"
                    )),
                    mimetype="application/x-ndjson",
                )

            # Route C: Hybrid Classifier Dispatch
            if is_action_or_deep_task(user_msg):
                # Deep Agentic Execution with Context Memory
                return Response(
                    stream_with_context(stream_agy_response(user_msg, data, emotion_tag="[emotion:joy]")),
                    mimetype="application/x-ndjson",
                )
            else:
                # Fast Local GPU Ollama Execution (<300ms latency)
                return stream_fast_local_ollama(path, data)

        except Exception as e:
            print(f"[bridge] Exception: {e}")

    # Standard loopback for non-chat endpoints (tags, embeddings, etc.)
    resp = requests.request(
        method=request.method,
        url=f"{OLLAMA_REAL_URL}/{path}",
        headers={k: v for k, v in request.headers if k != "Host"},
        data=request.get_data(),
        stream=True,
    )
    headers = [(n, v) for n, v in resp.raw.headers.items()]
    return Response(
        stream_with_context(resp.iter_content(chunk_size=1024)),
        status=resp.status_code,
        headers=headers,
    )

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=11434, threaded=True)
