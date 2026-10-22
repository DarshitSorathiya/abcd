"""IDE configuration, server root isolation, and client-facing MCP compatibility tests."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import Client, StdioServerParameters
from mcp.types import TextResourceContents

from repo_guide.root import resolve_root

WORKSPACE = Path(__file__).resolve().parents[2]


def git(cwd: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), *arguments],
        check=True,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def make_repo(path: Path, contents: str) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "--quiet")
    (path / "README.md").write_text(contents, encoding="utf-8")
    git(path, "add", "--", "README.md")
    git(path, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "fixture")
    return path


def test_vscode_configuration_has_workspace_scoped_stdio_root() -> None:
    config = json.loads((WORKSPACE / "examples" / "vscode.mcp.json").read_text(encoding="utf-8"))

    server = config["servers"]["repoGuide"]
    assert server == {
        "type": "stdio",
        "command": "repo-guide-mcp",
        "args": ["--repo", "${workspaceFolder}"],
    }


def test_portable_configuration_uses_explicit_absolute_root_placeholder() -> None:
    config = json.loads((WORKSPACE / "examples" / "portable.mcp.json").read_text(encoding="utf-8"))

    server = config["mcpServers"]["repoGuide"]
    assert server["command"] == "repo-guide-mcp"
    assert server["args"] == ["--repo", "/ABSOLUTE/PATH/TO/REPOSITORY"]
    assert "${workspaceFolder}" not in json.dumps(config)
    assert "cwd" not in server


def test_cursor_configuration_uses_project_workspace_variable() -> None:
    config = json.loads((WORKSPACE / "examples" / "cursor.mcp.json").read_text(encoding="utf-8"))

    server = config["mcpServers"]["repoGuide"]
    assert server == {
        "type": "stdio",
        "command": "repo-guide-mcp",
        "args": ["--repo", "${workspaceFolder}"],
    }


def test_root_precedence_nested_and_explicit_repo_remain_shared(tmp_path: Path) -> None:
    repository_a = make_repo(tmp_path / "A with spaces", "Repository A\n")
    repository_b = make_repo(tmp_path / "B 数据", "Repository B\n")
    nested = repository_a / "nested" / "child"
    nested.mkdir(parents=True)
    home = tmp_path / "home"
    home.mkdir()

    nested_context = resolve_root(nested, environ={}, home=home)
    env_context = resolve_root(None, environ={"REPO_GUIDE_ROOT": str(repository_b)}, cwd=nested, home=home)
    explicit_context = resolve_root(repository_a, environ={"REPO_GUIDE_ROOT": str(repository_b)}, cwd=nested, home=home)

    assert nested_context.path == repository_a.resolve()
    assert env_context.path == repository_b.resolve()
    assert explicit_context.path == repository_a.resolve()


def test_explicit_repo_server_launch_uses_root_not_another_cwd(tmp_path: Path) -> None:
    selected = make_repo(tmp_path / "selected repo", "Selected root\n")
    other = make_repo(tmp_path / "other repo", "Wrong root\n")

    async def connect_and_read() -> str:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "repo_guide.server", "--repo", str(selected)],
            cwd=str(other),
        )
        async with Client(parameters) as client:
            result = await client.read_resource("repo://readme")
            return result.contents[0].text

    readme = asyncio.run(connect_and_read())
    assert "Selected root" in readme
    assert "Wrong root" not in readme


def test_two_concurrent_stdio_processes_are_isolated_and_expose_same_server_contract(
    tmp_path: Path,
) -> None:
    repo_a = make_repo(tmp_path / "repo A", "Workspace Alpha\n")
    repo_b = make_repo(tmp_path / "repo B – β", "Workspace Beta\n")
    home = tmp_path / "home"
    home.mkdir()
    context_a = resolve_root(repo_a, environ={}, home=home)
    context_b = resolve_root(repo_b, environ={}, home=home)

    async def exercise(context: Any, expected: str) -> tuple[str, set[str], set[str], str]:
        args = ["-m", "repo_guide.server", "--repo", str(context.path)]
        parameters = StdioServerParameters(command=sys.executable, args=args)
        async with Client(parameters) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools.tools}
            resources = await client.list_resources()
            resource_uris = {str(resource.uri) for resource in resources.resources}
            prompts = await client.list_prompts()
            prompt_names = {prompt.name for prompt in prompts.prompts}
            readme = await client.read_resource("repo://readme")
            assert isinstance(readme.contents[0], TextResourceContents)
            return readme.contents[0].text, names, resource_uris, ",".join(sorted(prompt_names))

    async def run_both() -> tuple[tuple[str, set[str], set[str], str], ...]:
        return tuple(
            await asyncio.gather(
                exercise(context_a, "Workspace Alpha"),
                exercise(context_b, "Workspace Beta"),
            )
        )

    result_a, result_b = asyncio.run(run_both())

    for actual, expected, other_marker in (
        (result_a[0], "Workspace Alpha", "Workspace Beta"),
        (result_b[0], "Workspace Beta", "Workspace Alpha"),
    ):
        assert expected in actual
        assert other_marker not in actual
    expected_tools = {"list_tree", "read_file", "search_code", "git_log", "repo_overview", "list_issues"}
    assert result_a[1] == expected_tools
    assert result_b[1] == expected_tools
    assert result_a[2] == {"repo://readme", "repo://tree"}
    assert result_b[2] == {"repo://readme", "repo://tree"}
    assert "onboarding_guide" in result_a[3]
    assert "onboarding_guide" in result_b[3]


def test_unsafe_root_is_refused_by_shared_resolver(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    with pytest.raises(Exception) as error:
        resolve_root(home, environ={}, allow_non_git=True, home=home)
    assert getattr(error.value, "code", None) == "unsafe_root"


def test_server_startup_failures_keep_stdout_empty(tmp_path: Path) -> None:
    invalid = tmp_path / "not a repository"
    invalid.mkdir()
    result = subprocess.run(
        [sys.executable, "-m", "repo_guide.server", "--repo", str(invalid)],
        cwd=tmp_path,
        shell=False,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode != 0
    assert result.stdout == ""
    assert "not inside a Git working tree" in result.stderr
