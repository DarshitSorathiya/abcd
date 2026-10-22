# Repo Guide — Copilot Engineering Pack

This pack gives GitHub Copilot the project contract, architecture, security model, test plan, and build sequence for Repo Guide. It is **not the completed application**; use it to build the application inside this repository.

## Start here

1. Read `AGENTS.md` and `.github/copilot-instructions.md`.
2. Open the workspace in VS Code and select **Repo Guide Engineer** from Copilot's agent picker.
3. Follow `docs/COPILOT_WORKFLOW.md`. Work on one milestone at a time; do not ask Copilot to implement the entire project in one prompt.
4. Treat `docs/PROJECT_SPEC.md` as the functional contract, `docs/ARCHITECTURE.md` as the design boundary, and `docs/SECURITY.md` as mandatory acceptance criteria.
5. Record real test/evaluation results in `eval/results.md`. Never invent passing results.

## First Copilot prompt

> Read `AGENTS.md`, `.github/copilot-instructions.md`, `docs/PROJECT_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/TEST_STRATEGY.md`, and `docs/IMPLEMENTATION_PLAN.md`. Do not implement the whole product yet. Complete only Milestone M0: inspect the current workspace once, establish the package/test/config skeleton, choose and lock a compatible MCP Python SDK v2 release, add the minimum CI configuration, and update the implementation checklist. Keep the diff minimal. Do not run tests until this milestone's files are complete; then run the documented M0 validation commands once and report only changed files, command results, blockers, and next milestone.

## Product in one paragraph

Repo Guide is a local, read-only repository onboarding agent. It uses a Python MCP server to expose bounded tools for repository tree/file/search/history and public GitHub issues; a separate CLI agent uses a local Ollama model to choose tools, observe results, and stop when it has evidence. Final repository claims cite repository-relative `path:line` locations or commit hashes. Programmatic verification rejects invalid citations before output. MCP clients such as VS Code Copilot Chat and MCP Inspector can launch the same server independently; they use their own model. The Ollama CLI agent does not run inside Copilot Chat.

## Current protocol note (verified 21 Oct 2026)

Use the current stable MCP Python SDK **v2** and pin the exact version that passes the test suite. Do not copy older v1-only examples without checking API compatibility. The MCP protocol revision dated 28 July 2026 retired the Roots request flow; do not use `roots/list` to discover a workspace. Resolve the server root from `--repo`, then `REPO_GUIDE_ROOT`, then the current directory, and normalize git repositories to their top level. See `docs/DECISIONS.md`.

## Scope honesty

The implementation target is production-minded engineering: explicit trust boundaries, bounded resource use, robust errors, test coverage, CI, packaging, and security documentation. A local single-user prototype is not automatically “production certified.” Do not claim that all attacks are impossible or call the product production-ready until release gates, platform tests, and an independent security review have actually passed.

## Installation

Requires Python 3.11 or newer and Git. Install from the project directory, or use its absolute path from any current directory:

- Development: `python -m pip install -e ".[dev]"`
- Regular install: `python -m pip install .`
- Isolated user commands: `pipx install .`
- From another directory: `python -m pip install -e "/absolute/path/to/Repo Guide[dev]"` or `pipx install "/absolute/path/to/Repo Guide"`

Verify the installation with `repo-guide --help`, `repo-guide --version`, `repo-guide-mcp --help`, and `repo-guide-mcp --version`. To update, rerun the selected install command with `--upgrade` for pipx (`pipx upgrade repo-guide`) or reinstall the package with pip. Remove an isolated install with `pipx uninstall repo-guide`; remove a pip install with `python -m pip uninstall repo-guide` from the same environment.

Both commands work from arbitrary directories. By default the current directory is the root candidate; a nested Git directory resolves to its Git top level. `REPO_GUIDE_ROOT` sets the default, and `--repo PATH` takes precedence. Filesystem roots and the user's home directory remain refused. For a normal non-Git directory, explicitly use `--allow-non-git` for reduced filesystem-only mode.

If the command is not found, check that the environment's script directory is on `PATH`. For pipx, use `pipx ensurepath` only as a user-directed setup step, then open a new terminal; do not assume an IDE inherits the interactive shell's `PATH`. Locate an executable with `command -v repo-guide` on POSIX or `Get-Command repo-guide` in PowerShell. IDE MCP configuration should use an absolute executable path when necessary; see [docs/OPERATIONS.md](docs/OPERATIONS.md).

Packaging and CLI smoke tests were run on Linux with Python 3.12. Windows and macOS are supported targets but have not been tested in this workspace.

## IDE MCP clients

For VS Code, copy [examples/vscode.mcp.json](examples/vscode.mcp.json) to `.vscode/mcp.json` at the workspace root. It uses the VS Code `servers` format and `${workspaceFolder}` and passes that path explicitly to `repo-guide-mcp`.

For Cursor, copy [examples/cursor.mcp.json](examples/cursor.mcp.json) to `.cursor/mcp.json`. Cursor's project format uses `mcpServers`; it supports `${workspaceFolder}` interpolation in command arguments. For the portable Copilot format, use [examples/portable.mcp.json](examples/portable.mcp.json) as `.mcp.json` and replace the absolute repository path. Portable configuration does not share VS Code's workspace-variable mechanism; do not assume an unspecified current directory points at the intended repository.

Both IDEs use their own model to call this read-only MCP server. They do not run the Ollama-powered `repo-guide` CLI agent. Review workspace MCP configuration before trusting it: the client starts a local process with the user's permissions. Setup, executable path fallback, root verification, Inspector use, and client capability caveats are in [docs/OPERATIONS.md](docs/OPERATIONS.md).

## Evaluation and release status

The synthetic, pre-grounded evaluation fixture and reproduction instructions are in [eval/questions.md](eval/questions.md) and [docs/OPERATIONS.md](docs/OPERATIONS.md). Results belong in [eval/results.md](eval/results.md) and must reflect only actually executed checks. Citation path/line validation and one bounded reflection pass do not guarantee semantic correctness; this prototype is not security-certified.
