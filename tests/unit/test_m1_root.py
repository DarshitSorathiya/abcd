"""Root resolution and capability-boundary tests for milestone M1."""

from __future__ import annotations

import subprocess
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import repo_guide.root as root_module
from repo_guide.errors import RootResolutionError
from repo_guide.root import Capability, RootMode, resolve_root


def make_repo(path: Path, *, bare: bool = False) -> Path:
    path.mkdir(parents=True)
    args = ["git", "init", "--quiet"]
    if bare:
        args.append("--bare")
    args.append(str(path))
    subprocess.run(args, check=True, shell=False, capture_output=True)
    return path


def test_root_precedence_explicit_repo_beats_environment_and_cwd(tmp_path: Path) -> None:
    explicit = make_repo(tmp_path / "explicit path")
    environment = make_repo(tmp_path / "environment")
    working = make_repo(tmp_path / "working")

    context = resolve_root(
        explicit,
        environ={"REPO_GUIDE_ROOT": str(environment)},
        cwd=working,
        home=tmp_path / "home",
    )

    assert context.path == explicit.resolve()
    assert context.mode is RootMode.GIT


def test_environment_root_beats_cwd(tmp_path: Path) -> None:
    environment = make_repo(tmp_path / "環境 root")
    working = make_repo(tmp_path / "working")

    context = resolve_root(
        environ={"REPO_GUIDE_ROOT": str(environment)},
        cwd=working,
        home=tmp_path / "home",
    )

    assert context.path == environment.resolve()


def test_process_environment_root_is_read_when_no_explicit_mapping_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = make_repo(tmp_path / "env-root")
    working = make_repo(tmp_path / "working")
    monkeypatch.setenv("REPO_GUIDE_ROOT", str(environment))

    context = resolve_root(cwd=working, home=tmp_path / "home")

    assert context.path == environment.resolve()


def test_cwd_is_used_when_no_higher_precedence_root_exists(tmp_path: Path) -> None:
    working = make_repo(tmp_path / "working")

    context = resolve_root(environ={}, cwd=working, home=tmp_path / "home")

    assert context.path == working.resolve()


def test_resolved_root_context_cannot_be_reassigned(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    context = resolve_root(repo, home=tmp_path / "home")

    with pytest.raises(FrozenInstanceError):
        context.path = tmp_path  # type: ignore[misc]


def test_nested_directory_resolves_to_repository_top_level(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "project")
    nested = repo / "space and ünicode" / "nested"
    nested.mkdir(parents=True)

    context = resolve_root(nested, home=tmp_path / "home")

    assert context.path == repo.resolve()


@pytest.mark.parametrize("root_path", ["/", "home"])
def test_filesystem_root_and_user_home_are_refused(tmp_path: Path, root_path: str) -> None:
    target = Path("/") if root_path == "/" else tmp_path / "home"
    if root_path != "/":
        target.mkdir()

    with pytest.raises(RootResolutionError, match="cannot be served|cannot be served"):
        resolve_root(target, allow_non_git=True, home=tmp_path / "home")


def test_git_repository_at_user_home_is_refused(tmp_path: Path) -> None:
    home = make_repo(tmp_path / "home")

    with pytest.raises(RootResolutionError, match="home directory"):
        resolve_root(home, home=home)


def test_missing_and_non_directory_roots_are_rejected(tmp_path: Path) -> None:
    file_path = tmp_path / "not-a-directory"
    file_path.write_text("data", encoding="utf-8")

    with pytest.raises(RootResolutionError, match="accessible path"):
        resolve_root(tmp_path / "missing", allow_non_git=True, home=tmp_path / "home")
    with pytest.raises(RootResolutionError, match="existing directory"):
        resolve_root(file_path, allow_non_git=True, home=tmp_path / "home")


def test_non_git_directory_requires_opt_in_and_reduced_mode_blocks_git_features(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "ordinary directory"
    directory.mkdir()
    with pytest.raises(RootResolutionError, match="not inside a Git"):
        resolve_root(directory, home=tmp_path / "home")

    context = resolve_root(directory, allow_non_git=True, home=tmp_path / "home")
    assert context.mode is RootMode.REDUCED
    context.require_capability(Capability.FILESYSTEM)
    for capability in (Capability.GIT_HISTORY, Capability.GITHUB_ISSUES):
        with pytest.raises(RootResolutionError, match="reduced mode"):
            context.require_capability(capability)


def test_missing_git_is_reported_or_permits_explicit_reduced_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "folder"
    directory.mkdir()
    monkeypatch.setattr(root_module.shutil, "which", lambda _: None)

    with pytest.raises(RootResolutionError) as error:
        resolve_root(directory, home=tmp_path / "home")
    assert error.value.code == "git_unavailable"

    context = resolve_root(directory, allow_non_git=True, home=tmp_path / "home")
    assert context.mode is RootMode.REDUCED


def test_bare_repository_is_not_accepted_even_in_reduced_mode(tmp_path: Path) -> None:
    bare = make_repo(tmp_path / "bare.git", bare=True)

    with pytest.raises(RootResolutionError) as error:
        resolve_root(bare, allow_non_git=True, home=tmp_path / "home")
    assert error.value.code == "bare_repository"


def test_git_invocations_use_fixed_argument_lists_and_disable_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path / "repo")
    original_run = root_module.subprocess.run
    calls: list[subprocess.CompletedProcess[bytes]] = []

    def checked_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert isinstance(args[0], list)
        assert kwargs["shell"] is False
        result = original_run(*args, **kwargs)  # type: ignore[arg-type]
        calls.append(result)
        return result

    monkeypatch.setattr(root_module.subprocess, "run", checked_run)
    context = resolve_root(repo, home=tmp_path / "home")

    assert context.path == repo.resolve()
    assert len(calls) == 2