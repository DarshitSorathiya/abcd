"""MCP protocol and stdio coverage for the M3 server integration."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from functools import wraps
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import Client, StdioServerParameters
from mcp.types import TextResourceContents

import repo_guide.server as server_module
from repo_guide.root import RootContext, RootMode, resolve_root
from repo_guide.server import build_server


def git(cwd: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), *arguments],
        check=True,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def make_repository(path: Path, *, git_repo: bool = True, readme: bool = True) -> RootContext:
    path.mkdir(parents=True)
    if git_repo:
        git(path, "init", "--quiet")
        git(path, "config", "user.name", "MCP Fixture")
        git(path, "config", "user.email", "mcp-fixture@example.invalid")
    tracked: list[str] = []
    if readme:
        (path / "README.md").write_text("# Fixture\nSafe documentation.\n", encoding="utf-8")
        tracked.append("README.md")
    (path / "main.py").write_text("def main():\n    return 'fixture'\n", encoding="utf-8")
    tracked.append("main.py")
    (path / "secrets").mkdir()
    (path / "secrets" / ".env").write_text("DO_NOT_DISCLOSE=synthetic\n", encoding="utf-8")
    tracked.append("secrets/.env")
    if git_repo:
        git(path, "add", "--", *tracked)
        git(path, "commit", "--quiet", "-m", "fixture base")
        return resolve_root(path, home=path.parent / "unrelated-home")
    return RootContext(path.resolve(), RootMode.REDUCED)


def structured(result: Any) -> dict[str, Any]:
    assert not result.is_error
    assert result.structured_content is not None
    return result.structured_content


def mcp_test(function: Callable[..., Awaitable[None]]) -> Callable[..., None]:
    """Run one async MCP test without relying on an extra pytest plugin."""
    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        asyncio.run(function(*args, **kwargs))

    return wrapper


@pytest.fixture
def repository(tmp_path: Path) -> RootContext:
    return make_repository(tmp_path / "fixture repo with spaces")


@mcp_test
async def test_server_exposes_exact_tools_schemas_descriptions_and_all_tool_calls(
    repository: RootContext,
) -> None:
    server = build_server(repository)
    async with Client(server) as client:
        listed = await client.list_tools()
        by_name = {tool.name: tool for tool in listed.tools}
        assert set(by_name) == {
            "list_tree",
            "read_file",
            "search_code",
            "git_log",
            "repo_overview",
            "list_issues",
        }
        for tool in by_name.values():
            assert tool.description
            assert tool.input_schema["type"] == "object"

        assert "path" in by_name["list_tree"].input_schema["properties"]
        assert "query" in by_name["search_code"].input_schema["properties"]
        assert "since" in by_name["git_log"].input_schema["properties"]

        tree = structured(await client.call_tool("list_tree", {"depth": 2, "max_entries": 20}))
        assert any(entry["path"] == "main.py" for entry in tree["entries"])
        assert not any(".env" in entry["path"] for entry in tree["entries"])

        file_result = structured(await client.call_tool("read_file", {"path": "main.py"}))
        assert file_result["total_lines"] == 2
        assert file_result["lines"][0] == {"number": 1, "text": "def main():"}

        search = structured(await client.call_tool("search_code", {"query": "fixture"}))
        assert search["tracked_files_only"] is True
        assert any(match["path"] == "main.py" for match in search["matches"])

        history = structured(await client.call_tool("git_log", {}))
        assert history["commits"][0]["subject"] == "fixture base"

        overview = structured(await client.call_tool("repo_overview", {}))
        assert overview["readme_present"] is True
        assert "main.py" in overview["likely_entry_points"]


@mcp_test
async def test_invalid_tool_arguments_and_hostile_paths_return_controlled_errors(
    repository: RootContext,
) -> None:
    async with Client(build_server(repository)) as client:
        invalid = await client.call_tool("list_tree", {"depth": 99})
        assert invalid.is_error
        assert "invalid_depth" in invalid.content[0].text

        traversal = await client.call_tool("read_file", {"path": "../outside.txt"})
        assert traversal.is_error
        assert "path_traversal" in traversal.content[0].text

        denied = await client.call_tool("read_file", {"path": "secrets/.env"})
        assert denied.is_error
        assert "DO_NOT_DISCLOSE" not in denied.content[0].text
        assert "synthetic" not in denied.content[0].text

        missing = await client.call_tool("read_file", {"path": "missing.txt"})
        assert missing.is_error
        assert "path_unavailable" in missing.content[0].text


@mcp_test
async def test_symlink_escape_is_rejected_through_mcp(
    repository: RootContext, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("outside secret", encoding="utf-8")
    link = repository.path / "escape.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    async with Client(build_server(repository)) as client:
        result = await client.call_tool("read_file", {"path": "escape.txt"})
        assert result.is_error
        assert "symlink_denied" in result.content[0].text
        assert "outside secret" not in result.content[0].text


@mcp_test
async def test_read_limits_and_tree_truncation_survive_mcp_wrapping(tmp_path: Path) -> None:
    context = make_repository(tmp_path / "small", readme=False)
    limits = context.limits.__class__(max_tree_entries=2)
    context = RootContext(context.path, context.mode, limits)
    for name in ("a.txt", "b.txt", "c.txt"):
        (context.path / name).write_text(name, encoding="utf-8")

    async with Client(build_server(context)) as client:
        tree = structured(await client.call_tool("list_tree", {"max_entries": 2}))
        assert len(tree["entries"]) == 2
        assert tree["truncated"] is True

        oversized_range = await client.call_tool(
            "read_file", {"path": "main.py", "start_line": 1, "end_line": 201}
        )
        assert oversized_range.is_error
        assert "line_limit_exceeded" in oversized_range.content[0].text


@mcp_test
async def test_resources_are_lazy_bounded_and_safely_handle_missing_readme(
    repository: RootContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_list_tree = server_module.gitops.list_tree
    calls: list[str] = []

    def tracked_list_tree(*args: Any, **kwargs: Any) -> Any:
        calls.append("tree")
        return original_list_tree(*args, **kwargs)

    monkeypatch.setattr(server_module.gitops, "list_tree", tracked_list_tree)
    server = build_server(repository)
    assert calls == []
    async with Client(server) as client:
        listed = await client.list_resources()
        assert {str(resource.uri) for resource in listed.resources} == {
            "repo://readme",
            "repo://tree",
        }

        readme = await client.read_resource("repo://readme")
        assert isinstance(readme.contents[0], TextResourceContents)
        assert "Safe documentation." in readme.contents[0].text

        tree = await client.read_resource("repo://tree")
        tree_payload = json.loads(tree.contents[0].text)
        assert calls == ["tree"]
        assert tree_payload["entries"]
        assert isinstance(tree_payload["truncated"], bool)

    without_readme = make_repository(tmp_path / "no-readme", readme=False)
    async with Client(build_server(without_readme)) as client:
        with pytest.raises(Exception, match="README"):
            await client.read_resource("repo://readme")


@mcp_test
async def test_readme_resource_applies_explicit_output_byte_limit(
    repository: RootContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server_module, "_README_OUTPUT_BYTES", 128)
    (repository.path / "README.md").write_text("# Fixture\n" + "documentation " * 30, encoding="utf-8")
    async with Client(build_server(repository)) as client:
        result = await client.read_resource("repo://readme")
    text = result.contents[0].text
    assert len(text.encode("utf-8")) <= 128
    assert "README truncated" in text


@mcp_test
async def test_prompt_is_discoverable_and_rendered_with_safe_instructions(
    repository: RootContext,
) -> None:
    async with Client(build_server(repository)) as client:
        prompts = await client.list_prompts()
        onboarding = next(prompt for prompt in prompts.prompts if prompt.name == "onboarding_guide")
        assert onboarding.arguments[0].name == "repo_name"
        rendered = await client.get_prompt("onboarding_guide", {"repo_name": "fixture"})
        prompt_text = rendered.messages[0].content.text
        assert "observed facts" in prompt_text
        assert "untrusted data" in prompt_text
        assert "paths and line numbers" in prompt_text
        assert "fixture" in prompt_text


@mcp_test
async def test_reduced_mode_hides_git_data_but_keeps_filesystem_operations(tmp_path: Path) -> None:
    context = make_repository(tmp_path / "reduced", git_repo=False, readme=False)
    async with Client(build_server(context)) as client:
        file_result = structured(await client.call_tool("read_file", {"path": "main.py"}))
        assert file_result["total_lines"] == 2
        overview = structured(await client.call_tool("repo_overview", {}))
        assert overview["readme_present"] is False

        for tool_name, arguments in (("search_code", {"query": "main"}), ("git_log", {})):
            result = await client.call_tool(tool_name, arguments)
            assert result.is_error
            assert "unavailable in reduced mode" in result.content[0].text


@mcp_test
async def test_server_root_is_fixed_even_if_process_environment_changes(
    repository: RootContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = make_repository(tmp_path / "other")
    monkeypatch.setenv("REPO_GUIDE_ROOT", str(other.path))
    async with Client(build_server(repository)) as client:
        result = structured(await client.call_tool("read_file", {"path": "README.md"}))
    assert "Fixture" in result["lines"][0]["text"]


@mcp_test
async def test_actual_stdio_server_smoke_and_stdout_protocol_hygiene(
    repository: RootContext,
) -> None:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "repo_guide.server", "--repo", str(repository.path)],
    )
    async with Client(parameters) as client:
        tools = await client.list_tools()
        assert len(tools.tools) == 6
        result = await client.call_tool("read_file", {"path": "README.md"})
        assert not result.is_error
        assert "Fixture" in result.structured_content["lines"][0]["text"]


@mcp_test
async def test_stdio_startup_reports_to_stderr_and_invalid_root_exits_nonzero(
    tmp_path: Path,
) -> None:
    invalid_root = tmp_path / "not a repository"
    invalid_root.mkdir()
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "repo_guide.server",
        "--repo",
        str(invalid_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
    assert process.returncode == 2
    assert stdout == b""
    assert b"not inside a Git working tree" in stderr


def test_startup_root_errors_and_logging_do_not_print_to_stdout(
    repository: RootContext, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(server_module, "resolve_root", lambda *args, **kwargs: repository)

    class StoppedServer:
        def run(self, *, transport: str) -> None:
            assert transport == "stdio"

    monkeypatch.setattr(server_module, "build_server", lambda *args, **kwargs: StoppedServer())
    assert server_module.main(["--repo", str(repository.path), "--verbose"]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "repo-guide-mcp 0.1.0 root=" in captured.err
    assert "mode=git" in captured.err


def test_server_construction_does_not_call_external_service(repository: RootContext, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("issue API must not run during server construction")

    monkeypatch.setattr(server_module.github_api, "list_issues", fail_if_called)
    build_server(repository)
    assert "ollama" not in sys.modules
