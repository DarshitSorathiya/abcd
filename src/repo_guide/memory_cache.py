"""Memory, cache, and /goal loop using SQLite + Groq fallbacks."""
from __future__ import annotations
import sqlite3, os, time, requests
from pathlib import Path

# Load API keys from keys.env if it exists
_keys_file = Path(__file__).parent / "keys.env"
if _keys_file.exists():
    for line in _keys_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

DB = Path.home() / ".repo_guide" / "agent.db"
DB.parent.mkdir(parents=True, exist_ok=True)

def _init_db():
    conn = sqlite3.connect(str(DB))
    conn.execute("CREATE TABLE IF NOT EXISTS memory (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT, hits INTEGER DEFAULT 0, misses INTEGER DEFAULT 0)")
    conn.commit(); conn.close()
_init_db()

class Memory:
    def __init__(self): pass
    def get(self, k, default=None):
        conn = sqlite3.connect(str(DB))
        row = conn.execute("SELECT value FROM memory WHERE key = ?", (k,)).fetchone()
        conn.close()
        return row[0] if row else default
    def set(self, k, v):
        conn = sqlite3.connect(str(DB))
        conn.execute("INSERT OR REPLACE INTO memory (key, value) VALUES (?, ?)", (k, v))
        conn.commit(); conn.close()

class Cache:
    def __init__(self): pass
    def get(self, k):
        conn = sqlite3.connect(str(DB))
        row = conn.execute("SELECT value, hits FROM cache WHERE key = ?", (k,)).fetchone()
        if row:
            conn.execute("UPDATE cache SET hits = hits + 1 WHERE key = ?", (k,))
            conn.commit(); conn.close(); return row[0]
        conn.execute("INSERT OR IGNORE INTO cache (key) VALUES (?)", (k,))
        conn.execute("UPDATE cache SET misses = misses + 1 WHERE key = ?", (k,))
        conn.commit(); conn.close(); return None
    def set(self, k, v):
        conn = sqlite3.connect(str(DB))
        conn.execute("INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)", (k, v))
        conn.commit(); conn.close()
    def ratio(self) -> float:
        conn = sqlite3.connect(str(DB))
        hits, misses = conn.execute("SELECT COALESCE(SUM(hits),0), COALESCE(SUM(misses),0) FROM cache").fetchone()
        conn.close()
        total = hits + misses
        return hits / total if total > 0 else 0.0

def fallback_model():
    """Try Groq API first, then fall back to local Ollama."""
    try:
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            return "qwen3:8b"
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model":"qwen/qwen3.8-27b","messages":[{"role":"user","content":"hi"}],"max_tokens":5},
            timeout=5
        )
        if resp.status_code == 200:
            return "groq"
    except Exception:
        pass
    return "qwen3:8b"

def run_until_goal(context, ollama, settings, question, goal_string="final"):
    memory = Memory(); cache = Cache()
    result = None; step = 0; max_steps = settings.max_steps
    while step < max_steps:
        try:
            result = __import__("asyncio").run(__import__("repo_guide.agent", fromlist=["_run_turn_with_server"])._run_turn_with_server(context, ollama, question, settings))
        except Exception as exc:
            print("Crash-safe: caught", exc)
            result = None
        step += 1
        if result is not None:
            key = question + ":" + str(step)
            cached = cache.get(key)
            if cached is not None: print("Cache HIT ratio:", cache.ratio())
            else: cache.set(key, str(result.answer))
            memory.set("last_step", str(step)); memory.set("goal", goal_string)
            if result.answer and (goal_string in result.answer or not result.incomplete):
                print("Goal at step", step, "hit ratio:", cache.ratio())
                break
    if step >= max_steps: print("Max steps, hit ratio:", cache.ratio())
    return result
