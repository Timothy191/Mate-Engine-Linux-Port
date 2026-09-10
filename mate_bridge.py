"""
mate_bridge.py — High-Performance Async FastAPI ↔ MateEngine Multi-Agent Bridge

Key Enhancements (P2 Architecture):
  1. ASGI / FastAPI Core:
     - Fully asynchronous request handling via Starlette/FastAPI and httpx.AsyncClient.
  2. Async Streaming (ndjson & SSE):
     - StreamingResponse for sub-300ms time-to-first-token on local Ollama banter.
     - Async subprocess streaming for Antigravity (agy) agentic actions.
  3. Strict VRAM Safeguard (RTX 500 Ada):
     - Automatic injection of num_ctx: 2048 on all forwarded Ollama payloads to protect 4GB VRAM ceiling.
  4. High-Concurrency SQLite with WAL Mode:
     - PRAGMA journal_mode=WAL and synchronous=NORMAL to eliminate database contention.
  5. Smart Non-Avatar Hyprland Grounding:
     - Intelligently filters out MateEngineX when capturing desktop for /see or /look.
  6. Proactive Ambient Notifications:
     - Automatically surfaces unread notifications into agent reasoning context.
"""

import asyncio
import json
import os
import re
import sqlite3
import subprocess
from typing import AsyncGenerator, Optional, Tuple

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="MateEngine Hardened Agent Bridge", version="2.0.0")

OLLAMA_REAL_URL = os.getenv("OLLAMA_REAL_URL", "http://127.0.0.1:11435")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "mate_memory.db")
MAX_CONTEXT_TOKENS = 2048

# ─────────────────────────────────────────────────────────────
# 1. SQLite Persistent Episodic Memory & Notification Storage
# ─────────────────────────────────────────────────────────────
def get_db_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn

def init_db():
    with get_db_conn() as conn:
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

def log_memory(role: str, content: str):
    try:
        with get_db_conn() as conn:
            conn.execute("INSERT INTO conversation_turns (role, content) VALUES (?, ?)", (role, content))
            conn.commit()
    except Exception as e:
        print(f"[bridge:memory] DB log error: {e}")

def get_recent_context(limit: int = 6) -> str:
    """Fetches recent conversation turns to prevent context amnesia."""
    try:
        with get_db_conn() as conn:
            rows = conn.execute(
                "SELECT role, content FROM conversation_turns ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            if not rows:
                return ""
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

def fetch_and_mark_undelivered_notifications() -> list:
    """Retrieves queued system/daemon notifications to inject into agent stream."""
    alerts = []
    try:
        with get_db_conn() as conn:
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
def capture_desktop_window() -> Tuple[Optional[str], Optional[str]]:
    """
    Captures the active workspace or target application window,
    filtering out MateEngineX to avoid self-capture loops.
    """
    capture_path = "/tmp/mate_screen_capture.png"
    target_title = "Desktop Workspace"

    try:
        clients_proc = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=2)
        if clients_proc.returncode == 0 and clients_proc.stdout.strip():
            clients = json.loads(clients_proc.stdout)
            valid_windows = [
                c for c in clients
                if "mateengine" not in c.get("class", "").lower()
                and "mateengine" not in c.get("title", "").lower()
                and c.get("size", [0, 0])[0] > 100
            ]

            focused = next((c for c in valid_windows if c.get("focusHistoryID", 1) == 0), None)
            if not focused and valid_windows:
                valid_windows.sort(key=lambda c: c.get("focusHistoryID", 999))
                focused = valid_windows[0]

            if focused:
                geom = f"{focused['at'][0]},{focused['at'][1]} {focused['size'][0]}x{focused['size'][1]}"
                subprocess.run(["grim", "-g", geom, capture_path], check=True, timeout=5)
                return capture_path, focused.get("title", focused.get("class", "Target Window"))

    except Exception as e:
        print(f"[bridge:vision] Smart client detection fallback: {e}")

    try:
        subprocess.run(["grim", capture_path], check=True, timeout=5)
        return capture_path, target_title
    except Exception as e:
        print(f"[bridge:vision] Full capture failed: {e}")
        return None, None

# ─────────────────────────────────────────────────────────────
# 3. Hybrid Intent Classifier
# ─────────────────────────────────────────────────────────────
ACTION_PATTERNS = [
    r"\bsystem\b", r"\bterminal\b", r"\bbash\b", r"\bshell\b",
    r"\bexecute\b", r"\binstall\b", r"\bdebug\b",
    r"check my", r"fix (this|that|it|the|\w+ bug)", r"\bcompile\b",
    r"create file", r"edit file", r"look at",
    r"what is on my screen", r"\bgit\b", r"\bbuild\b",
    r"find file", r"search code", r"\binspect\b",
    r"\bvram\b", r"\bgpu\b", r"\bdaemon\b",
]

def is_action_or_deep_task(user_msg: str) -> bool:
    msg = user_msg.strip().lower()
    if msg.startswith(("/", "!", "$")):
        return True
    return any(re.search(pattern, msg) for pattern in ACTION_PATTERNS)

MCP_DEBUG_PATTERNS = (
    "[mcp", "mcp:", "mcp server", "connected to mcp", "loading mcp",
    "call_mcp_tool", "tool_call", "tool_result", "[gin]", "running command",
    "executing tool", "thinking process:", "debug:"
)

def is_internal_debug_line(line: str) -> bool:
    cleaned = line.strip().lower()
    if not cleaned:
        return False
    return any(cleaned.startswith(pat) or pat in cleaned for pat in MCP_DEBUG_PATTERNS)

# ─────────────────────────────────────────────────────────────
# 4. Antigravity Deep Agentic Async Streaming Engine
# ─────────────────────────────────────────────────────────────
async def stream_agy_response(prompt: str, request_data: dict) -> AsyncGenerator[bytes, None]:
    model = request_data.get("model", "qwen2.5:0.5b")
    full_response = []

    def make_chunk(content: str, done: bool = False) -> bytes:
        payload = {
            "model": model,
            "message": {"role": "assistant", "content": content},
            "done": done,
        }
        return (json.dumps(payload) + "\n").encode("utf-8")

    # Send initial thinking emotion tag for Unity's EmotionDriver
    yield make_chunk("[emotion:thinking] ", done=False)

    context_prefix = get_recent_context(limit=6)
    pending_alerts = fetch_and_mark_undelivered_notifications()
    if pending_alerts:
        alert_block = "--- PENDING SYSTEM ALERTS ---\n" + "\n".join(pending_alerts) + "\n--- END ALERTS ---\n"
        context_prefix = f"{alert_block}\n{context_prefix}" if context_prefix else alert_block

    full_agent_prompt = f"{context_prefix}User Directive:\n{prompt}" if context_prefix else prompt

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "agy", "-p", full_agent_prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )

        try:
            while True:
                line_bytes = await asyncio.wait_for(proc.stdout.readline(), timeout=120.0)
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace")
                if is_internal_debug_line(line):
                    continue

                full_response.append(line)
                yield make_chunk(line, done=False)

            await proc.wait()
            if proc.returncode != 0:
                err_msg = f"\n\n⚠️ Agent execution finished with code {proc.returncode}."
                full_response.append(err_msg)
                yield make_chunk(err_msg, done=False)

        except asyncio.TimeoutError:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            err_msg = "\n\n⚠️ Operation timed out after 120 seconds."
            full_response.append(err_msg)
            yield make_chunk(err_msg, done=False)

    except Exception as e:
        if proc and proc.returncode is None:
            proc.kill()
        err_msg = f"\n\n⚠️ Bridge error: {str(e)}"
        full_response.append(err_msg)
        yield make_chunk(err_msg, done=False)

    log_memory("assistant", "".join(full_response))
    yield make_chunk("", done=True)

# ─────────────────────────────────────────────────────────────
# 5. Fast Local GPU Ollama Forwarding (<300ms Latency)
# ─────────────────────────────────────────────────────────────
def enforce_vram_guard(payload: dict) -> dict:
    """Enforces RTX 500 Ada 4GB VRAM ceiling: num_ctx <= 2048."""
    options = payload.setdefault("options", {})
    if "num_ctx" not in options or options["num_ctx"] > MAX_CONTEXT_TOKENS:
        options["num_ctx"] = MAX_CONTEXT_TOKENS
    return payload

async def stream_fast_local_ollama(path: str, request_data: dict) -> StreamingResponse:
    """Proxies casual banter directly to local RTX 500 Ada Ollama via httpx.AsyncClient."""
    enforced_data = enforce_vram_guard(request_data)

    async def async_generator() -> AsyncGenerator[bytes, None]:
        full_text = []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream("POST", f"{OLLAMA_REAL_URL}/{path}", json=enforced_data) as response:
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            parsed = json.loads(line)
                            content = parsed.get("message", {}).get("content", "")
                            if content:
                                full_text.append(content)
                        except Exception:
                            pass
                        yield (line + "\n").encode("utf-8")
        except Exception as e:
            print(f"[bridge:local] Local Ollama error: {e}")
            user_msg = request_data.get("messages", [{}])[-1].get("content", "")
            async for fallback_chunk in stream_agy_response(user_msg, request_data):
                yield fallback_chunk
            return

        if full_text:
            log_memory("assistant", "".join(full_text))

    return StreamingResponse(async_generator(), media_type="application/x-ndjson")

# ─────────────────────────────────────────────────────────────
# 6. HTTP Webhooks & Routing
# ─────────────────────────────────────────────────────────────
@app.post("/notify")
async def receive_notification(request: Request):
    """Webhook for ambient daemons and orca-cli events."""
    try:
        data = await request.json()
        message = data.get("message", "System notification received.")
        source = data.get("source", "system-daemon")

        with get_db_conn() as conn:
            conn.execute("INSERT INTO system_notifications (source, message, delivered) VALUES (?, ?, 0)", (source, message))
            conn.commit()

        return JSONResponse({"status": "SUCCESS", "message": "Notification recorded"})
    except Exception as e:
        return JSONResponse({"status": "ERROR", "error": str(e)}, status_code=500)

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "mate-bridge-fastapi",
        "vram_ceiling": f"{MAX_CONTEXT_TOKENS} tokens",
        "upstream_ollama": OLLAMA_REAL_URL
    }

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"])
async def proxy_catch_all(request: Request, path: str):
    if request.method == "POST" and path in ("api/chat", "api/generate"):
        try:
            data = await request.json()
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
                    return StreamingResponse(
                        stream_agy_response(vision_prompt, data),
                        media_type="application/x-ndjson"
                    )

            # Route B: Explicit System / Agent Actions
            if user_msg.startswith(("/system ", "/agy ", "!")):
                cmd = user_msg.split(" ", 1)[1] if " " in user_msg else user_msg[1:]
                return StreamingResponse(
                    stream_agy_response(cmd, data),
                    media_type="application/x-ndjson"
                )

            # Route C: Hybrid Classifier Dispatch
            if is_action_or_deep_task(user_msg):
                return StreamingResponse(
                    stream_agy_response(user_msg, data),
                    media_type="application/x-ndjson"
                )
            else:
                return await stream_fast_local_ollama(path, data)

        except Exception as e:
            print(f"[bridge] Exception: {e}")

    # Standard loopback for non-intercepted calls (tags, embeddings, model info, Anthropic v1 messages)
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}

    client = httpx.AsyncClient(timeout=300.0)
    req = client.build_request(
        request.method,
        f"{OLLAMA_REAL_URL}/{path}",
        headers=headers,
        content=body,
        params=dict(request.query_params)
    )
    upstream = await client.send(req, stream=True)

    async def forward_stream():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    resp_headers = {
        k: v for k, v in upstream.headers.items()
        if k.lower() not in ("content-length", "transfer-encoding", "content-encoding")
    }

    return StreamingResponse(
        forward_stream(),
        status_code=upstream.status_code,
        headers=resp_headers,
        media_type=upstream.headers.get("content-type")
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=11434, log_level="warning")
