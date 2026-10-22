# Evaluation and Launch Results

> Replace this template with observed results only. Do not enter planned outcomes as passes.

## Environment

- Date:
- OS / version:
- Python:
- Repo Guide version/commit:
- MCP SDK exact version:
- Ollama version and model (if used):
- CPU/GPU/RAM (if relevant):
- Evaluation repository and commit:

## Validation gate

| Check | Command or manual step | Result (pass/fail/not run) | Evidence / failure |
|---|---|---|---|
| Lint | `ruff check .` | Not run | |
| Format | `ruff format --check .` | Not run | |
| Type check | `pyright src` | Not run | |
| Unit/security | `pytest -q` | Not run | |
| MCP Inspector | Manual | Not run | |
| VS Code repo A/B | Manual | Not run | |
| Any-folder install | Manual | Not run | |

## Agent metrics

| Metric | Observed value | Method/notes |
|---|---:|---|
| Questions scored | 0 / 12 | |
| Tool-selection accuracy | N/A | |
| Answer correctness | N/A | |
| Citation validity before verification | N/A | |
| Citation validity after verification | N/A | |
| Grounded claim rate | N/A | |
| Median latency | N/A | |
| p95 latency | N/A | |
| Mean steps per query | N/A | |
| Security cases blocked | N/A | |

## Failure triage

| Failure ID | Cause | Impact | Fix | Regression test |
|---|---|---|---|---|

## Launch matrix

Copy L1–L16 from `docs/TEST_STRATEGY.md` and record date/platform/evidence for each case. Mark unavailable platforms as not run, never passed.

## Residual risk and release decision

- Known limitations:
- Unresolved security findings:
- Unsupported clients/platforms:
- Release decision and rationale:
- Independent security review completed? (yes/no; reference):
