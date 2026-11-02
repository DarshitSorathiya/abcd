# Unified MCP Architecture — Built + Custom

## Structure
- Built: repo-guide-mcp (existing, read-only repo tools)
- Custom: custom-mcp-server.py (user-defined extensions, memory, cache)
- Merge: both register under same root context; custom can call built tools

## Fallback
- Use local Ollama (`qwen3:8b`) when neither hosted provider key is set.
- When `GROQ_API_KEY` is set, use Groq's fixed HTTPS chat endpoint and `GROQ_MODEL` (default `qwen/qwen3.8-27b`); do not silently fall back after a Groq request fails.
- When `GEMINI_API_KEY` is set and Groq is not, use Google's fixed Gemini HTTPS endpoint and `GEMINI_MODEL` (default `gemini-3.8-flash`); do not silently fall back after a Gemini request fails.
- Automatic selection prefers Groq, then Gemini, then Ollama; explicit `--provider` overrides this order.
- Report the selected provider and model at CLI startup and disclose that the selected hosted provider receives the question and repository excerpts.

## Safety
- All agent loops wrapped in try/except
- No unhandled exceptions reach production

## Memory + Cache (SQLite DB, not JSON)
- Memory: SQLite DB at `~/.repo_guide/agent.db` (table `memory`)
- Cache: SQLite DB at `~/.repo_guide/agent.db` (table `cache`, hits/misses tracked)
- Hit ratio: `ratio()` reads `SUM(hits) / SUM(hits + misses)` from DB
- Key file: `src/repo_guide/memory_cache.py`

## /goal
- Agent runs turn loop until final answer or goal string matched
- If max_steps reached, return partial with status
