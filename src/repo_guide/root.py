"""Resolve and freeze the single repository root used by a server process."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Mapping

from repo_guide.config import SafetyLimits
from repo_guide.errors import RootResolutionError

_GIT_ENV = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_PAGER": "cat",
    "GIT_TERMINAL_PROMPT": "0",
    "PATH": os.defpath,
}


class RootMode(StrEnum):
    """Available modes for repository operations."""

    GIT = "git"
    REDUCED = "reduced"


class Capability(StrEnum):
    """Operation classes gated by the resolved root mode."""

    FILESYSTEM = "filesystem"
    GIT_HISTORY = "git_history"
    GITHUB_ISSUES = "github_issues"


@dataclass(frozen=True, slots=True)
class RootContext:
    """Immutable canonical root and capabilities for one process lifetime."""

    path: Path
    mode: RootMode
    limits: SafetyLimits = SafetyLimits()

    def require_capability(self, capability: Capability) -> None:
        """Reject Git-derived behavior in explicitly enabled reduced mode."""
        if self.mode is RootMode.REDUCED and capability is not Capability.FILESYSTEM:
            raise RootResolutionError(
                "capability_unavailable",
                f"{capability.value} is unavailable in reduced mode",
            )


def resolve_root(
    repo: str | os.PathLike[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    cwd: str | os.PathLike[str] | None = None,
    home: str | os.PathLike[str] | None = None,
    allow_non_git: bool = False,
    limits: SafetyLimits | None = None,
) -> RootContext:
    """Resolve ``--repo`` > environment > cwd and normalize a Git worktree.

    The model-facing application should retain only the returned immutable
    context. It must not pass tool arguments into this startup-only function.
    """
    env = os.environ if environ is None else environ
    if repo is not None:
        candidate: str | os.PathLike[str] = repo
    elif env.get("REPO_GUIDE_ROOT"):
        candidate = env["REPO_GUIDE_ROOT"]
    elif cwd is not None:
        candidate = cwd
    else:
        candidate = Path.cwd()

    try:
        initial = Path(candidate).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise RootResolutionError("invalid_root", "repository root is not an accessible path") from exc
    if not initial.is_dir():
        raise RootResolutionError("invalid_root", "repository root must be an existing directory")

    user_home = Path(home).expanduser().resolve() if home is not None else Path.home().resolve()
    _reject_protected_root(initial, user_home)
    configured_limits = limits or SafetyLimits()

    git = shutil.which("git")
    if git is None:
        if allow_non_git:
            return RootContext(initial, RootMode.REDUCED, configured_limits)
        raise RootResolutionError("git_unavailable", "Git is required unless reduced mode is enabled")

    bare = _run_git(git, initial, "--is-bare-repository", configured_limits)
    if bare is not None and bare.stdout.strip() == b"true":
        raise RootResolutionError("bare_repository", "bare repositories are not supported")

    top_level = _run_git(git, initial, "--show-toplevel", configured_limits)
    if top_level is None:
        if allow_non_git:
            return RootContext(initial, RootMode.REDUCED, configured_limits)
        raise RootResolutionError("not_git_repository", "path is not inside a Git working tree")

    try:
        canonical = Path(os.fsdecode(top_level.stdout).removesuffix("\n")).resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise RootResolutionError("invalid_git_root", "Git returned an invalid working-tree root") from exc
    if not canonical.is_dir():
        raise RootResolutionError("invalid_git_root", "Git working-tree root is not a directory")
    _reject_protected_root(canonical, user_home)
    return RootContext(canonical, RootMode.GIT, configured_limits)


def _reject_protected_root(path: Path, home: Path) -> None:
    if path == Path(path.anchor):
        raise RootResolutionError("unsafe_root", "filesystem root cannot be served")
    if path == home:
        raise RootResolutionError("unsafe_root", "user home directory cannot be served")


def _run_git(
    executable: str,
    cwd: Path,
    argument: str,
    limits: SafetyLimits,
) -> subprocess.CompletedProcess[bytes] | None:
    """Run one fixed, bounded, read-only Git query; never invoke a shell."""
    try:
        result = subprocess.run(
            [executable, "-C", os.fspath(cwd), "rev-parse", argument],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=limits.subprocess_timeout_seconds,
            check=False,
            shell=False,
            env=_GIT_ENV,
        )
    except subprocess.TimeoutExpired as exc:
        raise RootResolutionError("git_timeout", "Git root detection exceeded its time limit") from exc
    except OSError as exc:
        raise RootResolutionError("git_unavailable", "Git could not be started") from exc

    if (
        len(result.stdout) > limits.max_subprocess_output_bytes
        or len(result.stderr) > limits.max_subprocess_output_bytes
    ):
        raise RootResolutionError("git_output_limit", "Git root detection exceeded its output limit")
    return result if result.returncode == 0 else None