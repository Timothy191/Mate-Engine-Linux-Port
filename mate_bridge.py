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
import re
import sqlite3
import subprocess
import select
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
# Word-boundary patterns for actionable directives. Kept deliberately
# narrow: casual banter must NOT be hijacked into heavyweight agy runs.
# Multi-word phrases use substring matching; single words use \b boundaries.
ACTION_PATTERNS = [
    r"\bsystem\b", r"\bterminal\b", r"\bbash\b", r"\bshell\b",
    r"\bexecute\b", r"\binstall\b", r"\bdebug\b",
    r"check my", r"fix (this|that|it|the|\w+ bug)", r"\bcompile\b",
    r"create file", r"edit file", r"look at",
    r"what is on my screen", r"\bgit\b", r"\bbuild\b",
    r"find file", r"search code", r"\binspect\b",
    r"\bvram\b", r"\bgpu\b", r"\bdaemon\b",
]

def is_action_or_deep_task(user_msg):
    """
    Classifies whether a message requires deep agentic execution (Antigravity)
    or is casual conversational banter (Fast Local Ollama).
    """
    msg = user_msg.strip().lower()
    if msg.startswith(("/", "!", "$")):
        return True
    return any(re.search(pattern, msg) for pattern in ACTION_PATTERNS)

# ─────────────────────────────────────────────────────────────
# 4. Antigravity Deep Agentic Streaming Engine
# ─────────────────────────────────────────────────────────────
# Patterns of internal debug/MCP chatter to suppress from user view
MCP_DEBUG_PATTERNS = (
    "[mcp", "mcp:", "mcp server", "connected to mcp", "loading mcp",
    "call_mcp_tool", "tool_call", "tool_result", "[gin]", "running command",
    "executing tool", "thinking process:", "debug:"
)

def is_internal_debug_line(line):
    """Returns True if the line is internal tool/MCP telemetry that should be hidden."""
    cleaned = line.strip().lower()
    if not cleaned:
        return False
    return any(cleaned.startswith(pat) or pat in cleaned for pat in MCP_DEBUG_PATTERNS)

EMOTION_ALIASES = {
    "happy": "joy", "sad": "sorrow", "angry": "angry", "sorrow": "sorrow",
    "joy": "joy", "fun": "fun", "relaxed": "fun", "alert": "alert",
    "thinking": "thinking", "surprised": "alert",
}

def emotion_tag_line(tag):
    """Builds the leading [emotion:...] chunk understood by Unity's EmotionDriver."""
    return f"[emotion:{tag}] "

def stream_agy_response(prompt, request_data):
    model = request_data.get("model", "qwen2.5:0.5b")
    full_response = []
    # Inject emotion tag
    emotion = "thinking"
    yield chunk(emotion_tag_line(emotion), done=False)

    def chunk(content, done=False):
        return json.dumps({
            "model": model,
            "message": {"role": "assistant", "content": content},
            "done": done,
        }) + "\n"

    # Assemble contextual prompt curing amnesia and surface pending hardware alerts
    context_prefix = get_recent_context(limit=6)
    pending_alerts = fetch_and_mark_undelivered_notifications()
    if pending_alerts:
        alert_block = "--- PENDING SYSTEM ALERTS ---\n" + "\n".join(pending_alerts) + "\n--- END ALERTS ---\n"
        context_prefix = f"{alert_block}\n{context_prefix}" if context_prefix else alert_block

    full_agent_prompt = f"{context_prefix}User Directive:\n{prompt}" if context_prefix else prompt

    process = None
    try:
        process = subprocess.Popen(
            ["agy", "-p", full_agent_prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        # Deadline-bounded read loop: a silent-hanging agy is killed at the
        # 120 s mark instead of blocking on EOF forever.
        deadline = time.monotonic() + 120
        stdout_fd = process.stdout.fileno()
        os.set_blocking(stdout_fd, False)
        timed_out = False

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            ready, _, _ = select.select([stdout_fd], [], [], min(remaining, 2.0))
            if not ready:
                if process.poll() is not None:
                    break
                continue
            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    break
                continue
            # Hide internal MCP, tool calls, and debug telemetry from the user
            if is_internal_debug_line(line):
                continue

            full_response.append(line)
            yield chunk(line)

        if timed_out:
            process.kill()
            process.wait(timeout=5)
            err_msg = "\n\n⚠️ Operation timed out after 120 seconds."
            full_response.append(err_msg)
            yield chunk(err_msg)
        else:
            process.wait(timeout=10)

            if process.returncode != 0:
                err_msg = f"\n\n⚠️ An error occurred during execution (code {process.returncode})."
                full_response.append(err_msg)
                yield chunk(err_msg)

    except FileNotFoundError:
        raise
    except Exception as e:
        if process and process.poll() is None:
            process.kill()
        err_msg = f"\n\n⚠️ Bridge error: {str(e)}"
        full_response.append(err_msg)
        yield chunk(err_msg)

    # Persist assistant turn to SQLite
    log_memory("assistant", "".join(full_response))
    yield chunk("", done=True)

# ─────────────────────────────────────────────────────────────
# 5. Fast Local GPU Ollama Forwarding (<300ms Latency)
# ─────────────────────────────────────────────────────────────
def stream_fast_local_ollama(path, request_data):
    """Proxies casual banter directly to local RTX 500 Ada Ollama cleanly with no alerts/tags."""
    try:
        resp = requests.post(
            f"{OLLAMA_REAL_URL}/{path}",
            json=request_data,
            stream=True,
            timeout=30
        )

        def generate():
            full_text = []
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
    """Webhook for ambient daemons and orca-cli events (logged quietly to DB)."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        message = data.get("message", "System notification received.")
        source = data.get("source", "system-daemon")
        
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO system_notifications (source, message, delivered) VALUES (?, ?, 0)", (source, message))
            conn.commit()
            
        print(f"[bridge:notify] Recorded alert from [{source}]: {message}")
        return json.dumps({"status": "SUCCESS", "message": "Notification recorded"}), 200
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
                        stream_with_context(stream_agy_response(vision_prompt, data)),
                        mimetype="application/x-ndjson",
                    )

            # Route B: Explicit System / Agent Actions
            if user_msg.startswith(("/system ", "/agy ", "!")):
                cmd = user_msg.split(" ", 1)[1] if " " in user_msg else user_msg[1:]
                return Response(
                    stream_with_context(stream_agy_response(cmd, data)),
                    mimetype="application/x-ndjson",
                )

            # Route C: Hybrid Classifier Dispatch
            if is_action_or_deep_task(user_msg):
                # Deep Agentic Execution with Context Memory (clean output)
                return Response(
                    stream_with_context(stream_agy_response(user_msg, data)),
                    mimetype="application/x-ndjson",
                )
            else:
                # Fast Local GPU Ollama Execution (<300ms latency, clean output)
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
    headers = [(n, v) for n, v in resp.raw.headers.items() if n.lower() not in ('transfer-encoding', 'content-encoding')]
    return Response(
        stream_with_context(resp.iter_content(chunk_size=1024)),
        status=resp.status_code,
        headers=headers,
    )

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=11434, threaded=True)
