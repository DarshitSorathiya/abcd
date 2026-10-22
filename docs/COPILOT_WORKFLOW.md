# Copilot Workflow: Low-Token, High-Signal Implementation

## Operating rule

Give Copilot one milestone, not the entire project. The repo documents are already the project brief. Ask it to read only those docs and relevant source files, then make a complete feature slice. Do not ask it to repeat the design or create a lengthy plan every turn.

## First request

```text
Read AGENTS.md and the canonical docs. Implement M0 only from docs/IMPLEMENTATION_PLAN.md. Do not implement application logic yet. Inspect the workspace once, create the package/test/config skeleton, select and pin a compatible MCP SDK v2 release, and wire minimal CI. Write necessary smoke tests but do not run any validation until the M0 slice is complete. Then run the M0 checks once. Reply with changed files, exact commands/results, blockers, and next milestone; no long summary.
```

## Subsequent request template

```text
Implement M<N> only, per docs/IMPLEMENTATION_PLAN.md. Read the relevant contract sections and only inspect the files needed for this milestone. Preserve existing APIs unless the spec requires a change. Implement the complete feature plus deterministic positive, negative, and adversarial tests. Do not execute tests or linters until the feature slice is complete. Then run the target test command once; do not run optional network/model/benchmark checks. Keep the diff focused. Report files changed, exact test command/results, known risks, and the next milestone in concise form.
```

Replace `<N>` with the actual milestone number and add any specific acceptance scenario. Do not paste the entire spec again.

## Fix request after a failure

```text
Fix only this failure: <paste concise failing test/error>. Inspect the failing path and its immediate dependencies; do not redesign unrelated components. Run only the failing test or smallest relevant subset while diagnosing. When fixed, stop and report the changed files and result. Do not rerun the full suite unless this is a planned release gate.
```

## Integration/release-gate request

```text
The feature freeze for <milestone> is complete. Run the documented validation gate once: targeted tests, then the full unit/security suite, lint, format check and type check. Fix failures by rerunning only the failing subset while diagnosing; after all fixes, run the complete gate once. Do not call live APIs or Ollama unless that gate explicitly lists them. Record actual results in eval/results.md; do not invent passes.
```

## Rules that cut waste

- No speculative research/browsing when the checked-in docs resolve the question. If an SDK/API behavior is uncertain or changed, consult its official docs once and record the decision.
- No broad `find`, recursive search, reading every file or dependency exploration when a precise path is known.
- No repeated “thinking” or duplicate summaries. If blocked, ask one specific question or list the smallest assumption needed.
- No subagents, parallel code reviews, repeated plan generation, full test-suite loops, network retries outside policy, benchmarking or model comparisons until scheduled.
- Do not optimize tokens by omitting safety logic or tests. Optimize by using small prompts, bounded tool observations and focused execution.
