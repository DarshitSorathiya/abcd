# Architecture Decision Notes

## D-001: Separate server, CLI agent and IDE clients

**Decision:** the MCP server owns repo-aware read-only capabilities. The CLI owns the Ollama loop and deterministic citation checks. IDE clients launch the server separately and use their own model.

**Reason:** proves server reuse through real MCP; avoids falsely claiming Ollama runs in Copilot Chat; keeps model logic out of filesystem tools.

## D-002: Root is fixed at process start

**Decision:** precedence is `--repo` → `REPO_GUIDE_ROOT` → cwd, followed by canonicalization and Git top-level normalization. The model cannot select or change root.

**Reason:** explicit, debuggable trust boundary; avoids cross-repo confusion.

**Current-protocol correction:** the original v1.1 proposal used MCP Roots as a fallback. The MCP protocol revision dated 2026-07-28 retired the Roots request flow. The current SDK documentation deprecates/removes the old flow for modern connections. Do not build on it. If a future protocol reintroduces a replacement, consider it only through a separate ADR and compatibility tests.

## D-003: Current MCP Python SDK line

**Decision:** use SDK v2 and pin the exact tested release. Do not leave a floating `mcp>=1.2` dependency or copy v1-only snippets blindly.

**Reason:** the current stable SDK line is v2 with breaking changes; a broad lower bound can install a different API than development used. Every SDK upgrade requires targeted protocol tests.

## D-004: Text retrieval before semantic search

**Decision:** first release uses bounded Git text search and line-range reads, no embedding index.

**Reason:** cheaper, simpler to audit, and aligned with retrieval-style evaluation. Semantic search is a separate measured upgrade.

## D-005: Verification code owns citation validity

**Decision:** deterministic citation/path/line/snippet/commit checks are mandatory; reflection is secondary and bounded.

**Reason:** the model cannot certify its own invented citations. Deterministic checks establish only that a citation resolves, is permitted, is present in current-turn evidence, and refers to existing lines/objects; they do not prove the cited evidence semantically supports a claim. The single bounded reflection pass is secondary and also cannot guarantee semantic correctness. Measure citation validity separately from answer correctness and grounding.

## D-006: Fixed read-only subprocess surface

**Decision:** a small allowlist of fixed Git invocations; no general shell or arbitrary executable tools. Argument arrays, timeouts and output caps are mandatory.

**Reason:** model-controlled execution would violate product scope and expand the attack surface.

## D-007: Config-only IDE integration

**Decision:** ship supported client configuration instead of an extension.

**Reason:** same server can be tested by an IDE and Inspector without a client-specific plugin. Each client's config schema must be verified against official docs at release time.

## D-008: Avoid unsupported “production-ready” claims

**Decision:** engineer toward release-quality controls, but describe as a local single-user prototype until security review, target-platform matrix and release gates are complete.

**Reason:** read-only and test coverage reduce risk but do not demonstrate absence of vulnerabilities, semantic errors or client incompatibilities.

## Official references checked 21 Oct 2026

- Copilot repository and agent instructions: https://docs.github.com/en/copilot/concepts/prompting-and-context/custom-instructions
- Custom agent profile format: https://docs.github.com/en/copilot/reference/custom-agents-configuration
- VS Code MCP config reference: https://code.visualstudio.com/docs/agents/reference/mcp-configuration
- MCP Python SDK, current v2 line and migration guidance: https://github.com/modelcontextprotocol/python-sdk
- MCP SDK deprecations/Roots retirement notes: https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/deprecated.md
- Unauthenticated GitHub REST API rate limits: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
