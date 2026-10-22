"""Bounded read-only Git and filesystem operations for a fixed repository root."""

from __future__ import annotations

import heapq
import os
import re
import shutil
import stat
import subprocess
import threading
from collections import Counter, deque
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import BinaryIO

from repo_guide.config import SafetyLimits
from repo_guide.errors import PathPolicyError, RepoGuideError, RootResolutionError
from repo_guide.root import Capability, RootContext
from repo_guide.safety import (
    is_sensitive_repo_path,
    read_repo_file,
    resolve_repo_path,
    validate_repo_relative_path,
)

_GIT_ENV = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_PAGER": "cat",
    "GIT_TERMINAL_PROMPT": "0",
    "PATH": os.defpath,
}
_EXCLUDED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "target",
    "coverage",
    "htmlcov",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".pyright",
    ".tox",
}
_LANGUAGE_BY_SUFFIX = {
    ".c": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".cs": "C#",
    ".go": "Go",
    ".h": "C/C++",
    ".html": "HTML",
    ".java": "Java",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".kt": "Kotlin",
    ".md": "Markdown",
    ".php": "PHP",
    ".py": "Python",
    ".rb": "Ruby",
    ".rs": "Rust",
    ".sh": "Shell",
    ".sql": "SQL",
    ".swift": "Swift",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".vue": "Vue",
    ".xml": "XML",
    ".yaml": "YAML",
    ".yml": "YAML",
}
_LIKELY_ENTRY_POINTS = {
    "app.py",
    "index.js",
    "index.ts",
    "main.py",
    "main.rs",
    "manage.py",
    "package.json",
    "pyproject.toml",
    "setup.py",
    "src/app.py",
    "src/main.py",
    "src/index.js",
    "src/index.ts",
    "src/main.rs",
}


@dataclass(frozen=True, slots=True)
class TreeEntry:
    """One safe repository tree entry."""

    path: str
    kind: str
    size_bytes: int | None


@dataclass(frozen=True, slots=True)
class TreeResult:
    """Bounded tree listing and truncation status."""

    entries: tuple[TreeEntry, ...]
    truncated: bool


@dataclass(frozen=True, slots=True)
class NumberedLine:
    """One source line with its one-based repository line number."""

    number: int
    text: str


@dataclass(frozen=True, slots=True)
class FileReadResult:
    """A validated, bounded source range and whole-file line count."""

    path: str
    start_line: int
    end_line: int
    total_lines: int
    lines: tuple[NumberedLine, ...]


@dataclass(frozen=True, slots=True)
class SearchMatch:
    """One literal match in a tracked text file."""

    path: str
    line: int
    text: str


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Bounded tracked-file search results."""

    matches: tuple[SearchMatch, ...]
    truncated: bool
    tracked_files_only: bool = True


@dataclass(frozen=True, slots=True)
class Commit:
    """A commit summary and its safe changed-path list."""

    commit_hash: str
    author: str
    date: str
    subject: str
    changed_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GitLogResult:
    """Bounded history results and repository-history state."""

    commits: tuple[Commit, ...]
    truncated: bool
    shallow: bool


@dataclass(frozen=True, slots=True)
class RepoOverview:
    """Bounded structural summary; entry points are candidates only."""

    languages: dict[str, int]
    readme_present: bool
    top_level_entries: tuple[TreeEntry, ...]
    likely_entry_points: tuple[str, ...]
    truncated: bool


@dataclass(frozen=True, slots=True)
class _GitResult:
    stdout: bytes
    returncode: int
    truncated: bool


def list_tree(
    context: RootContext,
    path: str = ".",
    *,
    depth: int = 2,
    max_entries: int | None = None,
) -> TreeResult:
    """List at most the configured number of entries without following links."""
    if not 1 <= depth <= 4:
        raise RepoGuideError("invalid_depth", "depth must be between 1 and 4")
    cap = context.limits.max_tree_entries if max_entries is None else max_entries
    if not 1 <= cap <= context.limits.max_tree_entries:
        raise RepoGuideError("invalid_entry_limit", "max_entries exceeds the configured tree cap")
    relative = validate_repo_relative_path(path)
    start = resolve_repo_path(context, relative or ".")
    if not start.is_dir():
        raise PathPolicyError("not_a_directory", "tree path must be a directory")

    entries: list[TreeEntry] = []
    queue: deque[tuple[Path, int]] = deque([(start, 1)])
    truncated = False
    while queue:
        directory, level = queue.popleft()
        try:
            remaining = cap - len(entries)
            with os.scandir(directory) as iterator:
                children = heapq.nsmallest(
                    remaining + 1,
                    iterator,
                    key=lambda item: (item.name.casefold(), item.name),
                )
        except OSError as exc:
            raise PathPolicyError("directory_unavailable", "repository directory could not be listed") from exc

        if len(children) > remaining:
            truncated = True
            children = children[: remaining + 1]
        for child in children:
            rel_path = child.path
            relative_entry = Path(rel_path).relative_to(context.path).as_posix()
            if child.name.casefold() in {name.casefold() for name in _EXCLUDED_DIRECTORIES}:
                continue
            if is_sensitive_repo_path(context.path, relative_entry):
                continue
            try:
                metadata = child.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISLNK(metadata.st_mode):
                if len(entries) >= cap:
                    truncated = True
                    break
                entries.append(TreeEntry(relative_entry, "symlink", None))
                continue
            try:
                safe_path = resolve_repo_path(context, relative_entry)
            except PathPolicyError as exc:
                if exc.code in {"sensitive_path", "symlink_denied", "path_unavailable"}:
                    continue
                raise

            if stat.S_ISDIR(metadata.st_mode):
                if len(entries) >= cap:
                    truncated = True
                    break
                entries.append(TreeEntry(relative_entry, "directory", None))
                if level < depth:
                    queue.append((safe_path, level + 1))
            elif stat.S_ISREG(metadata.st_mode):
                if len(entries) >= cap:
                    truncated = True
                    break
                try:
                    # Content checks are delegated to the M1 policy; no file data is returned.
                    read_repo_file(
                        context,
                        relative_entry,
                        max_lines=context.limits.max_file_bytes,
                    )
                except PathPolicyError:
                    continue
                entries.append(TreeEntry(relative_entry, "file", metadata.st_size))
        if truncated:
            break
    entries.sort(key=lambda entry: (entry.path.casefold(), entry.path))
    return TreeResult(tuple(entries), truncated)


def read_file(
    context: RootContext,
    path: str,
    *,
    start_line: int = 1,
    end_line: int | None = None,
) -> FileReadResult:
    """Return a bounded, numbered range from one safe UTF-8 text file."""
    if start_line < 1 or (end_line is not None and end_line < start_line):
        raise RepoGuideError("invalid_line_range", "line range must be positive and ordered")
    final_line = start_line + context.limits.max_file_lines - 1 if end_line is None else end_line
    if final_line - start_line + 1 > context.limits.max_file_lines:
        raise RepoGuideError("line_limit_exceeded", "requested range exceeds the configured line limit")
    normalized_path = validate_repo_relative_path(path)
    text = read_repo_file(
        context,
        normalized_path,
        max_lines=context.limits.max_file_bytes,
    )
    all_lines = text.splitlines()
    total = len(all_lines)
    if total == 0:
        return FileReadResult(normalized_path, 0, 0, 0, ())
    if start_line > total:
        raise RepoGuideError("line_out_of_range", "start_line is beyond the end of the file")
    actual_end = min(final_line, total)
    numbered = tuple(
        NumberedLine(number, all_lines[number - 1])
        for number in range(start_line, actual_end + 1)
    )
    return FileReadResult(normalized_path, start_line, actual_end, total, numbered)


def search_code(
    context: RootContext,
    query: str,
    *,
    path_glob: str | None = None,
    max_results: int | None = None,
) -> SearchResult:
    """Find a literal query in tracked text files; repository text is untrusted."""
    context.require_capability(Capability.GIT_HISTORY)
    _validate_query(query, context.limits.max_search_query_chars)
    result_cap = context.limits.max_search_results if max_results is None else max_results
    if not 1 <= result_cap <= context.limits.max_search_results:
        raise RepoGuideError("invalid_result_limit", "max_results exceeds the configured search cap")
    argv = ["grep", "--no-color", "-I", "-F", "-l", "-z", "-e", query]
    if path_glob is None:
        argv.extend(["--", "."])
    else:
        glob = validate_repo_relative_path(path_glob)
        if not glob:
            raise RepoGuideError("invalid_path_filter", "path_glob must name a repository path")
        argv.extend(["--", f":(glob){glob}"])
    result = _run_git(context, argv, accepted_codes={0, 1})
    matches: list[SearchMatch] = []
    truncated = result.truncated
    output_bytes = 0
    relative_paths = (os.fsdecode(raw_path) for raw_path in result.stdout.split(b"\0") if raw_path)
    for relative_path in relative_paths:
        normalized = Path(relative_path).as_posix()
        if _is_excluded_path(normalized):
            continue
        if is_sensitive_repo_path(context.path, normalized):
            continue
        try:
            text = read_repo_file(context, normalized, max_lines=context.limits.max_file_bytes)
        except PathPolicyError:
            continue
        for line_number, line_text in enumerate(text.splitlines(), start=1):
            if query not in line_text:
                continue
            row_bytes = len(normalized.encode("utf-8")) + len(str(line_number)) + len(
                line_text.encode("utf-8")
            )
            if len(matches) >= result_cap or output_bytes + row_bytes > context.limits.max_subprocess_output_bytes:
                truncated = True
                break
            matches.append(SearchMatch(normalized, line_number, line_text))
            output_bytes += row_bytes
        if truncated and (len(matches) >= result_cap or result.truncated):
            break
    return SearchResult(tuple(matches), truncated)


def git_log(
    context: RootContext,
    *,
    path: str | None = None,
    n: int = 10,
    since: str | None = None,
    message_contains: str | None = None,
    string_changed: str | None = None,
) -> GitLogResult:
    """Return bounded commit metadata; path/string filters are never shell code."""
    context.require_capability(Capability.GIT_HISTORY)
    if not 1 <= n <= context.limits.max_log_commits:
        raise RepoGuideError("invalid_commit_limit", "n exceeds the configured history cap")
    path_arg = None
    if path is not None:
        path_arg = validate_repo_relative_path(path)
        if not path_arg:
            raise RepoGuideError("invalid_path_filter", "path filter must name a repository path")
    if since is not None:
        try:
            if len(since) != 10 or date.fromisoformat(since).isoformat() != since:
                raise ValueError
        except ValueError as exc:
            raise RepoGuideError("invalid_date", "since must be an ISO date in YYYY-MM-DD form") from exc
    if message_contains is not None:
        _validate_query(message_contains, 200)
    if string_changed is not None:
        _validate_query(string_changed, 200)

    shallow_result = _run_git(context, ["rev-parse", "--is-shallow-repository"], accepted_codes={0})
    shallow = shallow_result.stdout.strip() == b"true"
    head_result = _run_git(
        context,
        ["rev-parse", "--verify", "HEAD"],
        accepted_codes={0, 128},
    )
    if head_result.returncode != 0:
        return GitLogResult((), False, shallow)
    args = [
        "log",
        f"--max-count={n}",
        "--format=%H%x00%an%x00%aI%x00%s%x00",
        "--no-decorate",
    ]
    if since is not None:
        args.append(f"--since={since}T00:00:00")
    if message_contains is not None:
        args.extend(["--fixed-strings", f"--grep={message_contains}"])
    if string_changed is not None:
        args.append(f"-S{string_changed}")
    if path_arg is not None:
        args.extend(["--", f":(literal){path_arg}"])
    metadata = _run_git(context, args, accepted_codes={0})
    fields = metadata.stdout.split(b"\0")
    commits: list[Commit] = []
    truncated = metadata.truncated
    aggregate_bytes = len(metadata.stdout)
    for index in range(0, len(fields) - 3, 4):
        hash_raw = fields[index].strip(b"\r\n")
        author_raw, date_raw, subject_raw = fields[index + 1 : index + 4]
        if not hash_raw:
            continue
        try:
            commit_hash = hash_raw.decode("ascii")
            author = author_raw.decode("utf-8")
            commit_date = date_raw.decode("ascii")
            subject = subject_raw.decode("utf-8").strip("\r\n")
        except UnicodeDecodeError:
            continue
        remaining = context.limits.max_subprocess_output_bytes - aggregate_bytes
        if remaining <= 0:
            truncated = True
            break
        changed_result = _run_git(
            context,
            ["diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "-z", commit_hash],
            accepted_codes={0},
            output_cap=remaining,
        )
        aggregate_bytes += len(changed_result.stdout)
        truncated = truncated or changed_result.truncated
        changed: list[str] = []
        for raw_name in changed_result.stdout.split(b"\0"):
            if not raw_name:
                continue
            relative_name = os.fsdecode(raw_name)
            if is_sensitive_repo_path(context.path, relative_name):
                continue
            changed.append(Path(relative_name).as_posix())
        commits.append(Commit(commit_hash, author, commit_date, subject, tuple(changed)))
        if changed_result.truncated:
            break
    return GitLogResult(tuple(commits), truncated, shallow)


def repo_overview(context: RootContext) -> RepoOverview:
    """Summarize a bounded tree; listed entry points are candidate files only."""
    tree = list_tree(context, depth=2, max_entries=context.limits.max_tree_entries)
    top_level = tuple(entry for entry in tree.entries if "/" not in entry.path)
    counts: Counter[str] = Counter()
    for entry in tree.entries:
        if entry.kind != "file":
            continue
        language = _LANGUAGE_BY_SUFFIX.get(Path(entry.path).suffix.casefold())
        if language is not None:
            counts[language] += 1
    readme_present = any(
        entry.kind == "file" and Path(entry.path).name.casefold().startswith("readme")
        for entry in top_level
    )
    candidates = tuple(
        entry.path
        for entry in tree.entries
        if entry.kind == "file" and entry.path.casefold() in _LIKELY_ENTRY_POINTS
    )
    return RepoOverview(
        dict(sorted(counts.items())), readme_present, top_level, candidates, tree.truncated
    )


def configured_remotes(context: RootContext) -> tuple[tuple[str, str], ...]:
    """Return bounded remote names and URLs from local Git config, without contacting them."""
    context.require_capability(Capability.GITHUB_ISSUES)
    result = _run_git(
        context,
        ["config", "--local", "--no-includes", "--null", "--get-regexp", r"^remote\..*\.url$"],
        accepted_codes={0, 1},
    )
    if result.truncated:
        raise RepoGuideError("remote_config_too_large", "Git remote configuration exceeded the output limit")
    if result.returncode != 0:
        return ()
    records = result.stdout.split(b"\0")
    remotes: list[tuple[str, str]] = []
    for record in records:
        key, separator, value = record.partition(b"\n")
        if not separator:
            continue
        try:
            decoded_key = key.decode("utf-8")
            remote_name = decoded_key.removeprefix("remote.").removesuffix(".url")
            remote_url = value.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if remote_name and remote_url:
            remotes.append((remote_name, remote_url))
    return tuple(remotes)


def commit_exists(context: RootContext, commit_hash: str) -> bool:
    """Check one already-validated object name using bounded fixed Git arguments."""
    context.require_capability(Capability.GIT_HISTORY)
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", commit_hash):
        return False
    result = _run_git(
        context,
        ["cat-file", "-e", f"{commit_hash}^{{commit}}"],
        accepted_codes={0, 1, 128},
    )
    return result.returncode == 0


def _validate_query(query: str, max_chars: int) -> None:
    if not isinstance(query, str) or not query.strip() or len(query) > max_chars:
        raise RepoGuideError("invalid_query", f"query must contain 1 to {max_chars} characters")
    if "\x00" in query or "\n" in query or "\r" in query:
        raise RepoGuideError("invalid_query", "query cannot contain NUL or newline characters")


def _is_excluded_path(relative_path: str) -> bool:
    return any(
        part.casefold() in {name.casefold() for name in _EXCLUDED_DIRECTORIES}
        for part in Path(relative_path).parts
    )


def _run_git(
    context: RootContext,
    arguments: list[str],
    *,
    accepted_codes: set[int],
    output_cap: int | None = None,
) -> _GitResult:
    """Run an allowlisted Git subcommand with bounded output and runtime."""
    context.require_capability(Capability.GIT_HISTORY)
    if not arguments or arguments[0] not in {
        "grep",
        "log",
        "rev-parse",
        "diff-tree",
        "config",
        "cat-file",
    }:
        raise RepoGuideError("git_operation_denied", "requested Git operation is not allowlisted")
    executable = shutil.which("git")
    if executable is None:
        raise RootResolutionError("git_unavailable", "Git is required for this operation")
    cap = min(output_cap or context.limits.max_subprocess_output_bytes,
              context.limits.max_subprocess_output_bytes)
    argv = [executable, "-C", os.fspath(context.path), *arguments]
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
            env=_GIT_ENV,
        )
    except OSError as exc:
        raise RootResolutionError("git_unavailable", "Git could not be started") from exc
    assert process.stdout is not None
    chunks: list[bytes] = []
    state = {"size": 0, "truncated": False}

    def collect_output(stream: BinaryIO) -> None:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                break
            remaining = cap - state["size"]
            if len(chunk) > remaining:
                if remaining > 0:
                    chunks.append(chunk[:remaining])
                    state["size"] += remaining
                state["truncated"] = True
                process.kill()
                continue
            chunks.append(chunk)
            state["size"] += len(chunk)

    reader = threading.Thread(target=collect_output, args=(process.stdout,), daemon=True)
    reader.start()
    try:
        returncode = process.wait(timeout=context.limits.subprocess_timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait()
        reader.join()
        raise RepoGuideError("git_timeout", "Git operation exceeded its time limit") from exc
    reader.join()
    output = b"".join(chunks)
    if returncode not in accepted_codes and not state["truncated"]:
        raise RepoGuideError("git_operation_failed", "Git operation could not complete safely")
    return _GitResult(output, returncode, bool(state["truncated"]))