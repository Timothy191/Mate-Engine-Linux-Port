#!/usr/bin/env python3
"""
smoke_test.py — Lightweight smoke tests for the MateEngine bridge and routing.

Run against a live bridge instance:
    python3 scripts/smoke_test.py

Or against a specific host/port:
    MATE_BRIDGE_URL=http://127.0.0.1:11434 python3 scripts/smoke_test.py
"""

import os
import sys
import httpx
import sqlite3

BRIDGE_URL = os.getenv("MATE_BRIDGE_URL", "http://127.0.0.1:11434")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "mate_memory.db")

def test_health():
    try:
        r = httpx.get(f"{BRIDGE_URL}/health", timeout=5)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        data = r.json()
        assert data.get("status") == "healthy", f"Unexpected health payload: {data}"
        print("[PASS] /health endpoint is healthy")
        return True
    except Exception as e:
        print(f"[FAIL] /health endpoint: {e}")
        return False

def test_db_init():
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
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
        conn.close()
        print("[PASS] SQLite DB init (WAL + tables)")
        return True
    except Exception as e:
        print(f"[FAIL] SQLite DB init: {e}")
        return False

def test_notify_webhook():
    try:
        r = httpx.post(
            f"{BRIDGE_URL}/notify",
            json={"source": "smoke-test", "message": "test notification"},
            timeout=5
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        data = r.json()
        assert data.get("status") == "SUCCESS", f"Unexpected payload: {data}"
        print("[PASS] POST /notify webhook")
        return True
    except Exception as e:
        print(f"[FAIL] POST /notify webhook: {e}")
        return False

def test_chat_routing():
    try:
        payload = {
            "model": "smoke-test",
            "messages": [{"role": "user", "content": "hello from smoke test"}]
        }
        with httpx.stream("POST", f"{BRIDGE_URL}/api/chat", json=payload, timeout=15) as r:
            assert r.status_code == 200, f"Expected 200, got {r.status_code}"
            first_chunk = next(r.iter_raw(), b"")
            assert len(first_chunk) > 0, "Expected non-empty streaming response"
        print("[PASS] POST /api/chat returns streaming response")
        return True
    except Exception as e:
        print(f"[FAIL] POST /api/chat routing: {e}")
        return False

def main():
    results = []
    print(f"Smoke-testing bridge at {BRIDGE_URL} ...\n")
    results.append(test_health())
    results.append(test_db_init())
    results.append(test_notify_webhook())
    results.append(test_chat_routing())

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} tests passed")
    return 0 if all(results) else 1

if __name__ == "__main__":
    sys.exit(main())
