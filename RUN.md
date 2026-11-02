# Repo Guide — Quick Run Guide

For the full architecture, data flow, security model, IDE setup, module reference, limitations, and SQLite prototype analysis, see [docs/REPO_GUIDE_COMPLETE_GUIDE.md](docs/REPO_GUIDE_COMPLETE_GUIDE.md).

## Quick Start

```powershell
# 1. Install
python -m pip install -e ".[dev]"

# 2. Start the read-only MCP server (for IDE/MCP clients)
repo-guide-mcp --repo . --verbose

# 3. Run the interactive CLI agent (Ollama by default)
repo-guide --repo . --verbose
```

Ollama is the default provider and must be running locally with the selected model available. To use Groq, set `GROQ_API_KEY` in the same process environment before launching `repo-guide`. For example, enter the key securely in PowerShell:

```powershell
$secureKey = Read-Host "Groq API key" -AsSecureString
$env:GROQ_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
repo-guide --repo . --verbose
Remove-Item Env:GROQ_API_KEY
Remove-Variable secureKey
```

The CLI does not load credentials from `keys.env` or other repository files. Never commit a key or paste it into chat. Rotate any key that was exposed.

The standard CLI defaults to four model decisions per question. Groq may still reject requests with HTTP 429 when a provider-side rate or usage limit is reached.

SQLite memory/cache helpers and `custom_server.py` are experimental, are not used by the standard commands, and should not be treated as an API-cost optimization. Their behavior and limitations are documented in the complete guide.

## Tests

```powershell
uv run pytest -q
```

Do not rely on a hard-coded expected test count; report the count observed from the current run.
