# Repo Guide — How to Run & API Keys

## Quick Start

```bash
# 1. Install
python -m pip install -e ".[dev]"

# 2. Set your Groq API key (optional — used for model fallback)
#    Create the file below and add your key:
#    C:\Users\<you>\.repo_guide\keys.env
#    Content: GROQ_API_KEY=your_key_here

# 3. Set local model (optional — default qwen3:8b)
#    Same file or environment:
#    REPO_GUIDE_MODEL=qwen3:8b

# 4. Run MCP server
repo-guide-mcp --repo . --verbose

# 5. Run CLI agent (requires local Ollama running)
repo-guide --model qwen3:8b --max-steps 8 --verbose

# 6. Run unified custom server (memory + cache + fallback)
python -m repo_guide.custom_server --repo .
```

## Where to Put API Keys

File: `C:\Users\<your_username>\.repo_guide\keys.env`

This file is read by `memory_cache.py` (line `os.environ.get("GROQ_API_KEY")`). It is not checked into git and stays on your machine only. Example:

```
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
REPO_GUIDE_MODEL=qwen3:8b
OLLAMA_URL=http://localhost:11434
```

The code looks for this exact file first, then falls back to the system environment (`os.environ`). Never put keys in `pyproject.toml`, source files, or commit them.

## Memory & Cache (SQLite DB)

Location: `C:\Users\<your_username>\.repo_guide\agent.db`

This is a real SQLite database (not JSON). Tables:
- `memory` (key, value) — stores conversation state and last `/goal` step
- `cache` (key, value, hits, misses) — stores responses; hit ratio measured on read

To inspect manually:
```bash
sqlite3 C:\Users\<you>\.repo_guide\agent.db "SELECT * FROM memory;"
sqlite3 C:\Users\<you>\.repo_guide\agent.db "SELECT * FROM cache;"
```

## Project Files You Added This Session

- `docs/ARCHITECTURE.md` — unified built + custom MCP design
- `src/repo_guide/custom_server.py` — entry point using SQLite + Groq
- `src/repo_guide/memory_cache.py` — DB memory, DB cache, `fallback_model()`, crash-safe `/goal` loop

## Safety Reminders (From Security Audit)

- Symlink paths are denied (`safety.py`)
- Sensitive files (`.env`, `.git`) are blocked
- Binary/minified files are blocked
- File size capped at 1,000,000 bytes
- Agent stops at 8 steps (configurable)
- All loops are wrapped in `try/except` (no crash in production)

## Tests

```bash
pytest -q
pytest tests/unit/ -q
pytest tests/security/ -q
```

Expected: 76 passed, 3 skipped (symlink unavailable on Windows without developer mode).
