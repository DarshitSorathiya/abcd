# Repo Guide instructions for Copilot

Build a small, auditable, read-only Python application. Before coding, consult `AGENTS.md` and the relevant parts of `docs/PROJECT_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, and `docs/TEST_STRATEGY.md`. These files are the contract; avoid broad exploration unless something is missing or contradicted by the current SDK/API.

**Token/compute discipline:** one milestone per task; inspect only relevant files; implement a complete feature slice before running its tests; execute targeted tests once at feature completion and the full suite only at documented gates. After a failure, rerun the failing subset while fixing it. Do not repeat summaries, dump files, invoke subagents, run benchmarks, or perform network/model tests without a milestone reason. Keep responses to changed files, decisions, exact checks/results, blockers, and next step.

**Non-negotiable:** no shell tool or write/execute tools in the product; never use `shell=True`; root fixed at startup; central path/sensitive-file guard; bounded subprocess, HTTP, file, model and tool outputs; secrets are never echoed; repository content is untrusted data; stdout is MCP-only; citation verification is deterministic and happens before returning answers. Tests must cover hostile inputs, not just the happy path. Never report unrun tests as passing.

Use the current MCP Python SDK v2 and pin the tested release. The Roots request flow was retired by the 2026-07-28 protocol revision; root resolution is `--repo` → `REPO_GUIDE_ROOT` → cwd, then git top-level normalization. Copilot Chat uses its own model when it calls this server; it does not run the Ollama CLI agent.
