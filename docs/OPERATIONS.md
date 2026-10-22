# Installation, Client Setup and Troubleshooting

## Supported environment

Repo Guide requires Python 3.11 or newer and Git. Python 3.11+ is required by the exact pinned MCP SDK v2 release. Development-package pins are recorded in `uv.lock`; runtime dependencies are declared in `pyproject.toml`. Linux was exercised in this workspace; Windows and macOS have not yet been tested here.

## Installation modes

Run these commands from the project directory:

- Development: `python -m pip install -e ".[dev]"`
- Regular installation: `python -m pip install .`
- Isolated commands with pipx: `pipx install .`

From any other directory, supply the project path:

- Development: `python -m pip install -e "/absolute/path/to/Repo Guide[dev]"`
- Regular: `python -m pip install "/absolute/path/to/Repo Guide"`
- Isolated: `pipx install "/absolute/path/to/Repo Guide"`

For a reproducible locked development environment, use the committed `uv.lock` with `uv sync --locked --extra dev`.

After installation, check `repo-guide --help`, `repo-guide --version`, `repo-guide-mcp --help`, and `repo-guide-mcp --version`. Update a pipx install with `pipx upgrade repo-guide`; update a pip install by reinstalling the package in its original environment. Remove installations with `pipx uninstall repo-guide` or `python -m pip uninstall repo-guide` in that environment.

Do not install pipx or alter global PATH automatically as part of application startup or tests. If pipx is already available but command lookup fails, `pipx ensurepath` is an optional user-run setup command; start a new shell afterward. Locate the command with `command -v repo-guide`/`command -v repo-guide-mcp` on Linux/macOS, or `Get-Command repo-guide`/`Get-Command repo-guide-mcp` in PowerShell. Use the reported absolute path for IDE configuration if its PATH differs.

## Root selection from any folder

Both commands use the shared root resolver: `--repo PATH` > `REPO_GUIDE_ROOT` > current working directory. A nested Git directory resolves to its Git top level. Explicit `--repo` overrides the environment. Without an explicit path or environment value, an unrelated current directory is the selected candidate and must satisfy the existing root rules. The home directory and filesystem root remain refused. A non-Git directory requires `--allow-non-git`, which enables reduced filesystem-only mode.

Examples (replace paths with the actual repository):

- From a Git repository or nested folder: `repo-guide`
- From elsewhere: `repo-guide --repo "/path/to/repository"`
- With environment default: set `REPO_GUIDE_ROOT`, then run `repo-guide`
- Explicit path wins: `repo-guide --repo "/path/to/repository"`
- MCP server directly: `repo-guide-mcp --repo "/path/to/repository"`

The agent launches its child server using the current interpreter (`sys.executable -m repo_guide.server`) and passes the already resolved root as an argument. Paths containing spaces or Unicode are passed as individual process arguments; no shell activation or current-working-directory lookup is required for locating the installed module.

## Build and clean-install verification

Use the project environment's build frontend to produce wheel and source distributions. Install the wheel into a fresh virtual environment, then run both commands' `--help` and `--version` from an unrelated directory. Record the Python version, OS, exact commands, stderr startup root and observed exit codes. Do not claim installation or platform coverage that was not actually tested.

## M9 local evaluation

The hand-written rubric is in `eval/questions.md`; machine-readable questions are in `eval/questions.json`. `eval/run_eval.py` creates a synthetic repository and known commit history in a temporary directory. After Ollama is running and the selected model is already installed, run the evaluator with the desired model and save its JSON output under the evaluation directory. The script does not pull models or access live GitHub; the fixture has no remote, so Q10 checks the safe unavailable-remote behavior. Review each answer against the pre-written ground truth before entering manual correctness scores in `eval/results.md`. Keep required-term coverage labeled as a proxy, not semantic correctness.

## Any-folder smoke test

After installation, run both commands' `--version` from an unrelated folder. Then run `repo-guide` inside a Git repository and one nested subfolder. Startup diagnostics must go to stderr and show canonical root, mode and model; MCP startup also prints version and mode on stderr. MCP stdout is protocol-only.

## VS Code Copilot Chat configuration

1. Install Repo Guide in an environment visible to VS Code (or use the absolute executable fallback below).
2. Create `.vscode/` at the workspace root if needed, then copy `examples/vscode.mcp.json` to `.vscode/mcp.json`.
3. Review the local command and root argument before trusting the workspace.
4. Open Command Palette → **MCP: List Servers**, start/restart `repoGuide`, and inspect its server output. Startup diagnostics should show the canonical root, mode, and version on stderr.
5. In Copilot Chat, request a low-impact repository overview and inspect the actual tool call and result. Tools are the compatibility baseline; resources and prompts may appear or behave differently by client/harness.

The config uses the VS Code-specific top-level `servers`, `type: "stdio"`, and `${workspaceFolder}`. It explicitly passes `--repo`, so the server does not infer the workspace from process cwd. To refresh a changed tool catalogue, run **MCP: Reset Cached Tools** and restart the server. VS Code may forward eligible workspace servers to Copilot harnesses; input-variable-dependent servers are not forwarded. Repo Guide configuration uses no interactive inputs. The VS Code MCP documentation currently labels `.vscode/mcp.json` as a compatibility/deprecated destination in the guided flow; review the current destination guidance before team rollout and use the portable format for Copilot harnesses.

## Cursor configuration

Copy `examples/cursor.mcp.json` to `.cursor/mcp.json` in the project workspace. Cursor's documented project format uses top-level `mcpServers`; its stdio entry uses `type`, `command`, and `args`. Cursor currently supports `${workspaceFolder}` interpolation in these fields, so the example explicitly passes the project root. Restart/reconnect the MCP server from Cursor's MCP settings/Customize UI, then inspect its MCP logs (Output panel → MCP Logs) and issue a low-impact tool request.

Cursor uses its own model to call the Repo Guide MCP server. It does not automatically invoke the Ollama-backed `repo-guide` CLI. The server root is selected once at launch and cannot be changed by model tool arguments.

## Portable Copilot configuration

`examples/portable.mcp.json` uses the portable `mcpServers` format and an explicit absolute `--repo` placeholder. Place it at `.mcp.json` at the workspace root or in the documented Copilot user config. Portable `.mcp.json` does not support the VS Code-specific `${workspaceFolder}` variable or cwd property. Replace the placeholder for the target machine/workspace. If an absolute root cannot be supplied safely, do not rely on an assumed cwd: the server resolves `--repo` → `REPO_GUIDE_ROOT` → cwd and reports the selected canonical root on stderr.

## Executable discovery and PATH

IDE processes can have a different PATH from a terminal. Locate the installed executable in the same environment used for installation:

- Linux/macOS: `command -v repo-guide-mcp` (often an environment's `bin/repo-guide-mcp`; pipx exposes commands from its configured bin directory).
- Windows PowerShell: `Get-Command repo-guide-mcp | Select-Object -ExpandProperty Source` (often a Python environment's `Scripts\\repo-guide-mcp.exe`).
- uv tool install: locate the command with `uv tool dir --bin`, then check the actual `repo-guide-mcp` entry there; exact paths vary by uv configuration and platform.

Replace `command` in the client example with the exact reported executable path if the IDE cannot resolve PATH. Keep the `args` array (including `--repo` and the workspace path) as separate arguments. Do not use shell command strings, shell activation, or `shell=True`. No PATH modification or software installation is performed automatically. The server is the same installed package in all cases.

## MCP Inspector

The official MCP Inspector v2 package currently provides a CLI smoke mode. With Node.js installed, run from a terminal in a chosen repository:

1. List tools and schemas: `npx @modelcontextprotocol/inspector --cli repo-guide-mcp --repo "$PWD" --method tools/list`.
2. Read resources: repeat with `--method resources/list`, then `--method resources/read --uri repo://readme` and `--method resources/read --uri repo://tree`.
3. List prompts: repeat with `--method prompts/list`; use `--method prompts/get --prompt-name onboarding_guide --prompt-args repo_name=<name>` to render the onboarding prompt.
4. Call a low-impact tool: `--method tools/call --tool-name repo_overview`.
5. Confirm stderr reports the expected canonical root and mode. Use the same executable and args as the IDE config to test that exact launch.

The positional target is the executable followed by its argv; do not use a shell string. The Inspector CLI uses one short-lived connection per invocation. No live GitHub access is needed for local tools. The web Inspector is also available with `npx @modelcontextprotocol/inspector`; follow its current UI to configure the stdio command and arguments. Automated SDK protocol tests cover tools, resources, and prompts, but do not constitute a manual GUI Inspector test.

## Common failures

- **Command not found:** check the same environment with `command -v` or `Get-Command`; configure an absolute executable path or install with pipx/uv. A new shell may be needed after a user updates PATH.
- **Wrong root:** inspect stderr. `--repo` overrides environment and cwd. Relaunch the server; root is immutable for the process lifetime.
- **No Git history:** check if the directory is a worktree/shallow clone and whether `git rev-parse --show-toplevel` succeeds. Bare repositories are unsupported for file tools.
- **No issues:** confirm the `origin`/supported remote is a public GitHub remote, then check rate-limit/error output. The tool is unauthenticated and public-only.
- **Model missing:** verify Ollama is running and the configured model exists. The server itself should still start in an IDE without starting Ollama.
- **Tools stale in VS Code:** use **MCP: Reset Cached Tools**, then restart that MCP server.
- **Wrong root in an IDE:** inspect the server's stderr output and verify `--repo` is the intended workspace path. Each workspace launch has a separate process; restart after changing configuration.
- **Cursor cannot find the command:** inspect Cursor MCP Logs and replace `repo-guide-mcp` with the actual absolute path found by `command -v`, `Get-Command`, or the installed environment's bin directory.
- **Resource or prompt absent:** first confirm tool discovery and client support; resources/prompts are additive capabilities and are not surfaced identically by all clients.
- **Broken protocol:** ensure no `print()` or third-party logger writes to stdout. All diagnostics must go to stderr.
- **Windows PATH differs from terminal:** install in an environment visible to VS Code or use its absolute executable path. Windows cmd and PowerShell behavior remains unverified until those launch checks are run.

Keep troubleshooting factual. Record the versions, exact command and stderr excerpt without sharing secrets or entire repository contents.

## M8 compatibility record (2026-10-21)

Automated MCP SDK tests exercise discovery and calls for six read-only tools, `repo://readme`, `repo://tree`, and `onboarding_guide`; M7 packaging tests exercised installed command help/version and root resolution on Linux/Python 3.12. The M8 automated tests additionally cover config shape and process-root isolation. A GUI launch in VS Code, Cursor, and the Inspector web UI has not been performed in this workspace; Windows and macOS are also untested. Do not report those as passed.
