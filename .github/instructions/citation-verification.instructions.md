---
name: Citation Verification
description: "Use when implementing or changing repository citation extraction, evidence provenance, deterministic verification, answer sanitization, commit checks, or bounded reflection."
applyTo: ["src/repo_guide/verify.py", "tests/integration/test_m6_verify.py"]
---

# Citation Verification Guidance

- Treat model answers, MCP results, paths, quotations, issue text, and reflection output as untrusted data. Never use model text as proof that a tool succeeded.
- Keep verification independent of MCP transport and Ollama. Reuse the existing root and safety helpers; do not open a path except through the fixed-root policy.
- Derive provenance only from successful, non-truncated observations from the current turn. Preserve error and truncation status; a partial or failed result cannot establish provenance.
- Recognize only documented repository-relative `path:line` / `path:start-end` and explicitly identified commit citations. Do not infer citations from URLs, timestamps, bare hashes, or unrelated examples.
- Check file policy, root containment, line bounds, evidence provenance, quoted snippets near the cited lines, and commit existence with fixed, bounded Git calls. Distinguish confirmed invalid citations from operational verification failures.
- Sanitize the smallest affected claim or sentence. Never invent replacement citations or return the original answer after a verifier failure. Re-extract and deterministically verify all citations after every sanitization.
- Use at most one reflection call. Supply only the original question, bounded candidate answer, compact evidence, and verification findings. Accept only strict JSON naming exact, unique claim substrings; never accept a replacement answer or let reflection override deterministic failures.
- Define validity rate as valid extracted citations divided by all extracted citations. Return `null`/not applicable for zero citations; do not report an empty denominator as 100%.
- Citation existence and reflection are not proof of semantic correctness. Preserve that limitation in code comments and user-facing claims.
- Keep failure messages and diagnostics free of file contents, quotes, secrets, and exception details.

Canonical behavior and security requirements live in [docs/PROJECT_SPEC.md](../../docs/PROJECT_SPEC.md), [docs/SECURITY.md](../../docs/SECURITY.md), and [docs/TEST_STRATEGY.md](../../docs/TEST_STRATEGY.md).