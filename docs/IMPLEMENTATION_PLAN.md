# Implementation Plan and Milestones

Implement one milestone per Copilot task. Each milestone should end in a small, reviewable commit. The test code may be written alongside implementation, but test execution follows the policy in `docs/TEST_STRATEGY.md`.

## M0 — Repository contract and reproducible skeleton

**Build:** `pyproject.toml`, package metadata, source/test layout, formatting/lint/type/test configuration, `.gitignore`, CI baseline and dependency lock. Select an MCP SDK v2 release after checking its docs/API; lock the exact tested version. Add version metadata and minimal import smoke coverage.

**Done when:** clean environment can install the package, both console scripts are registered, CI commands are defined and all configured files agree. Run M0 checks once when the skeleton is complete.

## M1 — Root resolver and safety primitives

**Build:** root precedence, Git top-level normalization, home/root refusal, optional non-Git reduced mode, canonical path confinement, symlink policy, sensitive-file/binary policy, centralized limits and safe errors.

**Done when:** unit/security tests cover path abuse and all root cases. No MCP network/model work yet.

## M2 — Local Git/filesystem tools

**Build:** `list_tree`, `read_file`, `search_code`, `git_log`, `repo_overview` using bounded helpers and structured outputs. Keep shell out of the design; stream/cap large subprocess output. Add fixture repos with tracked/untracked/generated/denied content.

**Done when:** all five tool contracts and adversarial cases are covered, with read-only invariants proven. Run targeted tool tests once after the slice is complete.

## M3 — MCP server and protocol

**Build:** FastMCP/server wiring compatible with pinned SDK v2; resources, onboarding prompt, stdio-only logging, quick handshake, version/root/mode stderr line and server CLI. No startup tree scan/network call.

**Done when:** scripted MCP client lists and calls tools, reads resources, obtains prompt and confirms stdout hygiene. Inspect once in MCP Inspector.

## M4 — GitHub issues integration

**Build:** parse supported GitHub remote forms safely, unauthenticated public issue query, pull-request filtering, response validation/limits, timeout/retry/backoff/rate-limit behavior, and bounded cache only if it remains in scope.

**Done when:** offline tests mock every error/status; one opt-in live check validates assumptions if network access is available. A network failure must not break local tools.

## M5 — Ollama transport and agent loop

**Build:** local-only default endpoint, configurable model, request/token/timeout bounds, strict JSON action schema, live MCP tool discovery, one action per step, bounded observations, JSON repair/retry cap, duplicate-call guard, direct general answer and out-of-scope refusal.

**Done when:** scripted model tests cover normal loop, invalid JSON, invalid args, search refinement, repetition, direct answer, refusal and max-step behavior. Real Ollama smoke test is separate and opt-in.

## M6 — Citation verification and evidence ledger

**Build:** claim/evidence tracking, path:line/range parser, file/line/sensitive-file validation, snippet checks, commit checks, filtering/flagging of unsupported claims and one bounded reflection call only where appropriate.

**Done when:** fabricated files/lines/snippets/commits never pass verification. Report pre/post citation validity. No unsupported claim is silently presented as fact.

## M7 — Packaging and any-folder CLI

**Build:** `repo-guide` starts MCP server with `sys.executable`, resolves root once, forwards cancellation safely, shows useful startup/errors, installs as editable package and via documented pipx/uv route. Test absolute command paths in IDE instructions.

**Done when:** command works from repository root, nested folder, another repository and unrelated directory; explicit `--repo` wins; paths with spaces work.

## M8 — IDE integration

**Build:** copy-ready VS Code config and portable Copilot MCP config; docs for Inspector and one second client. VS Code config uses `type: stdio` and `${workspaceFolder}`; portable config must use an explicit absolute `--repo` path because it does not support a working-directory field.

**Done when:** VS Code tools are callable on repository A and then B, and Inspector protocol tests pass. Do not claim unsupported client behavior as tested.

## M9 — Security evaluation and release gates

**Build:** synthetic fixture with known source and Git history; independently authored 12-question ground truth; bounded local-model evaluation runner; complete adversarial suite; launch/client matrix; results and failure log; dependency/static/package gates; and release-readiness record. Optional second-model comparison occurs only after the base evaluation is stable. Never use real secrets or an untrusted production repository as the adversarial fixture.

**Done when:** full automated tests, build artifacts, clean wheel installation and available CLI/client checks have actual recorded results; all attack cases list input, invariant, observed result and residual risk; evaluation scores use the prewritten rubric; failures are triaged; and missing platform/GUI/model checks remain marked not run. A skipped check is not a pass. Production deployment claims require an independent security review; otherwise call it a production-minded local prototype.

## Cut order if time is short

Cut optional model comparison, embeddings, caching, extra-client breadth and commit-string-search refinements first. Do **not** cut root/path security, read-only guarantees, deterministic citation checks, security tests, installability, one real IDE launch, stdout hygiene or honest limitations.
