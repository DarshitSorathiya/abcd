# Copilot instructions for Repo Guide

## Project contract

Repo Guide is a local, read-only repository onboarding assistant. Treat the following as the source of truth before broad edits:

- `AGENTS.md`
- `docs/PROJECT_SPEC.md`
- `docs/ARCHITECTURE.md`
- `docs/SECURITY.md`
- `docs/TEST_STRATEGY.md`
- `.github/instructions/python.instructions.md`
- `.github/instructions/citation-verification.instructions.md`

This repo is intentionally narrow in scope: it exposes read-only MCP tools, does not execute repository code, and requires verified repository-relative citations for any repository-specific claim.

## Setup and local commands

Install for development from the repo root:

```bash
python -m pip install -e ".[dev]"
```

The project also supports a locked dev install with uv, which matches CI:

```bash
uv sync --locked --extra dev
```

Build, lint, type-check, and tests:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright src
uv run pytest -q
```

Run a single test file or single test case:

```bash
uv run pytest tests/unit/test_m1_root.py -q
uv run pytest tests/integration/test_m6_verify.py -q
uv run pytest tests/unit/test_m2_gitops.py -q -k "git_log"
```

Run the CLI entry points directly:

```bash
repo-guide-mcp --repo /path/to/repo --verbose
repo-guide --model qwen3:8b --max-steps 8 --verbose
```

## High-level architecture

The implementation is centered around a small set of modules and explicit boundaries:

- `src/repo_guide/root.py`: resolves the fixed repository root using `--repo` -> `REPO_GUIDE_ROOT` -> cwd, then normalizes to the git top-level. It rejects filesystem root and home directory; the root is fixed for the lifetime of the process.
- `src/repo_guide/safety.py`: central enforcement for allowed paths, sensitive-file denial, symlink rejection, and bounded content handling.
- `src/repo_guide/server.py`: the main MCP server. It exposes read-only tools such as tree/listing, file reads, code search, git log, repo overview, and public GitHub issue lookup.
- `src/repo_guide/gitops.py`: bounded git subprocess wrappers used for local history and filesystem reads.
- `src/repo_guide/github_api.py`: public GitHub issue lookups over unauthenticated REST endpoints; it must fail gracefully when no remote or rate-limit issues occur.
- `src/repo_guide/agent.py`: CLI agent loop; it discovers tools, decides between tool calls and a final answer, and uses Ollama as the model layer.
- `src/repo_guide/verify.py`: deterministic verification layer that checks repository-relative citations, root confinement, line ranges, commit hashes, and answer sanitization before final output.

The repo is intentionally split between a read-only MCP server and a separate local agent; the server is reusable by IDE clients and MCP Inspector without running the Ollama CLI agent.

## Repository conventions and guardrails

- Do not implement write or execution features in the product. The server is read-only by design.
- Use the current stable MCP Python SDK v2 and pin the dependency in `pyproject.toml` when updating compatibility.
- Do not rely on the retired MCP Roots flow; resolve repository roots explicitly from startup arguments/environment/cwd.
- Keep stdout protocol-only for MCP traffic; log diagnostics to stderr.
- Use `subprocess` argument arrays with `shell=False`, explicit timeouts, and bounded output; never interpolate user data into shell syntax.
- Prefer `pathlib` and central root validation instead of ad-hoc filesystem handling.
- Tests should use temporary fixture repositories and mocked GitHub/Ollama behavior. Avoid live network/model dependency in the default suite.
- Any repository-specific answer must cite repository-relative paths such as `src/repo_guide/server.py:42` or a verified local git hash; do not invent or infer citations.
- Keep edits minimal and milestone-scoped. The repo guidance explicitly prefers one vertical feature slice at a time.
- The default validation gate is `pytest -q` plus the lint/type checks in CI; do not claim tests passed without running them.

## Project-specific workflow expectations

- Before making a broad change, read the relevant project docs and the files directly involved in the feature.
- Write the targeted tests for the feature as part of the change, but do not run the suite repeatedly while editing. Run the focused test once the feature slice is complete.
- If something fails, rerun only the failing subset before broadening scope again.
- Keep command output bounded and avoid broad repository scans unless the current task requires them.

## CI and release gates

The canonical CI in `.github/workflows/ci.yml` runs:

```bash
uv sync --locked --extra dev
uv run ruff check .
uv run ruff format --check .
uv run pyright src
uv run pytest -q
```

Keep lint, static analysis, and tests aligned with this workflow when changing tooling or Python compatibility.

## Useful references in this repo

- `README.md`: product overview and installation details
- `RUN.md`: operational usage notes for the packaged commands
- `docs/PROJECT_SPEC.md`: functional contract and tool behavior
- `docs/ARCHITECTURE.md`: module boundaries and design intent
- `docs/SECURITY.md`: security expectations and denial cases
- `docs/TEST_STRATEGY.md`: test layers and release gates
- `examples/vscode.mcp.json`: IDE setup example for VS Code
- `examples/cursor.mcp.json` and `examples/portable.mcp.json`: MCP configuration examples for other clients

This file is intended to help future Copilot sessions stay within the repo’s actual architecture and operating constraints rather than using generic assumptions.
