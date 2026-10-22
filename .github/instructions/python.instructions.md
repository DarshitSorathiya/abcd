---
applyTo: "src/**/*.py,tests/**/*.py"
---

Use Python 3.10+ compatible syntax unless `pyproject.toml` deliberately raises the minimum. Add type hints to public functions and meaningful internal interfaces. Keep functions small, avoid global mutable state, and use explicit encodings for text files. Do not catch `Exception` unless adding a process boundary where all failures must be converted to a safe structured error; preserve the original exception for stderr logs without leaking sensitive content to tool output.

Use `pathlib`, but centralize trusted-root validation. Use subprocess argument arrays, `shell=False`, explicit timeout, bounded output, and controlled environment. Do not interpolate user strings into command syntax. Network calls require explicit connect/read timeouts, bounded response bodies, safe retries for idempotent requests, and structured errors. MCP stdout is protocol-only; logging is configured to stderr.

Tests must be deterministic by default. Use temporary fixture repositories and mocked HTTP/Ollama clients. Live network/model tests must be marked separately and must not run in the default unit suite. Test both valid and adversarial input, plus platform-specific path behavior where practical.
