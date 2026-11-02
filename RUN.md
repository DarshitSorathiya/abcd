# Repo Guide — Quick Run Guide

For the full architecture, data flow, security model, IDE setup, module reference, limitations, and SQLite prototype analysis, see [docs/REPO_GUIDE_COMPLETE_GUIDE.md](docs/REPO_GUIDE_COMPLETE_GUIDE.md).

## Quick Start

```powershell
# 1. Install
python -m pip install -e ".[dev]"

# 2. Start the read-only MCP server (for IDE/MCP clients only)
repo-guide-mcp --repo . --verbose

# Or run the interactive CLI agent (Ollama by default); it starts its own MCP child
repo-guide --repo . --verbose
```

The standalone `repo-guide-mcp` command communicates over stdio with the MCP client that launched it. The CLI starts its own server process for each question and does not connect to a separately launched `repo-guide-mcp` process. With `repo-guide --verbose`, its child server's tool-call diagnostics are written to the CLI's stderr.

Ollama is the default provider and must be running locally with the selected model available. To use Gemini, enter its API key securely in PowerShell and set it in the same process environment:

```powershell
$secureKey = Read-Host "Gemini API key" -AsSecureString
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
repo-guide --provider gemini --repo . --verbose
Remove-Item Env:GEMINI_API_KEY
Remove-Variable secureKey
```

The CLI does not load credentials from `keys.env` or other repository files. Never commit a key or paste it into chat. Rotate any key that was exposed.

`GEMINI_MODEL` selects the Gemini model (default `gemini-3.8-flash`). The standard CLI defaults to two model decisions per question. Hosted providers receive the question and repository excerpts; verify the startup provider/model before asking repository questions. Groq may reject requests with HTTP 429 when an organization-level rate or usage limit is reached.

Gemini requests use Google's streamed `streamGenerateContent` endpoint; the CLI still waits for the complete JSON action before using it. Gemini 3 requests use Google's documented `low` thinking level to reduce first-token latency. With `--verbose`, the CLI reports when each request starts, when response data first arrives, and when the request finishes. The configured read timeout is an inactivity limit between response chunks, not a total request deadline; diagnostics never expose prompt content, responses, or credentials.

SQLite memory/cache helpers and `custom_server.py` are experimental, are not used by the standard commands, and should not be treated as an API-cost optimization. Their behavior and limitations are documented in the complete guide.

## Tests

```powershell
uv run pytest -q
```

Do not rely on a hard-coded expected test count; report the count observed from the current run.
