"""Packaging, entry-point, and arbitrary-working-directory tests for M7."""

from __future__ import annotations

import os
import subprocess
import sys
from importlib.metadata import distribution
from pathlib import Path

import pytest

from repo_guide import __version__
from repo_guide.agent import build_server_parameters
from repo_guide.errors import RootResolutionError
from repo_guide.root import RootMode, resolve_root


WORKSPACE = Path(__file__).resolve().parents[2]


def git(cwd: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), *arguments],
        check=True,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def make_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "--quiet")
    nested = path / "nested folder" / "深い"
    nested.mkdir(parents=True)
    return path


def test_metadata_registers_both_console_scripts_and_one_authoritative_version() -> None:
    package = distribution("repo-guide")
    scripts = {entry.name: entry.value for entry in package.entry_points if entry.group == "console_scripts"}

    assert scripts["repo-guide-mcp"] == "repo_guide.server:main"
    assert scripts["repo-guide"] == "repo_guide.agent:main"
    assert package.version == __version__


def test_both_package_modules_support_help_and_version_from_unrelated_directory(tmp_path: Path) -> None:
    for module in ("repo_guide.agent", "repo_guide.server"):
        help_result = subprocess.run(
            [sys.executable, "-m", module, "--help"],
            cwd=tmp_path,
            check=False,
            shell=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        version_result = subprocess.run(
            [sys.executable, "-m", module, "--version"],
            cwd=tmp_path,
            check=False,
            shell=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert help_result.returncode == 0
        assert "usage:" in help_result.stdout.lower()
        assert version_result.returncode == 0
        assert __version__ in version_result.stdout
        assert help_result.stderr == ""
        assert version_result.stderr == ""


def test_root_selection_covers_nested_cwd_environment_precedence_and_explicit_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = make_repo(tmp_path / "first repository with spaces")
    second = make_repo(tmp_path / "另一个 repository")
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    home = tmp_path / "separate-home"
    home.mkdir()
    monkeypatch.setenv("REPO_GUIDE_ROOT", str(second))

    nested = resolve_root(first / "nested folder" / "深い", home=home)
    env_root = resolve_root(environ=None, cwd=unrelated, home=home)
    explicit_root = resolve_root(first, environ=os.environ, cwd=unrelated, home=home)

    assert nested.path == first.resolve()
    assert env_root.path == second.resolve()
    assert explicit_root.path == first.resolve()


def test_explicit_root_is_honored_from_unrelated_cwd_and_unicode_path(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "project with spaces and 数据")
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()

    context = resolve_root(root, cwd=unrelated, environ={}, home=tmp_path / "home")

    assert context.path == root.resolve()
    assert context.mode is RootMode.GIT


def test_non_git_reduced_mode_and_unsafe_roots_remain_enforced(tmp_path: Path) -> None:
    non_git = tmp_path / "ordinary folder"
    non_git.mkdir()
    with pytest.raises(RootResolutionError):
        resolve_root(non_git, environ={}, home=tmp_path / "home")
    reduced = resolve_root(non_git, environ={}, allow_non_git=True, home=tmp_path / "home")
    assert reduced.mode is RootMode.REDUCED
    with pytest.raises(RootResolutionError, match="home directory"):
        resolve_root(non_git, environ={}, allow_non_git=True, home=non_git)
    with pytest.raises(RootResolutionError, match="filesystem root"):
        resolve_root(Path("/"), environ={}, allow_non_git=True, home=tmp_path / "home")


def test_agent_server_parameters_use_current_interpreter_and_fixed_root(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "root path with spaces")
    context = resolve_root(repo, environ={}, home=tmp_path / "home")

    parameters = build_server_parameters(context)

    assert parameters.command == sys.executable
    assert parameters.args == ["-m", "repo_guide.server", "--repo", str(context.path)]
    assert not any("shell" in argument for argument in parameters.args)


def test_console_scripts_are_installed_and_callable_from_outside_workspace(tmp_path: Path) -> None:
    package = distribution("repo-guide")
    scripts = {entry.name: entry for entry in package.entry_points if entry.group == "console_scripts"}
    bindir = Path(sys.executable).parent
    for name in ("repo-guide", "repo-guide-mcp"):
        executable = bindir / name
        if not executable.exists():
            pytest.skip(f"console script {name} is not installed in this interpreter")
        result = subprocess.run(
            [str(executable), "--version"],
            cwd=tmp_path,
            check=False,
            shell=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0
        assert __version__ in result.stdout
        assert result.stderr == ""
        assert scripts[name].value in {"repo_guide.server:main", "repo_guide.agent:main"}


def test_server_invalid_root_exits_with_stderr_only_from_unrelated_directory(tmp_path: Path) -> None:
    not_a_repo = tmp_path / "not a repository"
    not_a_repo.mkdir()
    result = subprocess.run(
        [sys.executable, "-m", "repo_guide.server", "--repo", str(not_a_repo)],
        cwd=tmp_path,
        check=False,
        shell=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert "not inside a Git working tree" in result.stderr


def test_agent_invalid_root_exits_cleanly_without_starting_ollama(tmp_path: Path) -> None:
    not_a_repo = tmp_path / "not a repository"
    not_a_repo.mkdir()
    result = subprocess.run(
        [sys.executable, "-m", "repo_guide.agent", "--repo", str(not_a_repo)],
        cwd=tmp_path,
        check=False,
        shell=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "not inside a Git working tree" in result.stderr


def test_module_imports_are_from_installed_package_not_current_working_directory(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import repo_guide, repo_guide.server, repo_guide.agent; print(repo_guide.__version__)"],
        cwd=tmp_path,
        check=False,
        shell=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == __version__
    assert result.stderr == ""
