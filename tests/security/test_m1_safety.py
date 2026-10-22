"""Adversarial path, symlink, sensitive-file, and binary-content tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_guide.config import SafetyLimits
from repo_guide.errors import ConfigurationError, PathPolicyError
from repo_guide.root import RootMode, RootContext
from repo_guide.safety import read_repo_file, resolve_repo_path


@pytest.fixture
def root_context(tmp_path: Path) -> RootContext:
    root = tmp_path / "repo with spaces – 数据"
    root.mkdir()
    return RootContext(root.resolve(), RootMode.REDUCED)


@pytest.mark.parametrize(
    "untrusted_path",
    [
        "../outside.txt",
        "nested/../../outside.txt",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "C:relative\\secret.txt",
        "\\\\server\\share\\secret.txt",
        "//server/share/secret.txt",
        "nested\\..\\outside.txt",
        "．．/outside.txt",
        "bad\x00name",
        "",
    ],
)
def test_relative_absolute_windows_and_normalized_traversal_are_rejected(
    root_context: RootContext, untrusted_path: str
) -> None:
    with pytest.raises(PathPolicyError):
        resolve_repo_path(root_context, untrusted_path)


def test_paths_with_spaces_and_unicode_are_confined_and_readable(root_context: RootContext) -> None:
    file_path = root_context.path / "目录 with spaces" / "résumé.txt"
    file_path.parent.mkdir()
    file_path.write_text("safe text\n", encoding="utf-8")

    assert read_repo_file(root_context, "目录 with spaces/résumé.txt") == "safe text\n"


def test_symlink_escape_and_in_root_symlink_are_denied(
    root_context: RootContext, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    inside = root_context.path / "inside-target.txt"
    inside.write_text("ordinary text", encoding="utf-8")
    escape = root_context.path / "escape.txt"
    alias = root_context.path / "alias.txt"
    try:
        escape.symlink_to(outside)
        alias.symlink_to(inside)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    for path in ("escape.txt", "alias.txt"):
        with pytest.raises(PathPolicyError) as error:
            read_repo_file(root_context, path)
        assert error.value.code == "symlink_denied"


def test_broken_and_looping_symlinks_are_denied(root_context: RootContext) -> None:
    broken = root_context.path / "broken"
    loop_a = root_context.path / "loop-a"
    loop_b = root_context.path / "loop-b"
    try:
        broken.symlink_to(root_context.path / "missing")
        loop_a.symlink_to(loop_b)
        loop_b.symlink_to(loop_a)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    for path in ("broken", "loop-a"):
        with pytest.raises(PathPolicyError):
            resolve_repo_path(root_context, path)


@pytest.mark.parametrize(
    "relative_path",
    [
        ".env",
        ".env.local",
        "nested/.env.production",
        ".git/config",
        ".ssh/id_ed25519",
        ".aws/credentials",
        "nested/access_token.json",
        "server.private.pem",
        "certificate.p12",
        ".config/gcloud/application_default_credentials.json",
        "db/snapshot.sqlite3",
        "npm/.npmrc",
        "registry/.pypirc",
    ],
)
def test_sensitive_paths_are_denied_by_default(
    root_context: RootContext, relative_path: str
) -> None:
    target = root_context.path / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("synthetic non-secret fixture", encoding="utf-8")

    with pytest.raises(PathPolicyError) as error:
        read_repo_file(root_context, relative_path)
    assert error.value.code == "sensitive_path"


@pytest.mark.parametrize(
    "contents",
    [b"\x00\x01binary", b"\xff\xfeinvalid utf-8", b"text\x07with control"],
)
def test_binary_and_non_utf8_content_is_rejected_even_with_text_suffix(
    root_context: RootContext, contents: bytes
) -> None:
    (root_context.path / "apparently-safe.txt").write_bytes(contents)

    with pytest.raises(PathPolicyError) as error:
        read_repo_file(root_context, "apparently-safe.txt")
    assert error.value.code == "binary_file"


@pytest.mark.parametrize(
    "contents",
    [
        "password = 'synthetic-only-value'\n",
        "-----BEGIN RSA PRIVATE KEY-----\nsynthetic\n",
        "AWS_ACCESS_KEY_ID=AKIA1234567890ABCDEF\n",
        "github=ghp_abcdefghijklmnopqrstuvwxyz1234567890\n",
    ],
)
def test_secret_like_content_is_denied_even_in_ordinary_text_files(
    root_context: RootContext, contents: str
) -> None:
    (root_context.path / "ordinary-notes.txt").write_text(contents, encoding="utf-8")

    with pytest.raises(PathPolicyError) as error:
        read_repo_file(root_context, "ordinary-notes.txt")
    assert error.value.code == "sensitive_content"


def test_minified_and_large_files_are_rejected(root_context: RootContext) -> None:
    (root_context.path / "bundle.txt").write_text("x" * 1_001, encoding="utf-8")
    (root_context.path / "large.txt").write_text("12345", encoding="utf-8")

    with pytest.raises(PathPolicyError) as minified:
        read_repo_file(root_context, "bundle.txt")
    assert minified.value.code == "minified_file"

    with pytest.raises(PathPolicyError) as too_large:
        read_repo_file(root_context, "large.txt", SafetyLimits(max_file_bytes=4))
    assert too_large.value.code == "file_too_large"


def test_line_limit_is_enforced(root_context: RootContext) -> None:
    (root_context.path / "many-lines.txt").write_text("a\nb\nc\n", encoding="utf-8")

    with pytest.raises(PathPolicyError) as error:
        read_repo_file(root_context, "many-lines.txt", SafetyLimits(max_file_lines=2))
    assert error.value.code == "file_too_many_lines"


def test_structured_errors_do_not_include_secret_contents(root_context: RootContext) -> None:
    (root_context.path / ".env").write_text("synthetic-secret-value", encoding="utf-8")

    with pytest.raises(PathPolicyError) as error:
        read_repo_file(root_context, ".env")

    assert error.value.as_dict() == {
        "error": {
            "code": "sensitive_path",
            "message": "path is denied by repository safety policy",
        }
    }
    assert "synthetic-secret-value" not in str(error.value.as_dict())


@pytest.mark.parametrize(
    "parameters",
    [
        {"max_file_bytes": 0},
        {"max_file_lines": -1},
        {"max_subprocess_output_bytes": 0},
        {"subprocess_timeout_seconds": 0},
    ],
)
def test_safety_limits_reject_nonpositive_values(parameters: dict[str, int]) -> None:
    with pytest.raises(ConfigurationError):
        SafetyLimits(**parameters)  # type: ignore[arg-type]