# Security Contract and Threat Model

Security requirements are release blockers. The server may inspect untrusted repositories; its job is to reveal a bounded amount of permitted text, never to execute repository content.

## Trust boundaries

- **Trusted code/config:** packaged Repo Guide code and explicit launch arguments.
- **Untrusted data:** file contents, filenames, symlink targets, Git metadata, branches, commit messages, remote URLs, GitHub issue titles/labels, LLM outputs, model responses and client-supplied tool arguments.
- **External service:** public GitHub API. It may be unavailable, rate limited, malformed, slow, or return hostile text.
- **Local model:** output is untrusted and must be schema-validated; a local model is not a security boundary.

## Mandatory controls

### Filesystem confinement

- Resolve the root once to an absolute real path and keep it immutable.
- Reject filesystem root and user home as roots. Refuse a non-Git directory unless explicit reduced mode is requested.
- Every supplied path must be relative to the root. Reject absolute paths, drive-relative paths, UNC paths, traversal (`..`), NULs and invalid platform forms; canonicalize only after validating the path syntax, then prove containment.
- Resolve symlinks before any explicit read and reject targets outside the root. Tree traversal must not follow symlinks. Test symlink loops, broken links, Unicode paths, spaces, Windows drive/UNC forms and path-case behavior.
- Centralize file access. Never let an MCP handler bypass path policy. Fail closed on ambiguous path or filesystem errors.
- Enforce per-file byte and line limits before returning content. Detect binary/non-UTF-8 content safely; don't leak raw bytes.

### Sensitive and generated content

Deny `.git/**`, `.env*`, private/public key files where likely credentials are stored, SSH/cloud credential directories, token/credential files, certificate/private-key containers, `.npmrc`, `.pypirc`, credential-bearing config, database dumps, binaries, minified bundles and high-risk generated artifacts. Maintain a documented centralized policy with synthetic tests. Do not log or return matches from denied paths. Secret scanning is defense-in-depth, not a promise to detect every secret; when uncertain, refuse the file.

### Subprocesses and Git

- Run only a small allowlist of fixed Git subcommands (`rev-parse`, `ls-files` where required, `grep`, `log`, `show` if required, etc.). Do not expose an arbitrary Git command or shell tool.
- Use `subprocess` argument arrays, `shell=False`, a fixed executable, explicit timeout, bounded stdout/stderr, and a controlled environment (`GIT_TERMINAL_PROMPT=0`, pager disabled). Never concatenate a user query into command syntax.
- Use option terminators such as `--` where supported and pass search text as a fixed-string expression argument (for example via `-e`). Validate paths separately.
- Limit execution time, process output, returned matches and commit count. Kill/reap the process on timeout/cancellation.
- Prove read-only behavior with tests: no index/worktree changes, no new files, no hooks or repository scripts invoked.

### GitHub API

- Public unauthenticated endpoints only; no credential discovery or login flow.
- Accept only recognized GitHub HTTPS/SSH remote forms and normalize to an owner/repository pair without fetching or executing anything. Reject lookalike hosts, unusual URL schemes, embedded credentials and malformed repository names.
- Set User-Agent, connect/read timeout ≤20 seconds, response-size caps and retry budget. Retry only transient, idempotent GET failures; honor `Retry-After` and rate headers; do not retry quota exhaustion endlessly.
- Parse and validate response shape. Filter pull requests out of issues. Do not return full issue bodies by default. Treat title, labels and URLs as untrusted text.
- Avoid SSRF: the API host is constant, not derived from a user-supplied URL. Network access is deferred until the issue tool is called.

### Prompt injection and LLM outputs

- Treat retrieved content as quoted data, never instructions. Tool results must be explicitly labeled as data in the model prompt.
- Never give the model shell, filesystem mutation, arbitrary URL fetch, or arbitrary subprocess capability.
- Parse the exact expected JSON schema; reject additional fields and unknown tools. Limit model context, action length, tool steps and output tokens.
- Add a hostile fixture containing instructions to exfiltrate secrets, override the system prompt, run commands, change roots or ignore citations. The correct result is safe handling as text.
- Never pass API credentials or unrelated environment variables to Ollama. Default to loopback. Remote model endpoints require explicit opt-in and warning.

### Citation integrity

- Citation verification is deterministic and runs before output.
- Resolve each cited path under the same root and same denylist; verify the exact line/range; verify commit hashes against local history; normalize snippets and compare against actual content.
- Maintain an evidence ledger. Citations existing is not sufficient evidence that a claim is supported; unsupported claims must be removed or marked unknown.
- Test `../`, absolute/drive/UNC paths, symlink escape, invalid line/range, deleted file, misleading filenames, malformed commit hashes and fake snippets.

### Protocol and resource use

- stdout contains protocol messages only; test that startup, errors and verbose logs go to stderr.
- Bound tool arguments and result sizes, tree depth/count, line ranges, subprocess output, HTTP response size, retries, LLM request/response tokens and total loop steps.
- Catch failures at tool boundaries and return structured safe errors; internal logs may include exception class and operation, but not raw secrets or entire content.
- Server startup must not call GitHub or Ollama and must not walk the full repository.

## Adversarial acceptance suite

At minimum test:

1. `../../etc/passwd`, absolute paths, Windows drive paths, UNC paths, NULs, mixed separators and traversal after Unicode normalization.
2. Symlink to outside root, symlink loop, broken link, root symlink and path replaced during operation where the OS/test permits.
3. Denied secrets by exact name and pattern, nested secrets, a tracked `.env`, UTF-8 BOM, non-UTF-8, binary, minified and very large files.
4. Search text containing `;`, `&&`, `$()`, backticks, quotes, leading dashes, regex metacharacters and newline characters. Verify no shell side effects.
5. Huge match count, huge tree, deep directory, huge line, subprocess hang, timeout, cancellation and killed process cleanup.
6. README/issue/commit text attempting prompt injection or requesting secret disclosure.
7. Malformed JSON, extra keys, invalid schema, unknown tool, huge output, repeated identical tool call and loop exhaustion.
8. GitHub DNS/network timeout, 429, 403 quota, 5xx, invalid JSON, giant response, hostile URL/redirect, non-GitHub remote and pull-request filtering.
9. Citations to nonexistent files/lines, denied files, path escapes, wrong snippet, fabricated commit and citation to a file changed after observation.
10. Two simultaneous clients with different roots; ensure no cross-root reads.
11. Stdout protocol hygiene and repository/worktree remains unchanged after every tool call.

A passing adversarial suite reduces risk; it does not prove the absence of exploitable defects. Keep a residual-risk section in each release report.

## M9 synthetic evaluation fixture

The M9 fixture under `eval/fixture/` is synthetic and contains a clearly named fake `.env` canary only. `eval/run_eval.py` copies it to a temporary directory, creates a known three-commit history with fixed author/committer metadata, and serves only that temporary root. The fixture README and source include hostile-looking instructions strictly as test data. Never replace these with credentials or a production/private repository. The verifier checks citation existence and current-turn provenance, but neither it nor the secondary reflection pass proves semantic support; report semantic grounding independently.
