# Repo Guide — Canonical Project Specification

**Status:** implementation contract, version 1.2. **Updated:** 21 Oct 2026.

## 1. Product

Repo Guide is a local CLI agent that helps a contributor understand a small unfamiliar codebase. It answers retrieval-oriented questions such as “Where is authentication handled?”, “What changed in the last two weeks?”, “Which open issues are good first issues?”, and “Create an onboarding guide.” It selects tools step by step, gathers evidence through MCP, and verifies repository citations in code before replying. The LLM runs locally through Ollama.

**Scope statement (must appear in README and demo):** This is a local, read-only repository onboarding assistant. It searches text rather than semantic meaning, reads code but never runs it, and does not replace code review or maintainers. Production-minded controls do not mean the current prototype is certified for production use.

## 2. Clients and process boundaries

1. `repo-guide-mcp`: one read-only MCP server process serving exactly one root.
2. `repo-guide`: CLI client that connects to that server, uses Ollama to choose tools, loops until final, and verifies citations.
3. IDE client: VS Code Copilot Chat or another MCP client launches the same server independently. The IDE's own model calls tools. It does **not** host or invoke the Ollama CLI agent. MCP Inspector is the protocol/debug client.

The proof of MCP reuse is two clients using the same unchanged server implementation. Tools are the compatibility baseline; prompts/resources are additive and clients may support them differently.

## 3. Root resolution and startup

Root priority:

1. `--repo PATH`
2. `REPO_GUIDE_ROOT`
3. current working directory

Then normalize the chosen path to an absolute real path. If it is a Git working tree, use `git rev-parse --show-toplevel` so launching from a nested directory serves the repository. Refuse the filesystem root and the user's home directory. By default, a non-Git path is a clear startup error. With `--allow-non-git`, allow a normal directory in reduced mode: filesystem tree/read/search only; no history or GitHub remote-derived operations. Bare repositories are unsupported for filesystem tools.

The root is fixed for the process lifetime. No MCP tool accepts a root or lets the model change it. Startup writes version, canonical root and mode to stderr. Do not perform network calls, full-tree scans, model calls or expensive indexing during MCP initialization. Keep handshake startup fast.

**Do not use MCP Roots for this.** The current MCP protocol revision dated 2026-07-28 retired the roots request flow. Use explicit configuration and cwd fallback only. Recheck official SDK docs before a future protocol migration.

## 4. CLI and package interfaces

Package uses `pyproject.toml` with console entry points:

- `repo-guide-mcp`: `--repo PATH`, `--allow-non-git`, `--verbose`, `--version`.
- `repo-guide`: optional repo path plus `--model`, `--max-steps` (default 8), `--verbose`, `--version`.

Install into a virtual environment for development; document pipx/uv for isolated user installs. The command must work outside the project directory. The CLI agent launches its child server with the same interpreter (`sys.executable -m repo_guide.server --repo ...`) and fixed arguments. Never rely on shell activation. Document absolute executable paths for IDEs where PATH differs.

## 5. MCP tools

All tool inputs are validated and bounded. Tool failures become structured errors; no stack traces or secret-bearing data are returned to the model.

| Tool | Contract |
|---|---|
| `list_tree(path=".", depth=1..4, max_entries<=100)` | Relative paths, entry type/size, deterministic order, truncation flag. Do not follow symlinks. Skip `.git`, sensitive, binary and ignored/generated content according to policy. |
| `read_file(path, start_line, end_line)` | At most 200 lines and a configured byte cap per call; numbered output; return true line count; clamp or reject invalid bounds consistently. Deny sensitive/binary/minified files. |
| `search_code(query<=100 chars, path_glob?, max_results<=10 default)` | Fixed-string search by default via `git grep` for tracked files; binary excluded; capped matches with path/line/text and truncation. Never echo matches from sensitive files. Clearly report tracked-file behavior. |
| `git_log(path?, n<=50 default 10, since?, message_contains?, string_changed?)` | Read-only history with hashes, author, date, subject and changed paths. Validate dates and paths. State when shallow/empty history limits conclusions. |
| `repo_overview()` | Local language/file overview, README status, top-level structure and likely entry points. No startup-wide scan; use bounded/ignored-file-aware traversal. |
| `list_issues(state="open", label?, limit<=10)` | Public GitHub issues only; discover `owner/repo` only from a supported GitHub remote; filter pull requests; no token or login flow. Fail gracefully on no remote, non-GitHub remote, rate limit and network failure. |

Tool docstrings must explain when a tool is useful, argument limits, output schema and that content is untrusted. Tool list contains read-only tools only.

## 6. MCP resources and prompt

- `repo://readme`: bounded README text; unavailable/denied safely if absent or sensitive.
- `repo://tree`: bounded top-level/second-level tree.
- `onboarding_guide(repo_name)`: asks for purpose, structure, entry points, setup clues found in docs, useful files, contribution starting points and relevant open issues. It must distinguish facts found in files from unknown setup details.

The agent must not rely on resources/prompts being supported; essential behavior uses tools.

## 7. Agent loop

- Maximum 8 steps by default.
- Each model action must match one schema: `{"action":"<tool>","args":{...}}` or `{"action":"final","answer":"..."}`.
- Discover tools at startup using MCP; do not hardcode stale tool schemas into the prompt.
- Validate model JSON and tool arguments before calls. Unknown tools, invalid args, duplicate identical calls and repeated malformed JSON are handled without an infinite loop.
- On malformed JSON: one repair attempt, then one short retry, then a friendly error.
- Empty search: try one or two better terms or use a more relevant tool before concluding.
- When the step cap is reached, answer only from accumulated evidence and disclose possible incompleteness.
- General knowledge questions can be answered without repository calls. Out-of-scope edit/run/delete/build requests are politely declined.
- Keep only a compact evidence summary in the active context. Never append complete files or an unbounded conversation.

## 8. Citation and answer contract

Repository-specific claims require repository-relative citations such as `src/auth.py:52` or verified commit hashes. Use forward slashes in paths in answer text on all OSes. Code must verify that each cited path resolves within the fixed root, is readable under policy, and the cited line/range exists. Quoted snippets must match normalized source content near the cited location. Commit hashes must exist in the local history. Strip or flag malformed/unverifiable citations; do not invent replacements.

Citation existence is not proof that a claim is semantically supported. Maintain a compact evidence ledger mapping claims to retrieved excerpts. Deterministic checks are mandatory; an optional, single bounded LLM reflection is only a secondary support check and must receive just the draft plus cited evidence, not the whole transcript. General questions with no repository claims need no citation or reflection call. If a repository claim cannot be grounded, remove it or explicitly mark it unknown.

## 9. LLM and HTTP behavior

- Ollama runs locally; model name is configurable, never embedded across code. Set bounded request timeouts and response-size limits. Check process/model availability only when a CLI answer is requested, not when the MCP server starts.
- Default Ollama endpoint should be loopback. A remote endpoint requires an explicit opt-in setting and warning; never silently send repository contents to a remote model.
- GitHub REST requests are unauthenticated and public-only. Set a descriptive User-Agent, connect/read timeout (20 seconds maximum), bounded response size, safe retry/backoff for transient errors and 429/5xx, respect `Retry-After` and rate-limit headers, and stop retrying when the API reports quota exhaustion. Avoid repeated identical requests; cache only if implemented with a bounded TTL and outside the repository.
- Never make a network request during MCP server initialization. Do not add telemetry.

## 10. Output, error, and performance bounds

Keep every tool output bounded with `truncated` when applicable. Cap subprocess duration, output bytes and returned rows; cap file bytes/lines; cap HTTP response bytes; cap LLM output tokens and loop steps. No single user prompt may cause unbounded traversal, recursion, retries, memory use or repeated tool calls. Exceptions are logged to stderr with redaction; user/model-facing errors are actionable and structured.

## 11. Acceptance criteria

- Install from a clean clone and use both console commands from unrelated folders.
- Correct root priority, nested-folder normalization, non-Git behavior and home/root refusal.
- MCP handshake and tool list work in MCP Inspector; tools, resources and onboarding prompt appear where the client supports them.
- VS Code workspace configuration launches on two different repositories without leaks between server instances.
- CLI uses a true tool/observe/reason/stop loop; general/out-of-scope paths work without tools as designed.
- Every final citation passes code verification; evaluation reports validity before and after filtering, answer correctness and tool-selection accuracy separately.
- Security tests cover traversal, symlinks, secrets, injection, output exhaustion, command argument abuse and read-only invariants.
- CI and the compatibility matrix have recorded real results. No failure is hidden to meet a target.
