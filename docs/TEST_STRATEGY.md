# Test Strategy and Release Gates

## Principles

- Tests are part of each feature's implementation, but execute them only after the planned feature slice is complete. Avoid repeated test runs during active edits.
- Use synthetic fixture repositories created in temporary directories. Never point destructive or mutation-oriented test utilities at a real repository.
- Unit tests are offline and deterministic. Mock GitHub and Ollama in the default suite. Keep network/model/IDE tests separate and opt-in.
- Prefer tests that assert externally visible behavior and security invariants, not private implementation details.
- Never convert failures to skips merely to make CI green. Every skip needs a reason and platform marker.

## Layers

1. **Unit:** config precedence, root resolution, path validation/confinement, sensitive-file policy, output caps, JSON parsing, evidence ledger and citation parsing.
2. **Tool contract:** each MCP tool against a fixture repo, success, empty result, malformed input, denied path, truncation and structured error.
3. **Security/adversarial:** all required cases in `docs/SECURITY.md`; ensure read-only invariants.
4. **Agent loop:** scripted model outputs for one-tool-then-final, search refinement, invalid JSON repair, invalid args correction, unknown tool, duplicate loop, general answer without tool, out-of-scope refusal and max-step stop.
5. **MCP protocol:** connect via stdio client, list tools/resources/prompts, call each tool, verify errors, verify stdout only contains protocol data, close cleanly after Ctrl-C/EOF/error.
6. **Packaging/launch:** editable install, console scripts, spawn child with `sys.executable`, run from unrelated cwd and path containing spaces, inspect `--version` and stderr root line.
7. **Cross-platform:** Linux, Windows and macOS where available; path spaces, Unicode, separator normalization, symlinks and CRLF.
8. **End-to-end:** real Ollama and live public GitHub issue lookup are explicitly marked and opt-in. Never require either for normal CI.
9. **Evaluation:** hand-labeled questions in `eval/questions.md`; record correctness independently from citation validity and tool selection.
10. **IDE/MCP compatibility:** validate checked-in VS Code, portable Copilot, and Cursor JSON examples; launch isolated stdio server processes for separate roots; exercise tool/resource/prompt discovery over the pinned SDK. Record GUI checks separately and mark clients/OSes untested when no manual launch occurred.

## Required default checks

Use commands configured in `pyproject.toml` and document the canonical form. Recommended baseline:

```bash
ruff check .
ruff format --check .
pyright src
pytest -q
```

If a selected linter/type checker is replaced, update `pyproject.toml`, CI and this document together. Keep lint/type/static checks in CI. Security tests are part of `pytest`, not a separate undocumented manual run.

## Execution policy to conserve compute

- While implementing, write tests but do not run them after every edit.
- After a complete feature slice, run the targeted test file once.
- During integration, run all tests once at the milestone gate.
- If a test fails, run only the failing test or focused subset during diagnosis; after the fix, run the complete suite once.
- Run optional end-to-end model calls, benchmarks, all-client IDE checks and two-model comparison only in their planned milestones. Do not run them during ordinary unit-test cycles.
- Cache dependencies between CI jobs where supported; do not cache results in a way that hides changed tests or stale code.

## Evaluation set

Create about 12 labeled questions before tuning the agent:

- 4 locate-code questions;
- 3 history questions;
- 2 structure/onboarding questions;
- 1 good-first-issue query (record issue numbers or no issues);
- 1 general question requiring no tools;
- 1 out-of-scope request requiring a refusal.

For each repository question record ground-truth file/line or commit before running the agent. Include at least a traversal attempt, fixed-string shell metacharacter query and injected README/issue content. Keep the test repository small and known to the evaluator.

M9 keeps the independent rubric in `eval/questions.md`, its machine-readable test prompts in `eval/questions.json`, and a synthetic fixture in `eval/fixture/`. `eval/run_eval.py` creates a fresh temporary Git repository and a known ordered history before asking any model questions. The runner emits raw per-question evidence and a required-term coverage proxy; human answer correctness must still be scored independently against the written rubric. It must never tune ground truth after seeing model answers.

At the M9 gate, run the complete `pytest -q` suite once after focused fixes, build wheel and sdist, install the wheel in a fresh environment, then smoke-test both commands from outside the workspace. Live Ollama evaluation is separate from unit tests and must record the initial outcome, model/configuration and any failure without selective retrying.

## Metrics (report, do not manipulate)

- Tool-selection accuracy: target ≥90%, report observed result.
- Answer correctness: manual 0/1 scoring per question; report denominator and failures.
- Citation validity before filtering and after filtering; target 100% after deterministic verification.
- Grounding accuracy: whether each repository-specific claim is supported by cited evidence; measure separately from path/line validity.
- Median and p95 latency; step count; malformed JSON rate; retry rate; truncation frequency.
- Security test pass/fail, with platform and date.
- Model comparison only if a second model is actually run; report model, hardware/runtime conditions, exact question set and observed values.

## Launch matrix

Record date, OS, Python, package version, command, result and evidence in `eval/results.md`.

| ID | Test | Expected |
|---|---|---|
| L1 | CLI at Git root | Works; stderr prints canonical root/mode/version |
| L2 | CLI from nested directory | Serves Git top level |
| L3 | `--repo B` while cwd is A | Serves B |
| L4 | environment root, then CLI flag + environment | Environment applies alone; flag wins when present |
| L5 | non-Git directory | Clear failure; reduced mode only if explicitly allowed |
| L6 | home directory or filesystem root | Refused |
| L7 | Unicode/spaces in path | Works |
| L8 | Windows cmd/PowerShell | Works; separators normalized |
| L9 | VS Code `.vscode/mcp.json` with `${workspaceFolder}` | Tools callable; root correct |
| L10 | Open second repository in VS Code | Second root served; no leakage from prior session |
| L11 | MCP Inspector stdio | Tools/resources/prompt appear and tools run |
| L12 | second MCP client | Same server contract works unchanged |
| L13 | terminate server mid-call and restart | Clean client error; restart recovers |
| L14 | stdout hygiene | Only MCP protocol frames on stdout |
| L15 | install then run from unrelated cwd | Both console commands resolve and start |
| L16 | two concurrent server processes | Each serves only its own root |

## IDE capability matrix

Track each client independently; SDK in-memory or stdio tests do not constitute a GUI client check.

| Client | Tools list/call | Resources | Prompts | Workspace root | Error presentation | GUI status |
|---|---|---|---|---|---|---|
| VS Code Copilot Chat | Automated SDK protocol tests; manual GUI check pending | Automated SDK protocol tests; client rendering may differ | Automated SDK protocol tests; client UX may differ | Config uses `${workspaceFolder}`; process isolation automated | Review MCP server output / chat result | Not run |
| Cursor | Automated SDK protocol tests; manual GUI check pending | Automated SDK protocol tests; client rendering may differ | Automated SDK protocol tests; client UX may differ | Config uses documented `${workspaceFolder}`; process isolation automated | Cursor MCP Logs; chat result | Not run |
| MCP Inspector CLI | Run manually when environment permits | CLI methods available; run manually | CLI methods available; run manually | Explicit `--repo` command argument | CLI stderr/error envelope | Not run |

Submission minimum: L1–L7, L9, L11, L14 and L15 must have real recorded outcomes. Production release additionally requires the full claimed platform matrix, CI, dependency/security audit, threat review and rollback/recovery notes.
