# Unified MCP Architecture — Built + Custom

## Structure
- Built: repo-guide-mcp (existing, read-only repo tools)
- Custom: custom-mcp-server.py (user-defined extensions, memory, cache)
- Merge: both register under same root context; custom can call built tools

## Fallback
- Try model in order: qwen3:8b → mistral:7b → llama3 → any available
- If none available: reply with error, do not crash

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
