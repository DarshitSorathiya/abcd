"""Central path confinement and file-content policy for repository access."""

from __future__ import annotations

import os
import re
import stat
import unicodedata
from typing import BinaryIO
from pathlib import Path, PureWindowsPath

from repo_guide.config import SafetyLimits
from repo_guide.errors import PathPolicyError
from repo_guide.root import RootContext

_SENSITIVE_COMPONENTS = {".aws", ".azure", ".gnupg", ".kube", ".ssh", ".git"}
_SENSITIVE_NAMES = {
    ".netrc",
    ".npmrc",
    ".pypirc",
    "credentials",
    "credentials.json",
    "secrets.json",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa.pub",
    "id_dsa.pub",
    "id_ecdsa.pub",
    "id_ed25519.pub",
}
_SENSITIVE_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".kdbx",
    ".keystore",
    ".jks",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".dump",
    ".bak",
}
_SENSITIVE_TOKEN_PATTERN = re.compile(r"(?:^|[._-])(secret|credential|token)(?:[._-]|$)", re.I)
_BINARY_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_SECRET_CONTENT_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|password|client[_-]?secret)"
        r"\s*[:=]\s*['\"]?[^\s'\"]{8,}",
        re.IGNORECASE,
    ),
)


def resolve_repo_path(context: RootContext, relative_path: str) -> Path:
    """Validate a relative path, deny symlink components, and prove confinement."""
    parts = _validate_relative_path(relative_path)
    current = context.path
    try:
        for part in parts:
            current = current / part
            metadata = current.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise PathPolicyError("symlink_denied", "symbolic-link paths are not accessible")
        resolved = current.resolve(strict=True)
        resolved.relative_to(context.path)
    except PathPolicyError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise PathPolicyError("path_unavailable", "repository path is missing or inaccessible") from exc

    if _is_sensitive_path(context.path, resolved):
        raise PathPolicyError("sensitive_path", "path is denied by repository safety policy")
    return resolved


def validate_repo_relative_path(relative_path: str) -> str:
    """Validate a repository-relative path or glob without touching the filesystem."""
    parts = _validate_relative_path(relative_path)
    return "/".join(parts)


def is_sensitive_repo_path(root: Path, relative_path: str) -> bool:
    """Apply the centralized sensitive-name policy to a validated relative path."""
    normalized = validate_repo_relative_path(relative_path)
    candidate = root.joinpath(*normalized.split("/")) if normalized else root
    return _is_sensitive_path(root, candidate)


def read_repo_file(
    context: RootContext,
    relative_path: str,
    limits: SafetyLimits | None = None,
    *,
    max_lines: int | None = None,
) -> str:
    """Read a bounded UTF-8 text file after centralized policy validation."""
    policy = limits or context.limits
    path = resolve_repo_path(context, relative_path)
    if not path.is_file():
        raise PathPolicyError("not_a_file", "requested path is not a regular file")
    try:
        with _open_readonly_beneath(context.path, path) as handle:
            metadata = os.fstat(handle.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                raise PathPolicyError("not_a_file", "requested path is not a regular file")
            if metadata.st_size > policy.max_file_bytes:
                raise PathPolicyError("file_too_large", "file exceeds the configured size limit")
            data = handle.read(policy.max_file_bytes + 1)
    except PathPolicyError:
        raise
    except (OSError, RuntimeError) as exc:
        raise PathPolicyError("path_unavailable", "file could not be safely opened") from exc

    if len(data) > policy.max_file_bytes:
        raise PathPolicyError("file_too_large", "file exceeds the configured size limit")
    if _looks_binary(data):
        raise PathPolicyError("binary_file", "binary or non-UTF-8 files are not accessible")
    text = data.decode("utf-8-sig")
    if _contains_secret_pattern(text):
        raise PathPolicyError("sensitive_content", "file content is denied by repository safety policy")
    if _looks_minified(text):
        raise PathPolicyError("minified_file", "minified files are not accessible")
    line_limit = policy.max_file_lines if max_lines is None else max_lines
    if line_limit <= 0 or line_limit > policy.max_file_bytes:
        raise PathPolicyError("invalid_line_limit", "line limit must be within the configured byte cap")
    if len(text.splitlines()) > line_limit:
        raise PathPolicyError("file_too_many_lines", "file exceeds the configured line limit")
    return text


def _validate_relative_path(value: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise PathPolicyError("invalid_path", "path must be a non-empty relative path")
    normalized = unicodedata.normalize("NFKC", value)
    windows = PureWindowsPath(normalized)
    if (
        Path(normalized).is_absolute()
        or windows.is_absolute()
        or windows.drive
        or normalized.startswith(("//", "\\\\"))
    ):
        raise PathPolicyError("absolute_path", "absolute paths are not allowed")

    tokens = normalized.replace("\\", "/").split("/")
    if any(part == ".." for part in tokens):
        raise PathPolicyError("path_traversal", "parent-directory traversal is not allowed")
    parts = tuple(part for part in value.split("/") if part not in ("", "."))
    if any(part in ("..", "") for part in parts):
        raise PathPolicyError("path_traversal", "parent-directory traversal is not allowed")
    return parts


def _is_sensitive_path(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    normalized_parts = [unicodedata.normalize("NFKC", part).casefold() for part in relative.parts]
    for part in normalized_parts:
        if part == ".git" or part.startswith(".env"):
            return True
        if part in {component.casefold() for component in _SENSITIVE_COMPONENTS}:
            return True
        if part in {name.casefold() for name in _SENSITIVE_NAMES}:
            return True
        if Path(part).suffix.casefold() in _SENSITIVE_SUFFIXES:
            return True
        if _SENSITIVE_TOKEN_PATTERN.search(part):
            return True
    if any(
        normalized_parts[index : index + 2] == [".config", "gcloud"]
        for index in range(len(normalized_parts) - 1)
    ):
        return True
    return False


def _looks_binary(data: bytes) -> bool:
    if b"\x00" in data:
        return True
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return True
    return bool(_BINARY_CONTROL_PATTERN.search(text))


def _looks_minified(text: str) -> bool:
    lines = text.splitlines()
    return any(len(line) > 1_000 and not any(char.isspace() for char in line) for line in lines)


def _contains_secret_pattern(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SECRET_CONTENT_PATTERNS)


def _open_readonly_beneath(root: Path, path: Path) -> BinaryIO:
    """Open without following any path component on platforms with dir-fd support."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    if directory_flag and os.open in os.supports_dir_fd:
        descriptor = os.open(root, flags | directory_flag)
        try:
            parts = path.relative_to(root).parts
            if not parts:
                return os.fdopen(descriptor, "rb")
            for part in parts[:-1]:
                child = os.open(part, flags | directory_flag, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            file_descriptor = os.open(parts[-1], flags, dir_fd=descriptor)
            return os.fdopen(file_descriptor, "rb")
        finally:
            os.close(descriptor)
    return os.fdopen(os.open(path, flags), "rb")