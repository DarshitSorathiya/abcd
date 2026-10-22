# Architecture and Module Boundaries

## Runtime diagram

```text
repo-guide CLI (Ollama agent)             VS Code Copilot Chat / MCP Inspector
  prompt from discovered tools             their own client model
  bounded JSON tool loop                   |
  evidence ledger + citation verifier      |
             | MCP stdio                   | MCP stdio
             +---------------+-------------+
                             v
                     repo-guide-mcp
                 one immutable root/process
                  tools / resources / prompt
                     /               \
             local checkout       public GitHub REST
              fixed git calls       unauthenticated
```

The two clients launch separate processes. No shared mutable process state or cross-repository routing is allowed.

## Recommended source tree

```text
pyproject.toml
src/repo_guide/
  __init__.py       # package version
  config.py         # typed limits and environment/config precedence
  root.py           # launch-time root resolution and refusal rules
  safety.py         # path confinement, denylist, file type and size policy
  gitops.py         # fixed read-only git subprocess helpers
  github_api.py     # public issue endpoint, retries/rate handling
  server.py         # MCP registration, tools, resources, prompt, CLI entry
  ollama_client.py  # bounded local Ollama transport and JSON actions
  agent.py          # ReAct/tool-observation loop and CLI entry
  verify.py         # path:line, snippet, commit verification and evidence ledger
  errors.py         # safe domain errors / structured tool results
 tests/
  fixtures/         # temporary, synthetic repositories and hostile files
  unit/
  integration/
  security/
 eval/
  questions.md
  run_eval.py
  results.md
 docs/
```

Do not create every module as an empty placeholder at the beginning. Add each module when its milestone is implemented. Keep MCP registration/wiring in `server.py`; put filesystem policy in one place; keep Git subprocess details out of tool functions; keep LLM transport separate from the loop; keep verification independent of model output.

## Core data flow

1. Parse CLI options and resolve root once. Refuse unsafe roots before serving.
2. Emit one startup summary to stderr: version, canonical root, mode, SDK/package version when useful, and optional verbose level.
3. Complete MCP initialization without scanning the repository or accessing the network.
4. For each request, validate schema, apply root/path/sensitive-file policy, execute bounded read-only work, and return a predictable JSON-compatible result.
5. The CLI asks Ollama for one action. It validates the action against the live MCP tool catalogue, calls one tool, records a bounded observation, and repeats up to the configured cap.
6. For a final draft, check the evidence ledger and deterministic citations. Optionally use one small, bounded reflection call only for non-trivial repository answers. Print the final answer after verification.
7. Close client/server subprocesses and sessions reliably on success, errors, Ctrl-C and EOF.

## Configuration precedence

- Repository root: `--repo` > `REPO_GUIDE_ROOT` > cwd.
- Agent model: CLI `--model` > documented environment setting > config default.
- Limits: one typed config module with conservative defaults and validated overrides. Do not allow environment variables from an untrusted repository to change root/safety limits implicitly.
- Verbose logs: stderr only; never log full file contents, prompts, credentials, issue bodies or raw model dumps by default.

## MCP SDK compatibility

Use current MCP Python SDK v2, pin an exact tested version and use v2 docs/examples. Do not rely on deprecated server-initiated Roots, sampling, or logging flows. Keep transport on stdio for local clients. Version upgrades require an isolated compatibility test before changing the pin.

## Design rules

- No shell, no code execution, no writes to the served repository.
- No dynamic tool registration from repository contents.
- No model-supplied root; tool paths are always relative to immutable root.
- No unbounded `capture_output`; stream/cap potentially large subprocess output and terminate safely when limits are exceeded.
- Do not follow symlinks during tree traversal. For explicit file access, resolve and confine before opening; fail closed on race-prone or unsupported cases.
- Do not scan arbitrary directories recursively without depth/count/byte budgets.
- Use dependency injection for Git, HTTP and Ollama edges so core tests remain deterministic.
