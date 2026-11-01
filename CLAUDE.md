# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Repo Guide is a local, read-only repository onboarding assistant built with Python and MCP (Model Context Protocol). It consists of two console commands:
- `repo-guide-mcp`: MCP server exposing bounded read-only repository tools
- `repo-guide`: CLI agent using local Ollama to answer questions about codebases

## Build and Development Commands

### Setup
```bash
# Development install
python -m pip install -e ".[dev]"
```

### Testing
```bash
# Run all tests
pytest -q

# Run specific test layer
pytest tests/unit/ -q
pytest tests/security/ -q
pytest tests/integration/ -q

# Run single test file
pytest tests/unit/test_m1_root.py -q
```

### Code Quality
```bash
# Lint and format check
ruff check .
ruff format --check .

# Type checking
pyright src
```

### Running the Application
```bash
# MCP server
repo-guide-mcp --repo /path/to/repo --verbose

# CLI agent (requires local Ollama)
repo-guide --model qwen3:8b --max-steps 8 --verbose
```

## High-Level Architecture

1. **Root Resolution (`src/repo_guide/root.py`)**: Resolves repo root from `--repo` → `REPO_GUIDE_ROOT` → cwd, normalizes to Git top-level, and rejects system roots/user home.
2. **Safety & Policy (`src/repo_guide/safety.py`)**: Centralized path confinement, traversal prevention, symlink denial, and sensitive file/content denylists.
3. **MCP Server (`src/repo_guide/server.py`)**: Exposes read-only repository tools (`list_tree`, `read_file`, `search_code`, `git_log`, `repo_overview`, `list_issues`), resources, and prompts over stdio transport.
4. **Git & GitHub Operations (`src/repo_guide/gitops.py`, `github_api.py`)**: Bounded subprocess wrappers and public unauthenticated REST API integration.
5. **Agent & Verification (`src/repo_guide/agent.py`, `verify.py`)**: ReAct loop connecting Ollama to discovered MCP tools, followed by deterministic citation validation and sanitization.
