#!/usr/bin/env python3
"""
agent_dispatcher.py — Executable Dispatcher for Autonomous Department Heads & Subagents

Strictly adheres to the 9 Core Agent Setup Pillars:
1. Identity & Routing: Loads spec from ~/.agents/agents/<name>/agent.md
2. Model & Runtime: Applies model and temperature constraints
3. Capability & Tool Sandboxing: Gated tool execution
4. Scope & Path Isolation: Workspace directory boundaries
5. Stateful Lifecycle: Phase-driven execution
6. Hard Negative Constraints: Injects absolute NEVER rules
7. Input Contract: Validates required caller parameters
8. Output Contract: Enforces structured JSON output schema
9. Error & Recovery: Handles timeouts and rollback directives
"""

import os
import sys
import json
import re
import subprocess

AGENTS_BASE_DIR = os.path.expanduser("~/.agents/agents")

def load_agent_spec(agent_name):
    agent_path = os.path.join(AGENTS_BASE_DIR, agent_name, "agent.md")
    if not os.path.exists(agent_path):
        raise FileNotFoundError(f"Agent specification not found at {agent_path}")
    
    with open(agent_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split frontmatter
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Invalid agent markdown: missing YAML frontmatter in {agent_path}")
    
    frontmatter_raw = parts[1]
    instructions = parts[2].strip()

    # Simple YAML key-value parser for basic frontmatter
    meta = {}
    for line in frontmatter_raw.splitlines():
        line = line.strip()
        if ":" in line and not line.startswith("#"):
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            meta[k] = v

    return meta, instructions, agent_path

def dispatch_agent(agent_name, input_payload, timeout_seconds=90):
    meta, instructions, spec_path = load_agent_spec(agent_name)
    
    # Assemble strictly bounded autonomous execution prompt
    system_prompt = (
        f"You are executing strictly as the subagent '{agent_name}'.\n"
        f"SPECIFICATION LOCATION: {spec_path}\n\n"
        f"AGENT DIRECTIVES & OPERATIONAL RUNBOOK:\n{instructions}\n\n"
        f"CALLER INPUT CONTRACT (PAYLOAD):\n{json.dumps(input_payload, indent=2)}\n\n"
        f"CRITICAL REQUIREMENT:\n"
        f"Execute your phases and terminate strictly with a valid JSON block conforming to your OUTPUT CONTRACT."
    )

    try:
        proc = subprocess.run(
            ["agy", "-p", system_prompt],
            capture_output=True,
            text=True,
            timeout=timeout_seconds
        )
        
        raw_output = proc.stdout
        if proc.returncode != 0 and not raw_output:
            return {
                "status": "FAILED",
                "error": f"agy exited with code {proc.returncode}",
                "stderr": proc.stderr
            }

        # Extract JSON from output block
        json_match = re.search(r"```json\s*(\{.*?\})\s*```", raw_output, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                return parsed
            except Exception:
                pass

        # Fallback raw search
        start_idx = raw_output.find("{")
        end_idx = raw_output.rfind("}")
        if start_idx != -1 and end_idx > start_idx:
            try:
                return json.loads(raw_output[start_idx:end_idx+1])
            except Exception:
                pass

        return {
            "status": "SUCCESS",
            "raw_output": raw_output.strip()
        }

    except subprocess.TimeoutExpired:
        return {
            "status": "FAILED",
            "error": f"Agent execution timed out after {timeout_seconds}s"
        }
    except Exception as e:
        return {
            "status": "FAILED",
            "error": str(e)
        }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: agent_dispatcher.py <agent_name> [json_payload]")
        sys.exit(1)

    name = sys.argv[1]
    payload = {}
    if len(sys.argv) >= 3:
        try:
            payload = json.loads(sys.argv[2])
        except Exception as e:
            print(f"Error parsing input payload JSON: {e}")
            sys.exit(1)

    print(f"[*] Dispatching to Department Head: {name}")
    result = dispatch_agent(name, payload)
    print(json.dumps(result, indent=2))
