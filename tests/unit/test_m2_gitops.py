"""M2 local repository operation tests using only synthetic repositories."""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

import pytest

import repo_guide.gitops as gitops
from repo_guide.config import SafetyLimits
from repo_guide.errors import PathPolicyError, RepoGuideError, RootResolutionError
from repo_guide.root import RootContext, RootMode, resolve_root


def git(cwd: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(cwd), *arguments],
        check=True,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def make_repo(path: Path, *, commit: bool = True) -> RootContext:
    path.mkdir(parents=True)
    git(path, "init", "--quiet")
    git(path, "config", "user.name", "Fixture User")
    git(path, "config", "user.email", "fixture@example.invalid")
    if commit:
        (path / "README.md").write_text("Fixture repository\n", encoding="utf-8")
        git(path, "add", "README.md")
        git(path, "commit", "--quiet", "-m", "initial fixture")
    return resolve_root(path, home=path.parent / "unrelated-home")


def commit_file(context: RootContext, path: str, content: str, message: str) -> None:
    file_path = context.path / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    git(context.path, "add", "--", path)
    git(context.path, "commit", "--quiet", "-m", message)


@pytest.fixture
def repository(tmp_path: Path) -> RootContext:
    context = make_repo(tmp_path / "repo with spaces – ü")
    commit_file(context, "src/hello world.py", "NEEDLE = 'literal'\nsecond = 2\n", "Add literal")
    commit_file(context, "資料/配置.ts", "const value = 'NEEDLE';\n", "Update config")
    return context


def test_list_tree_returns_sorted_safe_entries_and_omits_generated_and_denied(
    repository: RootContext,
) -> None:
    (repository.path / ".env.local").write_text("synthetic", encoding="utf-8")
    (repository.path / "node_modules").mkdir()
    (repository.path / "node_modules" / "ignored.js").write_text("x", encoding="utf-8")
    (repository.path / "image.png").write_bytes(b"\x89PNG\x00")
    (repository.path / "link-out").symlink_to(repository.path.parent, target_is_directory=True)

    result = gitops.list_tree(repository, depth=3)
    names = [entry.path for entry in result.entries]

    assert names == sorted(names, key=str.casefold)
    assert "README.md" in names
    assert "src/hello world.py" in names
    assert ".env.local" not in names
    assert "node_modules" not in names
    assert "image.png" not in names
    assert any(entry.path == "link-out" and entry.kind == "symlink" for entry in result.entries)
    assert all(entry.size_bytes is None or entry.size_bytes >= 0 for entry in result.entries)


def test_list_tree_honors_depth_entry_cap_and_empty_repository(tmp_path: Path) -> None:
    context = make_repo(tmp_path / "tree", commit=False)
    (context.path / "one").mkdir()
    (context.path / "one" / "two").mkdir()
    (context.path / "one" / "two" / "leaf.txt").write_text("leaf", encoding="utf-8")
    (context.path / "a.txt").write_text("a", encoding="utf-8")
    limited_context = RootContext(
        context.path,
        context.mode,
        SafetyLimits(max_tree_entries=2),
    )

    shallow = gitops.list_tree(limited_context, depth=1, max_entries=2)
    capped = gitops.list_tree(limited_context, depth=3, max_entries=2)
    assert {entry.path for entry in shallow.entries} == {"a.txt", "one"}
    assert capped.truncated is True
    assert len(capped.entries) == 2

    empty = make_repo(tmp_path / "empty", commit=False)
    assert gitops.git_log(empty).commits == ()


def test_list_tree_rejects_bad_depth_and_caps(repository: RootContext) -> None:
    with pytest.raises(RepoGuideError):
        gitops.list_tree(repository, depth=5)
    with pytest.raises(RepoGuideError):
        gitops.list_tree(repository, max_entries=repository.limits.max_tree_entries + 1)


def test_read_file_numbers_requested_lines_and_reports_total(repository: RootContext) -> None:
    result = gitops.read_file(repository, "src/hello world.py", start_line=2, end_line=99)

    assert result.path == "src/hello world.py"
    assert result.start_line == 2
    assert result.end_line == 2
    assert result.total_lines == 2
    assert [(line.number, line.text) for line in result.lines] == [(2, "second = 2")]


def test_read_file_handles_empty_range_and_line_limits(repository: RootContext) -> None:
    empty = repository.path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    assert gitops.read_file(repository, "empty.txt").total_lines == 0
    with pytest.raises(RepoGuideError, match="positive and ordered"):
        gitops.read_file(repository, "README.md", start_line=0)
    with pytest.raises(RepoGuideError, match="beyond the end"):
        gitops.read_file(repository, "README.md", start_line=2)
    with pytest.raises(RepoGuideError, match="exceeds"):
        gitops.read_file(repository, "README.md", start_line=1, end_line=201)
    with pytest.raises(PathPolicyError):
        gitops.read_file(repository, "missing.txt")


@pytest.mark.parametrize("payload", [b"\x00binary", b"\xffinvalid"])
def test_read_file_denies_binary_invalid_encoding_and_oversize(
    repository: RootContext, payload: bytes
) -> None:
    (repository.path / "binary.dat").write_bytes(payload)
    with pytest.raises(PathPolicyError):
        gitops.read_file(repository, "binary.dat")

    (repository.path / "large.txt").write_text("12345", encoding="utf-8")
    small = RootContext(repository.path, repository.mode, SafetyLimits(max_file_bytes=4))
    with pytest.raises(PathPolicyError):
        gitops.read_file(small, "large.txt")


def test_read_file_uses_shared_denials_for_sensitive_and_generated_paths(
    repository: RootContext,
) -> None:
    (repository.path / ".env").write_text("synthetic", encoding="utf-8")
    with pytest.raises(PathPolicyError):
        gitops.read_file(repository, ".env")
    with pytest.raises(PathPolicyError):
        gitops.read_file(repository, "../outside")


def test_search_literal_matches_paths_with_unicode_and_fixed_string_syntax(
    repository: RootContext,
) -> None:
    result = gitops.search_code(repository, "NEEDLE", path_glob="資料/*.ts")
    assert [(match.path, match.line) for match in result.matches] == [("資料/配置.ts", 1)]

    metacharacters = "$(touch should-not-exist) .* [x] ; `echo nope`"
    (repository.path / "src" / "literal.txt").write_text(metacharacters, encoding="utf-8")
    git(repository.path, "add", "--", "src/literal.txt")
    git(repository.path, "commit", "--quiet", "-m", "metachar fixture")
    exact = gitops.search_code(repository, metacharacters)
    assert any(match.path == "src/literal.txt" and match.text == metacharacters for match in exact.matches)
    assert not (repository.path / "should-not-exist").exists()


def test_search_handles_no_matches_untracked_files_and_result_caps(repository: RootContext) -> None:
    no_matches = gitops.search_code(repository, "absent-symbol")
    assert no_matches.matches == ()
    (repository.path / "untracked.txt").write_text("UNTRACKED", encoding="utf-8")
    assert gitops.search_code(repository, "UNTRACKED").matches == ()

    context = RootContext(repository.path, repository.mode, SafetyLimits(max_search_results=1))
    results = gitops.search_code(context, "NEEDLE")
    assert len(results.matches) == 1
    assert results.truncated is True


def test_search_excludes_sensitive_and_binary_tracked_content(repository: RootContext) -> None:
    (repository.path / ".env").write_text("LEAKME", encoding="utf-8")
    (repository.path / "binary.txt").write_bytes(b"LEAKME\x00")
    git(repository.path, "add", "--", ".env", "binary.txt")
    git(repository.path, "commit", "--quiet", "-m", "sensitive fixture")

    result = gitops.search_code(repository, "LEAKME")
    assert result.matches == ()


def test_search_excludes_tracked_generated_directories(repository: RootContext) -> None:
    generated = repository.path / "vendor" / "generated.txt"
    generated.parent.mkdir()
    generated.write_text("GENERATED_MARKER", encoding="utf-8")
    git(repository.path, "add", "--", "vendor/generated.txt")
    git(repository.path, "commit", "--quiet", "-m", "generated fixture")

    assert gitops.search_code(repository, "GENERATED_MARKER").matches == ()


@pytest.mark.parametrize("query", ["", "x\ny", "x\x00y", "x" * 101])
def test_search_rejects_invalid_queries(repository: RootContext, query: str) -> None:
    with pytest.raises(RepoGuideError):
        gitops.search_code(repository, query)


def test_search_validates_filter_and_caps(repository: RootContext) -> None:
    with pytest.raises(RepoGuideError):
        gitops.search_code(repository, "NEEDLE", path_glob="../../*", max_results=1)
    with pytest.raises(RepoGuideError):
        gitops.search_code(
            repository,
            "NEEDLE",
            max_results=repository.limits.max_search_results + 1,
        )


def test_git_log_filters_path_date_message_and_changed_string(repository: RootContext) -> None:
    path_result = gitops.git_log(repository, path="資料/配置.ts")
    assert [commit.subject for commit in path_result.commits] == ["Update config"]
    assert path_result.commits[0].changed_files == ("資料/配置.ts",)

    since_result = gitops.git_log(repository, since="2000-01-01")
    assert len(since_result.commits) == 3
    message_result = gitops.git_log(repository, message_contains="literal")
    assert [commit.subject for commit in message_result.commits] == ["Add literal"]
    string_result = gitops.git_log(repository, string_changed="NEEDLE")
    assert {commit.subject for commit in string_result.commits} == {"Add literal", "Update config"}
    assert all(len(commit.commit_hash) == 40 for commit in string_result.commits)


def test_git_log_reports_shallow_clone_and_enforces_filters(repository: RootContext) -> None:
    with pytest.raises(RepoGuideError):
        gitops.git_log(repository, since="yesterday")
    with pytest.raises(RepoGuideError):
        gitops.git_log(repository, path="../bad")
    with pytest.raises(RepoGuideError):
        gitops.git_log(repository, n=51)
    git(repository.path, "clone", "--quiet", "--depth", "1", repository.path.as_uri(),
        str(repository.path.parent / "shallow"))
    shallow = resolve_root(repository.path.parent / "shallow", home=repository.path.parent / "home")
    result = gitops.git_log(shallow)
    assert result.shallow is True
    assert len(result.commits) <= 10


def test_reduced_mode_rejects_git_operations_but_allows_local_overview(tmp_path: Path) -> None:
    directory = tmp_path / "non-git"
    directory.mkdir()
    (directory / "README.md").write_text("hello", encoding="utf-8")
    context = RootContext(directory, RootMode.REDUCED)

    assert gitops.read_file(context, "README.md").lines[0].text == "hello"
    assert gitops.repo_overview(context).readme_present is True
    with pytest.raises(RootResolutionError):
        gitops.search_code(context, "hello")
    with pytest.raises(RootResolutionError):
        gitops.git_log(context)


def test_repo_overview_reports_candidates_not_verified_entry_points(repository: RootContext) -> None:
    (repository.path / "main.py").write_text("print('candidate')\n", encoding="utf-8")
    overview = gitops.repo_overview(repository)

    assert overview.readme_present is True
    assert overview.languages["Python"] >= 1
    assert "main.py" in overview.likely_entry_points
    assert overview.truncated is False
    assert all(entry.path == "README.md" or "/" not in entry.path for entry in overview.top_level_entries)


def test_git_operations_are_read_only(repository: RootContext) -> None:
    before = git(repository.path, "status", "--porcelain=v1", "--untracked-files=all")
    tracked_before = git(repository.path, "ls-files", "-z")
    files_before = {
        path.relative_to(repository.path).as_posix(): path.read_bytes()
        for path in repository.path.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }

    gitops.list_tree(repository, depth=3)
    gitops.read_file(repository, "README.md")
    gitops.search_code(repository, "NEEDLE")
    gitops.git_log(repository)
    gitops.repo_overview(repository)

    after = git(repository.path, "status", "--porcelain=v1", "--untracked-files=all")
    tracked_after = git(repository.path, "ls-files", "-z")
    files_after = {
        path.relative_to(repository.path).as_posix(): path.read_bytes()
        for path in repository.path.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    assert after == before
    assert tracked_after == tracked_before
    assert files_after == files_before


def test_git_command_timeout_and_missing_executable_are_structured(
    repository: RootContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    short = RootContext(
        repository.path,
        repository.mode,
        SafetyLimits(subprocess_timeout_seconds=0.001),
    )

    class TimeoutProcess:
        stdout = io.BytesIO()
        waits = 0

        def wait(self, timeout: float | None = None) -> int:
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired("git", timeout)
            return -9

        def kill(self) -> None:
            pass

    def timeout_process(*args: object, **kwargs: object) -> TimeoutProcess:
        return TimeoutProcess()

    monkeypatch.setattr(gitops.subprocess, "Popen", timeout_process)
    with pytest.raises(RepoGuideError) as timed_out:
        gitops.search_code(short, "NEEDLE")
    assert timed_out.value.code == "git_timeout"

    monkeypatch.setattr(gitops.shutil, "which", lambda _: None)
    with pytest.raises(RootResolutionError) as missing:
        gitops.git_log(repository)
    assert missing.value.code == "git_unavailable"


def test_git_output_is_capped(repository: RootContext) -> None:
    context = RootContext(
        repository.path,
        repository.mode,
        SafetyLimits(max_subprocess_output_bytes=64),
    )
    result = gitops.search_code(context, "NEEDLE")
    assert result.truncated is True
    assert len(result.matches) <= context.limits.max_search_results