# Copy-Ready Copilot Tasks

Use the **Repo Guide Engineer** custom agent. Send one prompt at a time. Do not append the complete specification; these prompts point to the canonical files already in the workspace.

## M0 — Scaffold

```text
Implement M0 only from docs/IMPLEMENTATION_PLAN.md. Read AGENTS.md and the relevant canonical docs. Inspect the workspace once, create the package/test/config skeleton, choose and pin a compatible MCP Python SDK v2 release, add version metadata and minimal CI. Do not implement product behavior. Write smoke tests, but run no checks until the slice is complete; then run M0 validation once. Keep the diff minimal. Report files, actual commands/results, blockers, and next milestone.
```

## M1 — Root and safety

```text
Implement M1 only. Build root precedence, Git top-level normalization, refusal rules, optional non-Git reduced mode, path confinement, symlink policy, sensitive-file policy and centralized limits. Read docs/SECURITY.md before coding. Add synthetic adversarial tests. Do not run tests until the full M1 slice is complete; then run only M1 tests once. Do not add tools or network calls.
```

## M2 — Local tools

```text
Implement M2 only: list_tree, read_file, search_code, git_log and repo_overview, using the existing M1 helpers. Follow docs/PROJECT_SPEC.md and docs/SECURITY.md. Bound subprocess and result size; keep Git calls fixed and shell-free. Add fixture-repository contract and abuse tests. Run targeted M2 tests once after the feature slice is complete; no live network or Ollama.
```

## M3 — MCP server

```text
Implement M3 only: wire the completed local tools into the pinned MCP SDK v2 server, add repo://readme, repo://tree and onboarding_guide, plus version/root/mode/verbose CLI behavior. Startup must not scan the repository, call GitHub or start Ollama. Stdout is protocol-only. Add scripted stdio protocol tests, then run those targeted tests once at slice completion.
```

## M4 — GitHub issues

```text
Implement M4 only: public unauthenticated GitHub issue lookup and safe remote parsing. Follow docs/SECURITY.md: fixed API host, User-Agent, <=20 s timeout, bounded body/retries, rate-limit handling, PR filtering and structured errors. Add mocked offline tests for status codes, malformed/large payloads and hostile remotes. Do not call the live API during unit tests; run targeted tests once after the slice is complete.
```

## M5 — Ollama and agent loop

```text
Implement M5 only: bounded local Ollama client and the MCP tool/observe loop with live tool discovery, strict JSON validation, repair/retry caps, duplicate-call guard, direct general answers, out-of-scope refusal and max-step behavior. Default to loopback; no repository text may be sent to a remote model unless explicitly enabled. Add scripted model tests. Run targeted tests once after implementation; no real model call unless separately requested.
```

## M6 — Citation verification

```text
Implement M6 only. Build an evidence ledger and deterministic path:line/range, snippet and commit verification. Remove or flag unsupported repository claims; never invent replacement citations. Reflection is secondary, bounded, and gets only the draft plus cited evidence. Add adversarial fabricated-citation tests. Run the targeted verification tests once after the slice is complete.
```

## M7 — Packaging / any-folder

```text
Implement M7 only: console scripts, child server launch through sys.executable, clean shutdown/cancellation, version commands and install docs. Confirm root precedence and run from root, nested folder, unrelated cwd, another repo and a path with spaces. Add tests first; execute the focused launch/package tests once after the complete slice.
```

## M8 — IDE clients

```text
Implement M8 only. Finalize the VS Code workspace config with type=stdio, command, args and ${workspaceFolder}; finalize a portable mcpServers config with an explicit absolute path placeholder and explain that it has no cwd/workspace variable. Update troubleshooting for PATH and cached tools. Perform the MCP Inspector and VS Code A/B manual checks once, record outcomes, and do not claim an untested client works.
```

## M9 — Evaluation and release

```text
Implement M9 only. Finalize the 12-question ground-truth set, adversarial cases, eval runner, launch matrix, results report, scope/limitations docs and release checklist. Run the planned validation gate once: lint, format check, type check and full unit/security suite. Diagnose failures with the smallest subset, then run the gate once after fixes. Run live Ollama, GitHub and second-model comparisons only if available and explicitly part of this milestone. Record only observed results.
```

## Generic bug fix

```text
Fix only <specific failure>. Read the failing test and the smallest relevant implementation path. Do not redesign unrelated modules. Run only the failing test or smallest subset during diagnosis; do not run the full suite unless this is an agreed release gate. Report the actual result and any residual risk.
```
