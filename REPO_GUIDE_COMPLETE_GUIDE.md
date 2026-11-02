# Repo Guide: Complete User and Developer Guide

This guide describes the checked-in implementation, not just the intended design. In particular, Repo Guide has an implemented read-only MCP server and a separate CLI agent, but the SQLite memory/cache helpers and `custom_server.py` are experimental and are not part of the normal installed command flow.

### Run

# Optional: standalone MCP server for an IDE client; the CLI below starts its own child server
`
pip install -e ".[dev]"

repo-guide-mcp --repo . --verbose

`
# terminal - 2

`
$secureKey = Read-Host "Gemini API key" -AsSecureString
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
$env:GEMINI_MODEL = "gemini-3.8-flash"

pip install -e ".[dev]"

repo-guide --provider gemini --verbose

`

## Contents

1. [What Repo Guide is for](#what-repo-guide-is-for)
2. [What it can and cannot do](#what-it-can-and-cannot-do)
3. [Example prompts](#example-prompts)
4. [Ways to install and run it](#ways-to-install-and-run-it)
5. [Can I use a repository URL without cloning?](#can-i-use-a-repository-url-without-cloning)
6. [Branches, read-only behavior, and security boundaries](#branches-read-only-behavior-and-security-boundaries)
7. [User flow and process architecture](#user-flow-and-process-architecture)
8. [Data flow for a CLI question](#data-flow-for-a-cli-question)
9. [MCP tools, resources, and prompt](#mcp-tools-resources-and-prompt)
10. [Module and file reference](#module-and-file-reference)
11. [SQLite memory and cache: current behavior and limitations](#sqlite-memory-and-cache-current-behavior-and-limitations)
12. [IDE integration](#ide-integration)
13. [Configuration reference](#configuration-reference)
14. [Limits, failure modes, and edge cases](#limits-failure-modes-and-edge-cases)
15. [Tests and maintenance](#tests-and-maintenance)

## What Repo Guide is for

Repo Guide is a local repository-onboarding assistant. It can help a contributor inspect a checked-out project by:

- listing a bounded portion of its directory tree;
- reading permitted text files and selected line ranges;
- searching literal text in Git-tracked files;
- summarizing local commit history;
- returning a small public GitHub issue listing when a supported GitHub remote is configured;
- producing a bounded structural overview and candidate entry points.

The CLI agent can use local Ollama or explicitly selected hosted Groq/Gemini models to choose which read-only repository tools to call. Answers are citation-verified by default; `--no-verify` is an explicit opt-out that prints the model answer without citation/provenance checks.

This project is useful when someone needs a quick, evidence-linked orientation to an unfamiliar codebase. It is not a code reviewer, a build system, a source-control client, a security certification, or a replacement for maintainers. It searches text and reads files; it does not understand every program semantically and does not run the repository's code.

The canonical behavior and security contracts are in [PROJECT_SPEC.md](./PROJECT_SPEC.md), [ARCHITECTURE.md](./ARCHITECTURE.md), [SECURITY.md](./SECURITY.md), and [TEST_STRATEGY.md](./TEST_STRATEGY.md).

## What it can and cannot do

| Capability | Current behavior |
|---|---|
| Inspect local repository | Yes, for the one root selected at server startup. |
| Read files | Yes, subject to path, sensitive-content, byte, and line policies. |
| Search code | Literal/fixed-string search over tracked files; untracked files are not a complete search surface. |
| Read history | Yes, from local Git history of the selected working tree; history may be shallow or absent. |
| List GitHub issues | Yes, for supported public `github.com` remotes, using unauthenticated API requests. Pull requests are filtered out. |
| Run application code, tests, builds, or shell commands | No. No arbitrary shell or repository-code execution tool is exposed. |
| Edit files, commit, push, switch branches, or change Git state | No. |
| Open a GitHub URL as a remote repository source | No. A local checkout or directory is required. |
| Use the CLI agent inside Copilot Chat/Cursor | No. IDE clients launch the MCP server and use their own model. |
| Guarantee that every model claim is semantically correct | No. Citation checks prove bounded properties about citations and evidence provenance, not full semantic truth. `--no-verify` turns even those checks off. |
| Prevent every possible data disclosure | No. Hosted Groq/Gemini receive the question and repository excerpts sent in prompts. IDE clients may send tool results to the model configured in that IDE. |
| Use SQLite memory/cache in the standard `repo-guide` command | No. Those helpers are not wired into the standard CLI flow. |

## Example prompts

Type a natural-language question at the `Question>` prompt. There is no special prompt syntax. Ask focused questions and name a file, symbol, date range, or label when you already know one; Repo Guide will choose from its discovered read-only tools.

### Repository orientation

```text
Give me an overview of this repository.
Show me the top-level folders and likely entry points.
What does the README say this project is for?
Where should a new contributor start reading?
```

### Find and understand code

```text
Where is the configuration loaded? Search for the configuration class and cite the relevant lines.
Find the definition of `resolve_root` and explain what it validates.
Read the first 40 lines of `src/repo_guide/agent.py` and summarize its role.
Search tracked files for `GEMINI_API_KEY`; show the matching paths and lines.
```

### Local history

```text
Show the 10 most recent commits.
What changed in `src/repo_guide/agent.py` recently?
Find commits from the last month whose message mentions timeout.
```

History questions require a Git checkout with usable local history. Repo Guide does not fetch remote history.

### Public GitHub issues

```text
List the five newest open issues.
Show open issues labeled `good first issue`.
Are there any open issues labeled `bug`?
```

Issue lookup requires a supported public `github.com` remote and network access. It returns issue metadata, not issue bodies.

### General and out-of-scope requests

```text
What is an MCP server?                         # General concept; may not inspect this repo.
What is the difference between HTTP and HTTPS? # General concept; may not inspect this repo.
Run the test suite.                            # Unsupported: Repo Guide does not execute commands.
Edit the README to add setup instructions.     # Unsupported: Repo Guide does not modify files.
```

General conceptual questions can be answered without repository evidence. Requests to edit/delete files, run tests/builds, or execute commands are declined; use your normal development tools for those tasks. Repo Guide also has no general web search, so avoid relying on it for live external information.

## Ways to install and run it

The project provides two installed entry points declared in [pyproject.toml](../pyproject.toml):

- `repo-guide-mcp`: starts the read-only stdio MCP server.
- `repo-guide`: starts the interactive CLI agent; it starts its own child MCP server for each question.

Install dependencies from the repository root:

```powershell
# Development install, including test/lint/type-check tools
python -m pip install -e ".[dev]"

# Or a locked development environment, if the committed lock is current
uv sync --locked --extra dev
```

### Supported launch patterns

1. **Installed MCP server command**

   ```powershell
   repo-guide-mcp --repo .
   ```

   This is the form an IDE MCP client launches. It speaks MCP over standard input/output; it is not an interactive Q&A chat.

2. **Installed interactive agent**

   ```powershell
   repo-guide --repo . --verbose
   ```

   At the `Question>` prompt, ask about the selected repository. The CLI writes answers to stdout and startup/status diagnostics to stderr.

3. **Run the package entry points through Python**

   ```powershell
   python -m repo_guide.server --repo .
   python -m repo_guide.agent --repo . --verbose
   ```

   The package must be installed in the selected Python environment (for example with the editable install above).

4. **Run with uv in the project**

   ```powershell
   uv run --project . repo-guide --repo . --verbose
   uv run --project . repo-guide-mcp --repo .
   ```

   This runs the corresponding project scripts in the uv-managed environment.

5. **Install as an isolated user command with pipx**

   ```powershell
   pipx install .
   repo-guide --repo C:\work\some-repository
   ```

   `pipx` must be installed separately, and its executable directory must be visible to the terminal/IDE.

6. **Install normally from a local wheel or source distribution**

   Build/package the project using the repository's configured build workflow, then install the resulting artifact with pip. This is a distribution route, not a separate runtime mode; the two commands above remain the product entry points.

7. **IDE-managed MCP process**

   Configure an IDE to launch `repo-guide-mcp` as a stdio server. See [IDE integration](#ide-integration). This exposes repository tools to the IDE model; it does not run the CLI's agent loop.

8. **Evaluation runner**

   `eval/run_eval.py` runs scripted evaluation questions against a synthetic temporary repository. It is a test/evaluation path, not a way to ask normal questions about the current project. Consult [OPERATIONS.md](./OPERATIONS.md) and [TEST_STRATEGY.md](./TEST_STRATEGY.md) before running it.

9. **Experimental custom runner**

   `src/repo_guide/custom_server.py` and `memory_cache.py` contain a separate prototype. It is not registered as a project console command, is not the standard MCP server, and has behavior/argument limitations described below. Do not treat it as the recommended production or lower-cost path.

### Select a repository root

Both entry points use the common root resolver. Its priority is:

```text
--repo PATH  >  REPO_GUIDE_ROOT  >  current working directory
```

A directory inside a Git worktree resolves to the worktree's top-level root. The root is fixed for the process; model tool arguments cannot change it.

Examples:

```powershell
# Current directory, if it is in a Git worktree
repo-guide

# Explicit local checkout
repo-guide --repo C:\work\service

# Explicit root for one terminal session
$env:REPO_GUIDE_ROOT = "C:\work\service"
repo-guide
Remove-Item Env:REPO_GUIDE_ROOT

# Non-Git folder: reduced filesystem-only mode
repo-guide --repo C:\work\source-snapshot --allow-non-git
repo-guide-mcp --repo C:\work\source-snapshot --allow-non-git
```

The home directory and filesystem root are refused as roots. Bare Git repositories are unsupported. A non-Git directory requires the explicit reduced-mode flag; Git history and remote-derived issue lookup are unavailable in that mode.

### Choose the CLI model provider

In `auto` mode, provider selection prefers Groq when `GROQ_API_KEY` is set, then Gemini when `GEMINI_API_KEY` is set, and otherwise Ollama at `http://127.0.0.1:11434` using `qwen3:8b`. Ollama must be running and that model must already be installed.

When `GROQ_API_KEY` is present in the CLI process environment, auto mode selects Groq ahead of Gemini. The default Groq model is `qwen/qwen3.8-27b`; `GROQ_MODEL` or `--model` can override it. The CLI announces that Groq receives the question and repository excerpts. A new API key does not reset Groq account quota or rate limits.

When Groq is not selected and `GEMINI_API_KEY` is set, auto mode selects Gemini. The default model is `gemini-3.8-flash`; `GEMINI_MODEL` or `--model` can override it. Use `--provider gemini` to select Gemini explicitly. The CLI announces that prompts and repository excerpts are sent to Google.

For PowerShell, enter a Groq key without putting it into a command, source file, or repository-local `.env` file:

```powershell
$secureKey = Read-Host "Groq API key" -AsSecureString
$env:GROQ_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
$env:GROQ_MODEL = "qwen/qwen3.8-27b"  # Optional; use an active chat model from Groq
repo-guide --repo . --verbose
Remove-Item Env:GROQ_API_KEY
Remove-Item Env:GROQ_MODEL -ErrorAction SilentlyContinue
Remove-Variable secureKey
```

If `GROQ_MODEL` was previously set to a safeguard/classification model, clear or replace it. A safeguard model is not a general-purpose answer model. Do not paste API keys into chat or commit them. The CLI reads credentials from process environment variables; it does not load `src/repo_guide/keys.env`.

Useful options:

```powershell
repo-guide --help
repo-guide --version
repo-guide --repo . --provider ollama --model qwen3:8b
repo-guide --repo . --provider groq --model qwen/qwen3.8-27b
repo-guide --repo . --provider gemini --model gemini-3.8-flash
repo-guide --repo . --max-steps 2
repo-guide --repo . --no-verify
repo-guide-mcp --repo . --verbose
```

The default maximum is two model decisions per question. `--max-steps` accepts a bounded value up to 32. Lowering it can reduce requests but may leave a complex answer incomplete. `--no-verify` prints the final answer without citation/provenance checks or reflection; repository claims are unchecked. A single decision may still fail with an HTTP 429 when a hosted provider's account/model limit is exhausted. No client-side setting overrides provider-side quota.

## Can I use a repository URL without cloning?

**No—not with the current implementation.** `--repo` accepts a local filesystem directory, not a GitHub URL. The MCP server reads files from that local directory, and local Git commands inspect its existing checkout/history. It does not clone, fetch, checkout, or download source code.

To analyze a remote repository, first clone it yourself using your normal Git tooling and credentials, then point Repo Guide at the local checkout:

```powershell
git clone https://github.com/OWNER/REPOSITORY.git C:\work\REPOSITORY
repo-guide --repo C:\work\REPOSITORY
```

Cloning a private repository requires that your Git client be authorized. Repo Guide does not accept or manage clone credentials. Its GitHub issue feature uses public unauthenticated API endpoints only; it does not make private source accessible.

Do not confuse issue lookup with source access: `list_issues` reads a Git remote URL from the local Git config, validates that it identifies a supported `github.com` repository, and requests public issue metadata from a fixed GitHub API origin. It does not fetch repository contents from that URL.

## Branches, read-only behavior, and security boundaries

### Does Repo Guide change branch security?

Repo Guide does not switch branches or write to the Git index/worktree. Its exposed Git operations are fixed read-oriented commands such as `rev-parse`, `grep`, `log`, `diff-tree`, `config`, and `cat-file`; subprocesses use argument arrays, `shell=False`, timeouts, bounded output, and a controlled environment. There is no tool for arbitrary Git commands, shell execution, checkout, commit, push, or file mutation.

The tools inspect the **currently checked-out local working tree and its local history**. Repo Guide does not override GitHub branch protection, organization permissions, signed-commit rules, or server-side branch policies, because it never pushes changes. It also does not select or inspect every remote branch automatically. If you have checked out another local branch, file reads reflect that working tree and `git log` reflects the history available from that checkout.

“Read-only” is a product boundary, not a guarantee against every possible compromise. A bug, compromised dependency, malicious IDE, or hostile model could still pose risks outside the intended tool contract. Review the MCP command/configuration before allowing an IDE to launch it; that process runs with the operating-system permissions of the user.

### What security controls exist?

- **Fixed root:** `resolve_root` resolves `--repo`, `REPO_GUIDE_ROOT`, or cwd once, normalizes Git worktrees to their top-level, rejects home/filesystem roots, and creates an immutable `RootContext`.
- **Path confinement:** repository paths must be relative; absolute paths, drive/UNC forms, traversal, NULs, and symlinks are rejected. Resolved paths must remain beneath the selected root.
- **Sensitive-content policy:** `.git`, `.env*`, credential-like names and directories, key/database suffixes, binary/non-UTF-8 content, known secret patterns, and minified content are denied by centralized policy. Secret detection is defense-in-depth; it cannot detect every secret.
- **Bounded reads/search:** file byte/line caps, tree depth/entry caps, query/result limits, subprocess timeouts/output caps, model request/response caps, and a step budget constrain resource use.
- **No repository execution:** repository files are treated as untrusted text. The model receives only the read-only MCP tool catalogue and bounded observations—not a shell, Python interpreter, or arbitrary subprocess tool.
- **Git subprocesses:** fixed allowlist, no shell, controlled Git environment, bounded runtime/output. Git remote URLs are parsed as data; they are not executed.
- **GitHub:** fixed `https://api.github.com` host, unauthenticated public requests, validated remote owner/repository, bounded responses and retry policy. Redirects are refused; issue bodies are not fetched.
- **Ollama:** loopback is the default. Remote Ollama requires explicit opt-in and HTTPS. The HTTP session does not inherit environment proxy settings.
- **Groq:** fixed HTTPS chat endpoint, TLS verification, no redirects, bounded payloads/timeouts; the API key is read from the process environment and is not included in prompts or logs. Prompts/repository excerpts are sent to Groq when this provider is selected.
- **Prompt injection:** repository, issue, commit, and tool text are labeled untrusted. Model output is schema-validated; tool name and arguments are checked before a call. These safeguards reduce risk but do not prove semantic correctness.
- **Citation checks:** cited paths/lines and commits are checked against the same root, policy, and this turn's retrieved provenance. Invalid or unverifiable repository claims are removed or replaced with a safe fallback.

The full threat model and adversarial cases are in [SECURITY.md](./SECURITY.md). These controls are not a security certification and do not make sharing confidential source with a hosted model risk-free.

> **Credential warning for this checkout:** `src/repo_guide/keys.env` is a Git-tracked path, and the CLI does not load it. Never store credentials there. Rotate any credential that has been placed in a tracked file or shared in chat; deleting a working-tree file alone does not remove a credential from Git history.

## User flow and process architecture

### CLI user flow

1. User starts `repo-guide`, optionally giving `--repo`, provider, model, and step limit.
2. CLI resolves the root and checks provider configuration. It reports root/mode/provider/model on stderr. For Groq or Gemini, it warns that questions and retrieved excerpts are sent to that hosted provider. `--no-verify` adds a warning that repository claims are unchecked.
3. User types a question at `Question>`.
4. For each question, the CLI starts a child MCP server in stdio mode using the same Python interpreter and the already-resolved root.
5. The client discovers the server's tools instead of assuming tool schemas. No full-repository scan or persistent content cache is built at startup.
6. The selected model returns one strict JSON action: either call a discovered read-only tool with arguments or return a final answer.
7. The agent validates the action and arguments, calls the tool if appropriate, stores a bounded observation, and repeats until a final answer or the step limit.
8. By default, the verifier checks citations against retrieved evidence and the repository. Groq and Gemini skip optional LLM reflection; Ollama can use one bounded reflection call. With `--no-verify`, the CLI bypasses both reflection and deterministic verification and warns that claims are unchecked.
9. The CLI prints the answer and returns to `Question>`. EOF or Ctrl-C exits and closes the model client.

### Process diagram

```text
CLI user
  |
  v
repo-guide (agent.py)
  |-- resolves one fixed RootContext (root.py)
  |-- selects Ollama, Groq, or Gemini chat client
  |
  +--> child Python process: repo_guide.server (stdio MCP)
  |      |-- discovers tools/resources/prompts (server.py)
  |      |-- reads files under safety.py policy
  |      |-- invokes bounded local Git operations (gitops.py)
  |      +-- optionally requests public GitHub issue metadata (github_api.py)
  |
  +<-- tool results / bounded evidence ledger
  |
  +--> chat model: tool decision(s), then final answer
  |
  +--> verify.py: citation/path/line/commit/evidence checks (unless --no-verify)
  |
  +--> answer to CLI stdout; diagnostics to stderr
```

The MCP server can also be started directly by an IDE. In that case the IDE supplies the model and owns the chat loop. The IDE does not automatically invoke Repo Guide's `agent.py`.

## Data flow for a CLI question

### Root selection

`resolve_root` accepts a local directory. Its central precedence is equivalent to:

```python
if repo is not None:
    candidate = repo
elif environ.get("REPO_GUIDE_ROOT"):
    candidate = environ["REPO_GUIDE_ROOT"]
else:
    candidate = cwd or Path.cwd()
```

The implementation then resolves the directory, rejects protected roots, checks Git, and uses `git rev-parse --show-toplevel` for worktrees. `--allow-non-git` admits a normal directory in reduced mode; it does not add Git history or remote capabilities.

### Agent action protocol

The model must return exactly one of these JSON shapes:

```json
{"action":"read_file","args":{"path":"src/repo_guide/agent.py","start_line":1,"end_line":25}}
```

```json
{"action":"final","answer":"..."}
```

The model does not get to select arbitrary programs or paths outside the discovered tools. JSON parsing rejects invalid JSON, duplicate keys, extra/missing fields, and incorrect value types. Tool arguments are checked against the discovered JSON Schema before `call_tool`.

### Worked example: "give me an overview of this repo"

Assume the CLI is running with Gemini selected and verification enabled (the default):

1. **The CLI starts the question turn.** It already resolved and fixed the repository root at startup. When you enter the question, it starts a child MCP server for that root using the same Python interpreter. Starting `repo-guide-mcp` separately is not required and does not provide the server for this CLI turn.
2. **The MCP client discovers tools.** It asks the child server for its current tool catalogue and schemas. This is a lightweight protocol handshake, not a full repository scan or startup cache.
3. **The agent checks the request.** Empty/oversized questions are rejected. Requests to edit or delete files, run commands/tests/builds, or execute code are declined locally before a model request. The overview question is allowed and proceeds to Gemini.
4. **Gemini chooses an action (model decision 1).** The prompt contains the system rules, your question, discovered tool descriptions/schemas, and any observations already gathered in this turn. With Gemini, the CLI sends that data to Google's API; Gemini 3 requests set low thinking and use streamed JSON output. The client buffers the stream until the JSON action is complete and validated.
5. **The agent validates and calls the tool.** If the action is `repo_overview`, the agent checks that the tool exists and its arguments match the discovered schema. The MCP server computes a bounded structural summary from a shallow tree: language counts, README presence, top-level entries, candidate entry points, and a truncation flag. It does not read or index the whole repository.
6. **The agent gathers citable README evidence.** After a successful overview result, the agent automatically asks the already-running MCP server to read at most the first 20 lines of a top-level README, if one is listed and `read_file` is available. This is a local tool call, not another Gemini request. Its numbered lines and the overview result are saved in the bounded, turn-local evidence ledger as untrusted repository data.
7. **Gemini writes the answer (model decision 2).** The agent sends a new prompt containing the question, tool catalogue, overview result, and README excerpt. Gemini returns a final JSON answer. The default CLI maximum is two model decisions; this common path uses one to select the overview tool and one to write the answer. The README read does not consume an extra model decision.
8. **The CLI handles verification and output.** By default, deterministic verification checks citations against current-turn evidence and the actual repository. Gemini answers do not trigger the optional LLM reflection pass. If verification succeeds, the answer is printed to stdout; diagnostics go to stderr. If a necessary citation is missing or invalid, the verifier may remove unsupported claims or use its safe fallback instead of showing the original answer.
9. **The turn ends.** The child MCP server is closed after this question. The evidence ledger is not a persistent cache. For the next question, the CLI starts another child server and discovers tools again.

To see request timing, use `--verbose`. To print the final model answer directly, use `--no-verify`; this bypasses both deterministic citation/provenance checks and reflection, and prints a stderr warning that repository claims are unchecked:

```powershell
repo-guide --provider gemini --verbose --no-verify
```

### Evidence and verification

Each tool result is serialized and bounded before entering the turn-scoped evidence ledger. The ledger records tool name, bounded arguments, result, error/truncation flags, and a content fingerprint. It retains a compact context rather than an unbounded transcript and marks repository observations as untrusted data.

For repository answers, deterministic verification examines repository-relative path/line citations or explicitly identified commits. A file citation must be readable under the same safety policy, have an in-range line/range, and be represented in successful non-truncated evidence from this turn. Quoted snippets are compared with normalized source text when present. Commit citations must match local history. A citation's existence alone does not establish that the answer's meaning is correct.

If invalid claims are found, the verifier removes the smallest affected sentence/claim it can safely identify, then verifies remaining citations again. It will not invent replacement citations. If checks fail, it returns a safe fallback instead of presenting the unsupported repository claim as fact.

The interactive CLI has an explicit `--no-verify` opt-out. In this mode, the agent still parses/validates the model action and enforces the read-only MCP tool boundary, but after a final model answer it skips the citation/provenance verifier and the optional reflection call. The answer is printed as returned by the model, with a startup warning that repository claims and citations are unchecked. Programmatic `run_question()` remains verified by default.

### Questions outside the supported scope

- **Requests to change the repository or execute something** (for example, "edit this file", "delete the config", "run the tests", or "build the project") match the CLI's local out-of-scope guard. Repo Guide returns a brief refusal without calling Gemini or MCP tools. The MCP server itself also exposes no write, shell, build, test, or arbitrary execution tool.
- **General conceptual questions** (for example, "what is a pull request?") can be answered by the selected model without repository tool calls. The answer is general model output, not a fact checked against this checkout.
- **Unrelated or live-information questions** (for example, current weather or breaking news) are not repository tools/features. The CLI has no general web-search tool; do not treat any model response as current or independently sourced.
- **Repository questions outside available tools** (for example, asking what a file does when the model has not read it) may require more tool steps or a different question. The agent has a bounded step budget; if exhausted, it reports an incomplete investigation rather than running arbitrary commands.
- **External/private source requests** are not supported as remote repository access. Use a permitted local checkout. Public GitHub issue metadata is the only supported GitHub lookup, and only through a recognized public GitHub remote.
- **Invalid or ungrounded repository answers:** by default, citation/provenance verification may sanitize the response or replace it with a safe fallback. `--no-verify` prints the answer as-is but removes that safeguard.

### Network data

- **Groq:** receives the question, system/tool prompt, and bounded repository observations included in model requests. The key is sent only in the HTTPS authorization header. HTTP 429 can be a transient rate limit or exhausted account/model quota; waiting only helps the former. HTTP 413 indicates a request-size limit. Repo Guide does not retry Groq requests automatically.
- **Gemini:** receives the question, system/tool prompt, and bounded repository observations included in model requests. Its key is sent in the `x-goog-api-key` header. The CLI uses streamed `streamGenerateContent` for Gemini and does not automatically retry provider errors.
- **GitHub:** only runs when the issues tool is called. It derives owner/repository from the local Git remote and sends a bounded unauthenticated GET to the fixed API host. It returns issue number/title/labels/canonical URL; issue bodies are not fetched, pull requests are excluded.
- **Ollama:** receives prompts over the configured local endpoint by default. Remote endpoints are denied unless explicitly opted into with HTTPS.

## MCP tools, resources, and prompt

### Tools

| Tool | Purpose and key limits |
|---|---|
| `list_tree(path=".", depth=2, max_entries=100)` | Lists a deterministic bounded tree. Depth is 1–4; entries cannot exceed configured cap. Skips excluded/generated and denied entries; symlinks are identified but not followed. |
| `read_file(path, start_line=1, end_line=None)` | Reads a safe UTF-8 file and returns numbered lines. Default line cap is 200; file cap is 1,000,000 bytes. Invalid ranges, missing files, denied paths/content, binary files and too-many-lines fail safely. |
| `search_code(query, path_glob=None, max_results=10)` | Fixed-string Git search over tracked files. Query is 1–100 characters; result cap defaults to 10. A search result may be truncated; untracked files are not a comprehensive search target. |
| `git_log(path=None, n=10, since=None, message_contains=None, string_changed=None)` | Reads local commit metadata, with validated filters and cap of 50 commits. Reports shallow history/truncation where available. It does not fetch remote history. |
| `repo_overview()` | Returns bounded language counts, README presence, top-level entries, candidate entry points, and truncation state. Candidate entry points are guesses based on names, not proof the project runs. |
| `list_issues(state="open", label=None, limit=10)` | Requests at most 10 public issues from a supported GitHub remote. No auth; pull requests and bodies are excluded. Fails if no supported remote, reduced mode, network/rate limit, or public repository not found. |

Errors are converted to structured safe tool errors; raw stack traces and secret-bearing response bodies are not intentionally returned to the model. Protocol stdout is reserved for MCP messages; diagnostics are written to stderr.

### Resources and prompt

- `repo://readme`: first readable root README among `README.md`, `README.rst`, `README.txt`, and `README`, truncated to 32,000 UTF-8 bytes.
- `repo://tree`: JSON tree at up to two levels and a 100-entry cap, further shortened to 32,000 bytes.
- `onboarding_guide(repo_name)`: supplies an investigation prompt covering purpose, structure, README, likely entry points, setup clues, and contributor starting points. It asks the model to distinguish observations, inferences, and unknowns.

Clients may not support resources or prompts consistently. The essential CLI agent behavior uses tools; it does not depend on resources or prompts being available.

## Module and file reference

### Package and configuration

| File | Responsibility |
|---|---|
| [pyproject.toml](../pyproject.toml) | Package metadata, Python floor, pinned runtime/dev dependencies, entry-point scripts, Ruff/Pyright/Pytest configuration, wheel/sdist inclusion. |
| [uv.lock](../uv.lock) | Locked dependency resolution for uv installs. Keep it synchronized when manifests change. |
| [\_\_init\_\_.py](../src/repo_guide/__init__.py) | Package version constant. |
| [config.py](../src/repo_guide/config.py) | Immutable `AgentSettings` and `SafetyLimits`, default models/endpoint, and validation of numeric/URL-related limits. The CLI currently defaults to two model decisions per question. |
| [constants.py](../src/repo_guide/constants.py) | Shared caps for citations, evidence, file/tree/search/history, agent steps, JSON, HTTP, and paths. Some values are legacy/duplicated; when defaults differ, inspect the active `AgentSettings` or `SafetyLimits` consumer. |
| [errors.py](../src/repo_guide/errors.py) | `RepoGuideError` with stable safe `code` and `message`; `RootResolutionError`, `PathPolicyError`, `ConfigurationError`, and `AgentError` specialize it. `as_dict()` provides a structured safe representation. |

### Root, filesystem safety, and Git

#### `root.py`

- `RootMode` distinguishes full Git mode from reduced filesystem-only mode.
- `Capability` names filesystem, Git history, and GitHub issue capability classes.
- `RootContext` is a frozen root path/mode/limits bundle; `require_capability()` denies Git-dependent capabilities in reduced mode.
- `resolve_root()` applies `--repo > REPO_GUIDE_ROOT > cwd`, resolves/validates the directory, checks for a bare repo, finds Git top-level, and enforces protected-root rules.
- `_reject_protected_root()` refuses filesystem root and user home.
- `_run_git()` executes only root-resolution `rev-parse` checks using an argument array, fixed environment, no shell, timeout, and output bounds.

#### `safety.py`

- `resolve_repo_path()` validates a relative path, checks components for symlinks, resolves containment under the fixed root, and applies the sensitive-path rules.
- `validate_repo_relative_path()` validates and normalizes a path/glob without filesystem access.
- `is_sensitive_repo_path()` exposes the centralized path-name policy to other modules.
- `read_repo_file()` opens a bounded read-only UTF-8 file and applies byte, binary, secret-pattern, minified-file, and line-count checks.
- `_validate_relative_path()` rejects empty/NUL, absolute/drive/UNC, and traversal paths after Unicode normalization.
- `_is_sensitive_path()` denies `.git`, `.env*`, credential/key/token components and configured sensitive suffixes/directories.
- `_looks_binary()`, `_looks_minified()`, and `_contains_secret_pattern()` implement content checks. Pattern scanning catches known forms, not all secrets.
- `_open_readonly_beneath()` uses no-follow/open-beneath style safeguards where supported and a validated path approach on other platforms. Platform-specific behavior should be tested on the actual target OS.

#### `gitops.py`

Public operation functions:

- `list_tree()` walks directories breadth-first, sorts deterministically, enforces depth/entry caps, skips excluded/sensitive paths, and does not traverse symlinks.
- `read_file()` validates line ranges, delegates path/content checks to `safety.py`, and returns numbered lines plus total line count.
- `search_code()` calls fixed-string `git grep` over tracked text, validates optional path glob, then re-reads candidate text through the safety policy before returning matching lines.
- `git_log()` validates date/path/text filters, checks shallow/empty history, gathers bounded commit metadata and changed paths, and filters sensitive names.
- `repo_overview()` derives language counts, root README presence, top-level entries, and known likely entry-point names from a bounded tree.
- `configured_remotes()` reads local Git config values without contacting remotes.
- `commit_exists()` checks a well-formed local commit hash with fixed Git arguments.
- `analyze_dependencies()` reads supported manifest files and aggregates dependency records; see the caveat below.

Data types: `TreeEntry`, `TreeResult`, `NumberedLine`, `FileReadResult`, `SearchMatch`, `SearchResult`, `Commit`, `GitLogResult`, `RepoOverview`, `DependencyInfo`, and `DependencyAnalysis` carry structured results.

Private helpers:

- `_parse_pyproject_deps()`, `_parse_requirements_deps()`, `_parse_package_json_deps()` parse common dependency manifests.
- `_parse_requirement_line()` and `_extract_version()` normalize requirement lines and version hints.
- `_validate_query()` enforces bounded, nonempty, single-line search/filter text.
- `_is_excluded_path()` excludes generated/vendor/cache directories.
- `_run_git()` restricts allowed Git subcommands, uses `shell=False`, bounded output/time, controlled environment, and kills over-producing/timed-out processes.

`analyze_dependencies()` is a local parser utility; it is not currently exposed as an MCP tool. It skips inaccessible/unparseable manifests, so its counts are only a partial inventory.

### MCP server

#### `server.py`

- `build_server(context, verbose=False)` binds one root to an MCP server and registers the six tools, two resources, and onboarding prompt.
- Nested `tool_result()` converts dataclasses/tuples to JSON-friendly values and optionally logs tool names.
- Nested `tool_error()` maps safe Repo Guide errors to MCP tool errors.
- Nested handlers `list_tree_tool()`, `read_file_tool()`, `search_code_tool()`, `git_log_tool()`, `repo_overview_tool()`, and `list_issues_tool()` validate through their underlying operations and convert safe failures.
- `readme_resource()` reads one approved root README under policy.
- `tree_resource()` returns a bounded JSON tree.
- `onboarding_guide()` returns the investigation prompt text.
- `_json_value()` recursively serializes dataclasses, dictionaries, and sequences.
- `_truncate_utf8()` truncates at a valid UTF-8 boundary and adds a marker.
- `_parse_args()` defines the MCP server flags.
- `main()` configures stderr logging, resolves one root, reports startup state to stderr, and runs stdio transport. Broken pipe, EOF, and Ctrl-C exit cleanly.

The server is read-only by design. Its process lifetime and root are controlled by the local MCP client configuration.

### Agent and evidence

#### `agent.py`

- `ToolDefinition`, `AgentTurnResult`, and `_Action` represent discovered MCP schemas, turn output/evidence, and one validated model action.
- `build_server_parameters()` creates the child process parameters using `sys.executable -m repo_guide.server` and the already-fixed root.
- `discover_tools()` enumerates/paginates tool definitions, validates schema presence and enforces tool count/name uniqueness.
- `run_agent_turn()` builds a bounded tool catalogue, gets model actions, validates action/tool arguments, calls tools with timeout, records observations, guards duplicate calls, and stops at final answer or step limit.
- `_validate_tool_arguments()` checks JSON Schema validity and supplied arguments.
- `_parse_action()` rejects invalid, ambiguous, duplicate-key, extra-key, or wrong-shape JSON.
- `_request_action()` calls the model and recovers from malformed JSON. For the standard Groq client, the current rate-reduction behavior uses one request and does not send repair retries; the local Ollama path retains bounded repair behavior.
- `_make_user_prompt()` combines question, discovered catalogue, and bounded evidence context.
- `_serialize_catalogue()` serializes tools and rejects catalogues above the context cap.
- `_tool_result_payload()` converts results to bounded JSON-like untrusted data.
- `_record_overview_readme()` reads at most 20 lines from a top-level README after a successful `repo_overview` call so the final answer can cite actual current-turn lines.
- `_record_correction()` records one correction attempt per repeated action signature.
- `_action_signature()` creates a stable JSON signature for loop detection.
- `_evidence_dicts()` serializes ledger observations for verification.
- `_safe_failure_result()` and `_step_limit_result()` produce incomplete, evidence-limited outcomes.
- `_find_repo_guide_error()` finds safe Repo Guide exceptions nested in async task-group errors so useful safe messages can be displayed.
- `_reject_json_constant()` and `_reject_duplicate_json_keys()` reject non-standard JSON constants and duplicate object keys.
- `_run_turn_with_server()` launches the child MCP process, discovers tools, runs the agent, and verifies the answer by default. Groq/Gemini skip optional LLM reflection while preserving deterministic checks; the CLI's explicit `--no-verify` path skips final verification.
- `run_question()` is the public single-question wrapper shared with evaluation.
- `main()` parses CLI flags, selects provider/model, reports hosted-provider and optional no-verification notices, loops over user questions, and closes the client.

The question loop can use one model request for each decision, up to two by default (or the configured cap), and some provider/model responses may fail strict JSON validation. Hosted Groq/Gemini paths intentionally do not multiply such failures with repair requests.

#### `evidence.py`

- `Observation` stores a tool name, bounded args/result, error/truncation flags, and fingerprint.
- `EvidenceLedger.record()` bounds/serializes results, tracks unique fingerprints/generation, caps errors and total observations.
- `EvidenceLedger.context_text()` builds a compact recent context with explicit untrusted-data labels and a summarized error section.
- `_bound_arguments()` clips oversized arguments safely.

The ledger is per-turn memory, not persistent conversation memory and not a response cache.

### Citation verifier

#### `verify.py`

- `Citation`, `CitationFinding`, and `VerificationReport` represent parsed references, their verification status, and final report/metrics.
- `extract_citations()` finds repository-relative `path:line`/range citations and explicitly named commits, ignoring URL/fenced-example contexts and limiting count.
- `verify_answer()` deterministically validates citations and sanitizes claims; on verifier failure it returns a safe fallback rather than the original unsupported answer.
- `verify_and_reflect()` optionally runs one bounded secondary model check for unsupported claims, sanitizes exact claim substrings, and runs deterministic verification again. The standard Groq/Gemini CLI paths skip this optional request. `--no-verify` skips deterministic verification too.
- `_verify_citations()`, `_verify_file_citation()`, and `_verify_quote()` check evidence provenance, root/sensitive-file policy, line bounds, local commit existence, and quoted content.
- `_normalize_whitespace()` normalizes quote comparison.
- `_attributed_quote()` extracts quote text associated with a citation.
- `_citation_from_token()`, `_looks_like_repository_path()`, `_near_example_marker()`, and `_overlaps()` support safe citation parsing.
- `_provenance_from_evidence()` and `_record_file_lines()` derive only successful, non-truncated current-turn evidence.
- `_sanitize_invalid_citation_claims()`, `_sentence_spans()`, and `_sanitize_reflection_claims()` remove claims tied to invalid citations or exact unsupported-claim reports.
- `_parse_reflection()`, `_reject_constant()`, and `_reject_duplicate_json_keys()` validate the reflection response shape, constant values, duplicate keys, and claim sizes/count.
- `_check_json_depth()` is defined as a recursion-depth helper but is currently not called by `_parse_reflection()`; do not assume a separate explicit JSON-depth check is active.
- `_bounded_evidence()` limits reflection payload evidence.
- `_question_requires_repository_evidence()` distinguishes likely repository questions from general questions.
- `_rate()`, `_finding_text()`, `_compute_content_fingerprint()`, and `_safe_fallback()` produce metrics and safe output.

Reflection is secondary: it can reduce some unsupported content, but it does not prove a claim true. Deterministic citation checks are mandatory in both paths.

### Model clients

#### `ollama_client.py`

- `ChatClient` is the shared provider protocol.
- `OllamaClient` posts strict JSON chat requests to `/api/chat`, validates bounded responses, reports unavailable/missing-model/timeout errors, and closes owned sessions.
- `_validated_chat_url()` requires a valid origin, defaults to loopback HTTP, and requires explicit opt-in plus HTTPS for remote endpoints.
- `_new_session()` disables inherited proxy/environment behavior.
- `_read_response()` bounds streamed response bytes and handles HTTP stream errors.
- `_response_mentions_missing_model()` detects a model-missing error in a bounded response.
- `_closing_response` closes the response on every path.

#### `groq_client.py`

- `GroqClient` posts OpenAI-compatible JSON chat-completion requests to a fixed Groq HTTPS endpoint. It applies connect/read timeouts, request/response bounds, TLS verification, no redirects, and safe HTTP errors.
- HTTP 429 now produces an actionable rate/usage-limit message and includes a numeric `Retry-After` delay if present. It does not automatically retry.
- HTTP 413 produces a request-too-large message.
- `_new_session()` disables inherited proxies/environment settings.
- `_read_response()` enforces content length and streamed body caps.
- `_closing_response` guarantees response closure.

Neither client reads a key from `src/repo_guide/keys.env`.

### GitHub API

#### `github_api.py`

- `GitHubRemote`, `GitHubIssue`, and `IssueListResult` are bounded result types.
- `parse_github_remote()` accepts supported HTTPS/SSH GitHub remote forms and rejects lookalike hosts, credentials, malformed paths, and unsupported schemes.
- `discover_github_remote()` prefers `origin`, then safe configured remotes, without contacting them during discovery.
- `list_issues()` makes a bounded public unauthenticated request, applies retry/rate-limit logic, and never fetches issue bodies.
- `_validate_issue_arguments()` checks state/label/limit.
- `_valid_remote_component()` validates owner/repository components.
- `_new_session()` disables inherited environment proxies.
- `_read_bounded_body()` enforces HTTP response-size limits.
- `_parse_issues()` filters pull requests and validates/truncates titles and labels.
- `_parse_remaining()`, `_rate_limit_exhausted()`, `_respect_rate_reset()`, `_sleep_retry_after()`, `_sleep_backoff()`, and `_backoff_delay()` implement bounded GitHub rate/backoff behavior.
- `_closing_response` closes streamed responses.

GitHub API availability, public/private visibility, rate limits, and network access remain external dependencies of issue lookup.

### Experimental helpers and evaluation

#### `memory_cache.py` and `custom_server.py`

These are described in [SQLite memory and cache](#sqlite-memory-and-cache-current-behavior-and-limitations). They are not imported by the standard `repo-guide` entry point, and `custom_server.py` is not registered in `pyproject.toml`.

- `memory_cache._init_db()` creates the two tables at import time; `Memory.get()`/`set()` are simple key/value persistence; `Cache.get()`/`set()` record raw lookup hits/misses; `Cache.ratio()` reports the aggregate ratio; `fallback_model()` chooses a model ID from process environment/defaults; `run_until_goal()` repeatedly calls the full agent turn and writes step/goal markers.
- `custom_server.main()` is an experimental interactive CLI loop despite its name and server-related imports; it does not register/run an MCP stdio server. Its raw argument parsing is not compatible with documented `--repo PATH` syntax. Prefer `repo-guide` or `repo-guide-mcp`.

#### `eval/`

- `questions.json`, `questions.md`, and template files describe evaluation prompts/rubrics.
- `fixture/` contains a synthetic repository fixture.
- `run_eval.py` prepares/runs the evaluation workflow and emits results; it is not the regular CLI.
- Evaluation results must be based on actually executed models/tests, not inferred from expected outputs.

#### Tests

- `tests/unit/`: root and Git-operation tests.
- `tests/security/`: adversarial path/content safety cases.
- `tests/integration/`: MCP server, GitHub client, agent, verifier, packaging, IDE configuration, and evaluation integration tests.
- `tests/test_smoke.py`: broad smoke-level behavior.

The default suite uses fixtures/mocks and should not require live Groq, Ollama, or GitHub.

#### Other repository documentation/config files

- `AGENTS.md`, `CLAUDE.md`, and `.github/copilot-instructions.md` provide assistant/developer workflow guidance.
- `.github/instructions/python.instructions.md` and `.github/instructions/citation-verification.instructions.md` apply specialized coding rules.
- `docs/IMPLEMENTATION_PLAN.md`, `DECISIONS.md`, `OPERATIONS.md`, `COPILOT_TASKS.md`, and `COPILOT_WORKFLOW.md` record milestone, operational, and workflow information; reconcile these with executable code if they disagree.
- `examples/vscode.mcp.json`, `cursor.mcp.json`, and `portable.mcp.json` provide MCP client configuration examples.
- `vscode-extension/package.json` describes the small VS Code extension package surface; it does not make the CLI agent run as an IDE model.
- Deployment/final report markdown and root scripts are project artifacts, not console entry points unless explicitly registered in `pyproject.toml`.

## SQLite memory and cache: current behavior and limitations

### What the prototype creates

Importing [memory_cache.py](../src/repo_guide/memory_cache.py) sets a fixed database path:

```python
DB = Path.home() / ".repo_guide" / "agent.db"
DB.parent.mkdir(parents=True, exist_ok=True)
```

It initializes two SQLite tables:

```sql
CREATE TABLE IF NOT EXISTS memory (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    value TEXT,
    hits INTEGER DEFAULT 0,
    misses INTEGER DEFAULT 0
);
```

`Memory.get(key, default)` reads a string value; `Memory.set(key, value)` writes/replaces it. `Cache.get(key)` returns a cached string and increments `hits`; if absent, it creates the key if needed, increments `misses`, and returns `None`. `Cache.set(key, value)` stores a result. `Cache.ratio()` calculates total hits divided by total hits plus misses, or `0.0` if there have been no lookups.

The separate `fallback_model()` helper chooses `GROQ_MODEL` when a `GROQ_API_KEY` environment variable is present; otherwise it chooses `REPO_GUIDE_MODEL` or the Ollama default. It does not load an env/key file.

### Intended use case and expected impact

A correctly integrated response cache could avoid a repeated model/tool computation when the same normalized question is asked against the same repository state, provider, model, and settings. Persistent memory could retain an explicit user preference or session marker across process restarts. That could reduce latency and provider charges for cache hits, but introduces freshness, privacy, invalidation, and cross-repository isolation requirements.

Without persistence, the standard CLI pays for each model turn and forgets prior questions after the process/turn. It still keeps a bounded in-memory evidence ledger during a single answer. This is separate from semantic conversation memory.

### What actually happens now

The standard `repo-guide` command does not instantiate `Memory` or `Cache`. Its normal cost behavior is governed by the model-decision budget, JSON-repair behavior, optional reflection policy, provider limits, and tool-result/context sizes.

`run_until_goal()` is only called by the experimental helper. It reruns the full `_run_turn_with_server()` before looking up its cache key. It uses `question + ":" + step` as the key, so different loop steps are different cache entries; a cache hit cannot avoid the model call that already happened. It writes the resulting answer only after that call. The `Memory` values (`last_step`, `goal`) are written but not used to resume a later run. Therefore, the prototype's cache/memory currently does **not** reduce Groq requests or provide durable conversation continuity in the normal product flow.

Illustrative sequence from the current helper:

```python
result = run_full_agent_turn(question)  # model/network work already happened
key = question + ":" + str(step)
cached = cache.get(key)                # lookup is after the expensive work
if cached is None:
    cache.set(key, result.answer)
```

This is deliberately shown as a diagnosis of the current ordering, not a recommended cache design.

### Important caveats before using the prototype

- `custom_server.py` is not a configured console script; its command-line handling treats the first raw argument as the repository path rather than parsing the normal CLI flags.
- Importing the helper creates `~/.repo_guide/agent.db` and its parent directory as an import-time side effect.
- Cache keys omit repository identity/revision, provider, model, safety-policy version, and settings. Reusing these entries for answers would risk stale or cross-context results.
- Cache values and memory values persist on disk without TTL, size bound, encryption, or repository-content invalidation.
- No cleanup/eviction or database migration layer exists.
- `run_until_goal()` catches broad exceptions and prints exception text; that is not suitable as a hardened production boundary.
- The database is user-local, but any process running as the same user may be able to read it. Do not store API credentials or confidential answers in it.

Before making caching a real cost optimization, design a canonical cache key containing at least root identity, Git revision/dirty-state policy, normalized question, provider/model, prompt/tool schema version, and relevant settings. Avoid caching errors or incomplete answers; use a TTL and size bound; re-run deterministic citation verification on every cache hit; isolate data between repositories; and add tests proving repeated identical questions cause fewer provider calls while changed files invalidate stale entries. Do not claim these behaviors exist until implemented and tested.

## IDE integration

IDE integrations use the MCP server, not the CLI agent. Each IDE launches a local stdio process, passes the workspace root as `--repo`, discovers tools, and lets the IDE's own configured model call them.

### VS Code

The example [vscode.mcp.json](../examples/vscode.mcp.json) uses the VS Code-specific `servers` object and `${workspaceFolder}`:

```json
{
  "servers": {
    "repoGuide": {
      "type": "stdio",
      "command": "repo-guide-mcp",
      "args": ["--repo", "${workspaceFolder}"]
    }
  }
}
```

Place the config where the current VS Code MCP workflow expects it (the existing operations guide describes `.vscode/mcp.json` and current compatibility caveats). Start/restart the server through VS Code's MCP controls and inspect its output. If VS Code cannot find `repo-guide-mcp` because its PATH differs from the terminal, replace `command` with the absolute executable path.

### Cursor

The example [cursor.mcp.json](../examples/cursor.mcp.json) uses top-level `mcpServers` and `${workspaceFolder}`:

```json
{
  "mcpServers": {
    "repoGuide": {
      "type": "stdio",
      "command": "repo-guide-mcp",
      "args": ["--repo", "${workspaceFolder}"]
    }
  }
}
```

Place it in the Cursor project MCP config location, reconnect/restart the server in Cursor, and inspect MCP logs. Use the actual installed executable path if needed.

### Portable MCP/Copilot configuration

The portable [portable.mcp.json](../examples/portable.mcp.json) uses `mcpServers`, but an absolute path placeholder must be replaced for each machine/repository:

```json
{
  "mcpServers": {
    "repoGuide": {
      "command": "repo-guide-mcp",
      "args": ["--repo", "/ABSOLUTE/PATH/TO/REPOSITORY"]
    }
  }
}
```

Do not assume `${workspaceFolder}` works in every portable MCP config format. Use the format and path interpolation supported by the exact client.

### What happens after setup

1. The IDE starts the configured command as a child process.
2. The MCP server resolves and fixes the root once, then reports its root/mode/version to stderr.
3. The IDE connects over stdio and discovers tools/resources/prompts supported by that client.
4. When asked a repository question, the IDE model may call one or more Repo Guide tools.
5. Tool results return to the IDE/model; Repo Guide's CLI evidence ledger and verifier are not automatically in this IDE path.

That last distinction matters: the CLI performs its own citation verification; the IDE path delegates answer generation to the IDE model and does not inherently run `verify.py`. Tool handlers still enforce path policy and bounded outputs, but the IDE's final natural-language answer is not passed through the CLI verifier unless the client separately implements that behavior.

Review the command and root argument before enabling a workspace MCP server. The child process has the current user's local permissions. Keep credentials out of MCP configuration and repository files.

## Configuration reference

| Setting/argument | Used by | Meaning |
|---|---|---|
| `--repo PATH` | Both commands | Local repository/directory root; overrides environment and cwd. |
| `REPO_GUIDE_ROOT` | Both commands | Default local root when `--repo` is absent. |
| `--allow-non-git` | Both commands | Explicitly permit a normal non-Git directory in reduced mode. |
| `GROQ_API_KEY` | `repo-guide` | Presence selects Groq in auto mode; must be supplied through the process environment. |
| `GROQ_MODEL` | `repo-guide` | Groq model ID; default `qwen/qwen3.8-27b`. |
| `REPO_GUIDE_MODEL` | `repo-guide` | Ollama model ID; default `qwen3:8b`. |
| `OLLAMA_BASE_URL` / `--ollama-url` | `repo-guide` | Ollama origin; loopback HTTP by default. Remote use requires explicit opt-in and HTTPS. |
| `GEMINI_API_KEY` | `repo-guide` | Presence selects Gemini in auto mode when Groq is not selected; process environment only. |
| `GEMINI_MODEL` | `repo-guide` | Gemini model ID; default `gemini-3.8-flash`. |
| `--provider auto\|gemini\|groq\|ollama` | `repo-guide` | Choose provider; auto prefers Groq, then Gemini, then Ollama. |
| `--model MODEL` | `repo-guide` | Override selected provider model. |
| `--max-steps N` | `repo-guide` | Maximum model decisions; default two, maximum 32. More steps may consume more requests. |
| `--verbose` | Both commands | Non-sensitive stderr diagnostics/tool names; it does not authorize secrets to be logged. |
| `--no-verify` | `repo-guide` | Skip final citation/provenance checks and reflection; prints unchecked model answer with a warning. Verification remains on by default. |

## Limits, failure modes, and edge cases

### Root and filesystem

- Missing/inaccessible root, non-directory, filesystem root, home root, bare repo, absent Git, and non-Git root without reduced-mode opt-in produce startup errors.
- Paths must be relative. Absolute Unix/Windows paths, drive-relative paths, UNC paths, `..`, NUL, and symlink components are rejected.
- A path can be denied because it is missing, inaccessible, outside the root, sensitive, binary, non-UTF-8, too large, too long, too minified, or not the expected file/directory kind.
- A file read with an invalid line range, range above 200 lines, or start beyond EOF fails safely. Empty files return an empty range.
- Secret scanning recognizes selected patterns only; a secret that does not match policy may still be exposed. Review repositories before using hosted inference.
- Tree listings are bounded; truncation means absence from the listing does not prove a path does not exist.

### Git and search

- `search_code` is fixed-string, not regex search, and is restricted to Git-tracked content. Newly created/untracked files may be absent.
- Git history can be empty, shallow, or missing; local history is not fetched automatically.
- Invalid dates, paths, query strings, result limits, timeouts, output caps, and Git failures produce safe errors.
- The selected checkout determines which working files and local history are visible. Repo Guide does not compare all branches or remote refs.
- GitHub remotes are parsed from local Git config only; unsupported hosts, credentials embedded in URL, malformed owner/repository, or absent remote disable issue lookup.

### GitHub issues

- Issue lookup requires network access to the fixed public GitHub API; it is unauthenticated and may be rate-limited.
- Private repositories are not made accessible by a configured URL; a 404/403 or API failure is possible.
- Pull requests are omitted even though GitHub returns them in the issues endpoint.
- Issue titles/labels are untrusted and bounded; issue bodies are not fetched.
- GitHub transient failures may get bounded retry/backoff; quota exhaustion is not retried indefinitely.

### Model/provider

- Groq requires a valid environment key and an active chat-capable model ID. A classification/safeguard model is not an answer model.
- HTTP 400 can indicate unsupported request/model parameters; 413 indicates request size; 429 indicates rate/usage limit. Repo Guide does not retry Groq 429 automatically.
- A 429 caused by per-minute token/request limits may clear after waiting; an exhausted plan/account quota requires checking provider billing/limits and may not clear simply by rotating keys.
- A provider may return prose instead of strict JSON. Groq's request budget intentionally does not add repair calls, so such a response can fail rather than multiplying requests.
- At the step limit, the investigation may be incomplete. Lower step budgets reduce possible calls but can reduce answer completeness.
- Network/model output is untrusted. A valid citation is necessary for many repository claims but does not prove their semantics.
- General conceptual questions may not use repository tools and thus may not answer a question about this particular checkout.

### IDE

- An IDE's PATH/environment may differ from the terminal. Use an absolute command path if executable discovery fails.
- A configured MCP process can start successfully while the IDE fails to display resources/prompts; clients have different feature support.
- Reopening another workspace should launch a process with a separately configured root. Verify startup logs before asking about sensitive repositories.
- IDE models may send results to their configured cloud provider. Repo Guide's CLI Groq notice does not control or describe the IDE's own model privacy.

### SQLite prototype

- The database is under the current user's home directory; write permissions, concurrent access, stale rows, corruption, and disk growth are operational concerns.
- Current helper behavior does not avoid inference work because lookup follows the turn. Do not interpret its hit ratio as reduced model spending.
- Missing goal string, repeated exceptions, and the maximum loop count may produce no useful answer; this prototype is not a supported user workflow.

## Tests and maintenance

Focused and full validation commands are listed in [TEST_STRATEGY.md](./TEST_STRATEGY.md). For the normal development gate:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pyright src
uv run pytest -q
```

Tests should be deterministic and use temporary fixture repositories and mocked HTTP/model clients. Live Groq, Ollama, GUI IDE, and public GitHub checks are separate from the default suite and must be reported only if actually run.

When implementation and docs differ, trust the code for current behavior and the project specification for intended behavior, then resolve the discrepancy explicitly. Do not silently claim experimental memory, cache, IDE GUI support, remote URL ingestion, or security certification that has not been implemented and verified.
