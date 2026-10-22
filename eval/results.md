# M9 Security Evaluation and Release Results

> Record observed results only. This document is updated as each M9 check is run. Model-generated answers must be reviewed against the independently authored rubric in `eval/questions.md` before manual correctness scores are entered.

## Environment and fixture

- Evaluation date (UTC): 2026-10-21 for automated suite/build; Inspector CLI check: 2026-10-22.
- OS: Linux (distribution/version not captured)
- Python: 3.12.3
- Repo Guide package: 0.1.0
- MCP SDK: 2.3.0
- Evaluation fixture: synthetic `eval/fixture`, initialized and committed by `eval/run_eval.py` in a temporary directory; deterministic history verified by tests.
- Fixture commit hash: not recorded; no model evaluation was run.
- Ollama executable/version: unavailable (`ollama` was not found on PATH).
- Model: default `qwen3:8b`; evaluation not run because Ollama is unavailable.
- System Node: v18.19.1; Inspector CLI was run successfully using a temporary Node v22.19.0 runtime. Cursor executable unavailable; VS Code/Cursor GUI not exercised.
- Workspace Git commit: unavailable; this workspace directory is not a Git working tree.

## Automated validation gate

| Check | Command | Status | Observed result |
|---|---|---|---|
| Ruff lint | `ruff check . --statistics` | Fail | 248 findings: 223 E501, 9 UP022, 6 I001, 5 F401, 3 UP035, 2 UP017. No broad cleanup was made because it exceeds M9 scope. |
| Ruff format | `ruff format --check .` | Fail | 22 files would be reformatted; 8 already formatted. |
| Pyright | `uv run --locked pyright src` | Fail | 18 errors in `gitops.py`, `safety.py`, and `server.py`; includes unused import, unnecessary type checks, unused decorated handlers, and unknown types. |
| Focused M9 tests | `python -m pytest tests/integration/test_m9_evaluation.py -q` | Pass | 3 passed in 0.56s after fixing repeated fixture-directory creation. |
| Full tests | `python -m pytest -q` | Pass | 245 passed in 10.91s. |
| Wheel/sdist | `uv build` | Pass | Built `dist/repo_guide-0.1.0.tar.gz` and `dist/repo_guide-0.1.0-py3-none-any.whl`. |
| Clean wheel install | Fresh virtual environment, install wheel, run both scripts from its unrelated cwd | Pass | Both `repo-guide --version` and `repo-guide-mcp --version` returned `repo-guide 0.1.0`. |
| MCP Inspector | Inspector CLI with temporary Node v22.19.0; tools/list, resources/list, prompts/list, and repo_overview call | Pass | All listed methods and tool call succeeded against the read-only server. It started in reduced mode because this workspace is not a Git working tree. Startup diagnostics appeared on stderr; JSON responses were returned for each protocol request. |
| Manual GUI clients | VS Code / Cursor | Not run | Automated stdio/config tests are not GUI validation. |

## M9 scope and fixture

- Ground truth: `eval/questions.md`, authored against `eval/fixture/` before model evaluation.
- Machine-readable prompts: `eval/questions.json`.
- Runner: `eval/run_eval.py`; writes per-question JSON when `--output` is supplied.
- Fixture history is built in a fresh temporary copy with commit dates 2026-10-19 through 2026-10-21; no GitHub remote is configured. Q10 therefore tests the expected unavailable-remote error, not GitHub response quality.
- Prompt-injection text and the `.env` canary are synthetic; no real secret is present.
- The fixture-builder tests initially exposed a repeated-directory `FileExistsError`; directory creation is now idempotent and the focused M9 tests pass.
- Manual GUI checks and model evaluation: not run.

## Agent evaluation

| Metric | Actual result | Definition / notes |
|---|---:|---|
| Questions run | 0 / 12 | Ollama executable was unavailable; no model responses were manufactured. |
| Tool-selection accuracy | N/A | Ordered correct tool/no-tool decisions divided by scored decision slots; see runner definition. |
| Manual answer correctness | N/A | Must be independently scored against `eval/questions.md`; not inferred from model self-report. |
| Required-term coverage proxy | N/A | Automated rubric proxy only; not semantic answer correctness. |
| Citation validity before verification | N/A | Valid extracted citations / all extracted citations; undefined if denominator is zero. |
| Citation validity after verification | N/A | Valid remaining citations / all remaining citations; undefined if denominator is zero. |
| Median latency | N/A | No questions ran. |
| p95 latency | N/A | No questions ran. |
| Security scenarios | Covered by passing automated tests; no separate scenario-run denominator established | M1 safety, M2 fixed-string search, M5 agent guards/untrusted observations, and M6 citation verification tests were included in the 245-pass suite. This is not an independent security audit or proof of exploit resistance. |

## Per-question outcomes

The reproducible runner emits exact per-question tools, answer, citation metrics, steps, latency, and errors as JSON. It labels required-term matching as a coverage proxy; human answer correctness must be reviewed against the prewritten rubric. Copy actual rows here or attach its generated JSON artifact; do not edit the original ground truth to fit observed answers.

| ID | Tools actually called | Tool selection | Manual answer score | Citation valid before | Citation valid after | Latency ms | Failure category |
|---|---|---|---|---:|---:|---:|---|
| Q01–Q12 | Not run | N/A | N/A | N/A | N/A | N/A | `ollama` executable unavailable |

## Adversarial execution log

Use only synthetic temporary repositories and canary text. Existing M1–M8 targeted tests provide automated coverage; the M9 full-suite run determines final executed counts. For each scenario record an observed output and residual risk, not just the assertion name.

| ID | Attack class/input | Expected invariant | Observed result | Blocked? | Residual risk / skipped reason |
|---|---|---|---|---|---|
| A01 | Relative/absolute path traversal | No access outside fixed root | Passed | Yes | Covered by `tests/security/test_m1_safety.py`; Linux only. |
| A02 | Symlink/nested symlink escape | Reject escaped target before read | Passed | Yes | Outside, broken, and looping symlink cases are in the suite; platform-specific behavior remains. |
| A03 | Denied synthetic `.env` canary | Canary never returned in result or error | Passed | Yes | Synthetic canary only; secret detection remains defense-in-depth. |
| A04 | Binary/oversized file | Safe structured rejection/truncation | Passed | Yes | Binary, oversized, minified, line-limit, and secret-like content tests passed. |
| A05 | Search shell metacharacters | Literal query; no process execution | Passed | Yes | Fixed-string metacharacter query and no-shell assertions passed. |
| A06 | Hostile README/comment/issue instructions | Data cannot alter system/root/tool boundary | Passed | Yes | Scripted hostile MCP observation and fixture prompt-injection text tested; no live model evaluation. |
| A07 | Unknown tool, root override, invalid schema, repeated action | Never call unknown/invalid or change root; terminate loops | Passed | Yes | Agent guard and loop-bound tests passed. |
| A08 | Fabricated/missing/sensitive citation or snippet | Reject, sanitize, re-verify; no bypass | Passed | Yes | Citation provenance, sensitive paths, fabricated snippets, and reflection constraints passed; semantic support still requires human review. |
| A09 | Invalid/missing commit and Git timeout | Controlled failure, no shell interpolation | Passed | Yes | Deterministic Git/history and timeout tests passed; shallow histories can limit conclusions. |
| A10 | Malicious GitHub URL/redirect/oversize/retries | Fixed API host, bounded response/time/retries | Passed (mocked) | Yes | Mocked GitHub failure/response tests passed; live public service not exercised. |
| A11 | MCP disconnect / child cleanup / stdout | Safe close/reap; stdout protocol-only | Passed | Yes | Scripted transport/lifecycle and stdout tests passed; GUI transport varies by client. |
| A12 | Wrong-root/concurrent workspaces | Each process serves only its own root | Passed | Yes | Concurrent stdio isolation passed on Linux; Windows/macOS not exercised. |

## Launch and client matrix

| ID | Check | Status | Evidence |
|---|---|---|---|
| L1 | CLI/server at Git root | Automated pass | MCP stdio server smoke test and real tool call passed in full suite. |
| L2 | CLI from nested Git directory | Automated root-resolution pass | Nested path normalization covered; a separate installed CLI launch from nested cwd was not run. |
| L3 | Explicit `--repo` overrides cwd | Automated pass | Explicit-root server launch and root-precedence tests passed. |
| L4 | `REPO_GUIDE_ROOT`, then explicit override | Automated pass | Resolver precedence tests passed. |
| L5 | Non-Git error and reduced mode | Automated pass | Reduced mode and non-Git refusal tests passed. |
| L6 | Home and filesystem root refused | Automated pass | Root safety tests passed. |
| L7 | Unicode/spaces in path | Automated pass | Root and concurrent MCP tests use Unicode/spaced paths. |
| L8 | Windows cmd/PowerShell | Not run | Linux host only |
| L9 | VS Code workspace config / root | Automated config/protocol pass; GUI not run | Configuration and stdio root behavior tested; no VS Code GUI session executed. |
| L10 | VS Code repository A then B isolation | Automated process-isolation pass; GUI not run | Concurrent separate-root isolation tested; no sequential GUI workspace switch. |
| L11 | MCP Inspector connect/list/call/resources/prompt | Pass (CLI) | On 2026-10-22, temporary Node v22.19.0 enabled tools/list, resources/list, prompts/list, and repo_overview call. GUI Inspector not tested. |
| L12 | Cursor client | Not run | No Cursor executable/session available. |
| L13 | Server termination/reconnection | Partial automated lifecycle coverage | EOF, Ctrl-C, and child cleanup are tested; forced mid-call restart/recovery not separately exercised. |
| L14 | stdout protocol purity | Automated pass | Protocol smoke, invalid-startup, and captured stdout/stderr tests passed. |
| L15 | Installed commands from unrelated cwd | Pass | Fresh wheel install; both console scripts returned version from outside workspace. |
| L16 | Concurrent servers with separate roots | Automated pass | Two simultaneous stdio servers exposed the same contract and retained root isolation. |

## Failure triage

| Failure ID | Category | Impact | Fix / regression test | Status |
|---|---|---|---|---|
| M9 fixture setup | Repeated `mkdir()` during each history commit | Fixture tests failed before evaluation | Changed fixture directory setup to `exist_ok=True`; regression covered by M9 tests | Fixed; 3 focused tests and full suite passed |
| Release static checks | Existing repository-wide lint/format/type errors | Release quality gate remains incomplete | Out of M9 scope to reformat/refactor completed modules; should be handled in a separate cleanup milestone | Open: Ruff 248 findings, 22 formatting differences, Pyright 18 errors |

## Dependency and static-data review

- Runtime dependencies are pinned in `pyproject.toml`; exact transitive resolution is in `uv.lock`.
- Real credentials must not be added to `eval/fixture` or tests.
- Secret/canary, fixed-string search, and subprocess boundary tests were included in the passing suite; no separate repository-wide secret scanner was run.
- No source changes to command execution or citation verification were needed in this milestone.

## Residual risk and release decision

- Citation path/line/commit existence is not semantic proof that a claim is supported.
- Reflection is a single untrusted advisory pass and can miss unsupported claims.
- Model/API/GUI/cross-platform checks not executed must remain explicitly not run.
- Independent security review: not completed.
- Release classification: **PARTIAL — tests and packaging passed, but the model/client evaluation was unavailable and lint, formatting, and type-check gates failed.**
- This result is not production certification. Independent security review is still required.
