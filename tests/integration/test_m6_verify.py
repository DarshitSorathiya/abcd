"""Deterministic citation, provenance, sanitization, and reflection tests for M6."""

from __future__ import annotations

import asyncio
import contextlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import repo_guide.verify as verify_module
import repo_guide.agent as agent_module
from repo_guide.config import AgentSettings
from repo_guide.errors import AgentError, RepoGuideError
from repo_guide.root import RootContext, RootMode, resolve_root
from repo_guide.verify import (
    Citation,
    extract_citations,
    verify_and_reflect,
    verify_answer,
)


def git(cwd: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(cwd), *arguments],
        check=True,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


@pytest.fixture
def repo(tmp_path: Path) -> RootContext:
    root = tmp_path / "repo with spaces – 数据"
    root.mkdir()
    git(root, "init", "--quiet")
    git(root, "config", "user.name", "M6 Fixture")
    git(root, "config", "user.email", "m6@example.invalid")
    source = root / "src" / "main file.py"
    source.parent.mkdir()
    source.write_text("def answer():\n    return 'verified snippet value'\n\n# last line\n", encoding="utf-8")
    (root / "README.md").write_text("Repository overview\n", encoding="utf-8")
    (root / ".env").write_text("synthetic secret fixture", encoding="utf-8")
    (root / "binary.txt").write_bytes(b"\x00binary")
    git(root, "add", "--", "src/main file.py", "README.md", ".env", "binary.txt")
    git(root, "commit", "--quiet", "-m", "fixture commit")
    return resolve_root(root, home=tmp_path / "not-home")


def file_evidence(path: str, start: int, end: int, *, truncated: bool = False) -> tuple[dict[str, Any], ...]:
    result = {
        "path": path,
        "start_line": start,
        "end_line": end,
        "total_lines": max(end, 4),
        "lines": [{"number": number, "text": "evidence"} for number in range(start, end + 1)],
    }
    return ({"tool": "read_file", "result": json.dumps(result), "is_error": False, "truncated": truncated},)


def search_evidence(path: str, lines: list[int]) -> tuple[dict[str, Any], ...]:
    result = {"matches": [{"path": path, "line": line, "text": "found"} for line in lines]}
    return ({"tool": "search_code", "result": json.dumps(result), "is_error": False},)


def commit_evidence(commit_hash: str) -> tuple[dict[str, Any], ...]:
    result = {"commits": [{"commit_hash": commit_hash}]}
    return ({"tool": "git_log", "result": json.dumps(result), "is_error": False},)


class FakeOllama:
    def __init__(self, responses: list[str | BaseException]) -> None:
        self.responses = list(responses)
        self.messages: list[list[dict[str, str]]] = []

    def chat(self, messages: list[dict[str, str]], *, temperature: float | None = None) -> str:
        self.messages.append(messages)
        if temperature is not None:
            assert temperature == 0.0
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _reflection(*claims: dict[str, str]) -> str:
    return json.dumps({"unsupported_claims": list(claims)}, ensure_ascii=False)


def test_extracts_backticks_markdown_bullets_ranges_and_commit_hash(repo: RootContext) -> None:
    commit = git(repo.path, "rev-parse", "HEAD").decode().strip()
    answer = (
        "- `src/main file.py:1-2` contains the function.\n"
        f"History: commit {commit}.\n"
        "The web API is https://example.invalid/path:44 and the time is 10:30."
    )

    citations = extract_citations(answer)

    assert [(item.kind, item.path, item.line_start, item.line_end) for item in citations[:1]] == [
        ("file", "src/main file.py", 1, 2)
    ]
    assert citations[1].kind == "commit"
    assert citations[1].commit_hash == commit
    assert len(citations) == 2


def test_ignores_urls_timestamps_hex_strings_examples_and_fenced_examples(repo: RootContext) -> None:
    answer = (
        "URL https://host.invalid/src/example.py:4; time 10:30; hex abcdef012345. "
        "For example `src/main file.py:2`.\n"
        "```text\nExample src/main.py:88 and commit abcdef1234567\n```"
    )

    assert extract_citations(answer) == ()


def test_extracts_malformed_citations_but_not_arbitrary_hex() -> None:
    citations = extract_citations("Bad source `../src/a.py:0` and `src/a.py:abc`; hash abcdef1234567")
    assert len(citations) == 2
    assert citations[0].kind == "file"  # syntactically valid form; semantic line/path checks reject it
    assert citations[1].kind == "malformed"


def test_file_citation_verifies_path_line_and_provenance(repo: RootContext) -> None:
    evidence = file_evidence("src/main file.py", 1, 2)
    report = verify_answer(repo, "Function is here at `src/main file.py:1-2`.", evidence)

    assert report.safe_to_display is True
    assert report.total_extracted_citations == 1
    assert report.valid_citations_before_sanitization == 1
    assert report.citation_validity_rate_before == 1.0
    assert report.valid_citations_after_sanitization == 1
    assert report.citation_validity_rate_after == 1.0


@pytest.mark.parametrize(
    ("answer", "evidence", "reason"),
    [
        ("Bad path `missing.py:1`.", file_evidence("missing.py", 1, 1), "path_unavailable"),
        ("Bad line `src/main file.py:0`.", file_evidence("src/main file.py", 1, 1), "line range"),
        ("Beyond EOF `src/main file.py:99`.", file_evidence("src/main file.py", 1, 1), "beyond end"),
        ("No provenance `src/main file.py:2`.", file_evidence("README.md", 1, 1), "not returned"),
        ("Traversal `../outside.py:1`.", file_evidence("../outside.py", 1, 1), "invalid"),
        ("Sensitive `.env:1`.", file_evidence(".env", 1, 1), "sensitive_path"),
        ("Binary `binary.txt:1`.", file_evidence("binary.txt", 1, 1), "binary_file"),
        ("Absolute `/etc/passwd:1`.", file_evidence("/etc/passwd", 1, 1), "absolute_path"),
    ],
)
def test_invalid_file_citations_are_sanitized_without_sensitive_content(
    repo: RootContext, answer: str, evidence: tuple[dict[str, Any], ...], reason: str
) -> None:
    report = verify_answer(repo, f"Supported unrelated fact. {answer}", evidence)

    assert report.safe_to_display is True
    assert "Supported unrelated fact." in report.final_answer
    assert answer.strip() not in report.final_answer
    assert report.invalid_citations_before_sanitization == 1
    assert any(reason in detail for detail in report.invalid_citation_details)
    assert "synthetic secret fixture" not in repr(report)


def test_search_provenance_and_ranges_require_every_line(repo: RootContext) -> None:
    valid = verify_answer(repo, "Line is `src/main file.py:2`.", search_evidence("src/main file.py", [2]))
    invalid = verify_answer(
        repo,
        "Range is `src/main file.py:1-2`.",
        search_evidence("src/main file.py", [1]),
    )
    too_wide = verify_answer(
        repo,
        "Too wide `src/main file.py:1-201`.",
        file_evidence("src/main file.py", 1, 201),
    )

    assert valid.safe_to_display
    assert not invalid.safe_to_display
    assert not too_wide.safe_to_display


@pytest.mark.parametrize("flag", ["is_error", "truncated"])
def test_failed_or_truncated_observation_cannot_establish_provenance(repo: RootContext, flag: str) -> None:
    evidence = ({
        "tool": "read_file",
        "result": json.dumps({"path": "src/main file.py", "lines": [{"number": 1}]}),
        flag: True,
    },)

    report = verify_answer(repo, "At `src/main file.py:1`.", evidence)

    assert report.safe_to_display is False
    assert "not returned as evidence" in report.invalid_citation_details[0]


def test_unicode_and_spaced_path_citation_is_supported(repo: RootContext) -> None:
    unicode_file = repo.path / "源 code.py"
    unicode_file.write_text("value = 'ok'\n", encoding="utf-8")
    evidence = file_evidence("源 code.py", 1, 1)

    report = verify_answer(repo, "Observed at `源 code.py:1`.", evidence)

    assert report.safe_to_display


def test_symlink_escape_is_denied(repo: RootContext, tmp_path: Path) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("outside", encoding="utf-8")
    link = repo.path / "escape.py"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    report = verify_answer(repo, "Escapes `escape.py:1`.", file_evidence("escape.py", 1, 1))

    assert not report.safe_to_display
    assert "symlink_denied" in report.invalid_citation_details[0]


def test_whitespace_normalized_quote_must_match_near_cited_line(repo: RootContext) -> None:
    evidence = file_evidence("src/main file.py", 2, 2)
    good = verify_answer(repo, "It returns `verified   snippet value` at `src/main file.py:2`.", evidence)
    wrong = verify_answer(repo, "It returns “totally unrelated exact quote here” at `src/main file.py:2`.", evidence)
    far = verify_answer(repo, "“def answer():” is at `src/main file.py:4`.", file_evidence("src/main file.py", 4, 4))
    short = verify_answer(repo, "“return 1” is at `src/main file.py:2`.", evidence)

    assert good.safe_to_display
    assert not wrong.safe_to_display
    assert not far.safe_to_display
    assert short.safe_to_display


def test_empty_and_oversized_quotes_are_handled(repo: RootContext) -> None:
    evidence = file_evidence("src/main file.py", 2, 2)
    empty = verify_answer(repo, "“” at `src/main file.py:2`.", evidence)
    oversized = verify_answer(repo, f"`{'x' * 600}` at `src/main file.py:2`.", evidence)

    assert empty.total_extracted_citations == 1
    assert oversized.invalid_citations_before_sanitization == 1


def test_commit_must_be_observed_and_exist_in_this_repository(repo: RootContext) -> None:
    commit = git(repo.path, "rev-parse", "HEAD").decode().strip()
    valid = verify_answer(repo, f"Changed in commit {commit[:9]}.", commit_evidence(commit))
    missing = verify_answer(repo, f"Changed in commit {commit}.", ())
    unknown = "f" * 40
    unknown_report = verify_answer(repo, f"Changed in commit {unknown}.", commit_evidence(unknown))

    assert valid.safe_to_display
    assert not missing.safe_to_display
    assert not unknown_report.safe_to_display


def test_commit_subprocess_timeout_is_an_operational_failure(repo: RootContext, monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*args: Any, **kwargs: Any) -> bool:
        raise RepoGuideError("git_timeout", "Git operation exceeded its time limit")

    monkeypatch.setattr(verify_module.gitops, "commit_exists", timeout)
    hash_value = git(repo.path, "rev-parse", "HEAD").decode().strip()

    report = verify_answer(repo, f"Changed in commit {hash_value}.", commit_evidence(hash_value))

    assert report.safe_to_display is False
    assert "all_cited_claims_removed" in report.verification_errors
    assert "operational_error" in report.invalid_citation_details[0]


def test_zero_citation_metrics_are_not_reported_as_one_hundred_percent(repo: RootContext) -> None:
    report = verify_answer(repo, "A general conceptual answer.", ())

    assert report.total_extracted_citations == 0
    assert report.citation_validity_rate_before is None
    assert report.citation_validity_rate_after is None
    assert report.safe_to_display


def test_invalid_citation_sentence_removed_and_final_citations_rechecked(repo: RootContext) -> None:
    evidence = file_evidence("src/main file.py", 1, 2)
    answer = "Supported at `src/main file.py:1`. Unsupported at `missing.py:5`. Another supported fact."

    report = verify_answer(repo, answer, evidence)

    assert "Supported at `src/main file.py:1`." in report.final_answer
    assert "Another supported fact." in report.final_answer
    assert "missing.py" not in report.final_answer
    assert report.citations_checked_after_sanitization == 1
    assert report.valid_citations_after_sanitization == 1
    assert report.citation_validity_rate_after == 1.0


def test_all_invalid_citations_produce_controlled_fallback(repo: RootContext) -> None:
    report = verify_answer(repo, "Unsupported at `missing.py:5`.", file_evidence("missing.py", 5, 5))

    assert report.safe_to_display is False
    assert "couldn't safely verify" in report.final_answer
    assert report.invalid_citations_before_sanitization == 1


def test_operational_file_error_is_distinct_from_confirmed_invalid_path(
    repo: RootContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: Any, **kwargs: Any) -> str:
        raise OSError("private machine path")

    monkeypatch.setattr(verify_module, "read_repo_file", fail)
    report = verify_answer(repo, "At `src/main file.py:1`.", file_evidence("src/main file.py", 1, 1))

    assert report.safe_to_display is False
    assert "operational_error" in report.invalid_citation_details[0]
    assert "private machine path" not in repr(report)


def test_reflection_sanitizes_only_exact_unique_claim_and_reverifies(repo: RootContext) -> None:
    evidence = file_evidence("src/main file.py", 1, 2)
    answer = "Verified claim at `src/main file.py:1`. Unsupported repository claim."
    ollama = FakeOllama([_reflection({"claim": "Unsupported repository claim.", "reason": "No evidence."})])

    report = asyncio.run(
        verify_and_reflect(repo, "Where is the function?", answer, evidence, ollama, AgentSettings())
    )

    assert report.reflection_attempted
    assert report.safe_to_display
    assert report.final_answer == "Verified claim at `src/main file.py:1`."
    assert report.valid_citations_after_sanitization == 1
    assert report.claims_removed_or_flagged == ("Unsupported repository claim.",)
    assert len(ollama.messages) == 1
    reflection_input = ollama.messages[0][1]["content"]
    assert "Unsupported repository claim." in reflection_input
    assert "whole repository" not in reflection_input


def test_reflection_cannot_replace_answer_or_add_citation(repo: RootContext) -> None:
    evidence = file_evidence("src/main file.py", 1, 2)
    answer = "Verified at `src/main file.py:1`."
    ollama = FakeOllama(
        [json.dumps({"unsupported_claims": [], "replacement_answer": "Invented at fake.py:9"})]
    )

    report = asyncio.run(
        verify_and_reflect(repo, "Question", answer, evidence, ollama, AgentSettings())
    )

    assert report.final_answer == answer
    assert report.reflection_error == "reflection_invalid_schema"
    assert report.safe_to_display
    assert "fake.py" not in report.final_answer


def test_reflection_malformed_or_timeout_is_recorded_once_and_fails_closed_for_uncited_repo_answer(
    repo: RootContext,
) -> None:
    evidence = file_evidence("src/main file.py", 1, 2)
    for failure, expected in (("not JSON", "reflection_invalid_json"), (AgentError("ollama_timeout", "timeout"), "ollama_timeout")):
        ollama = FakeOllama([failure])
        report = asyncio.run(
            verify_and_reflect(repo, "Where is this?", "The function is in the source file.", evidence, ollama, AgentSettings())
        )
        assert report.reflection_attempted
        assert report.reflection_error == expected
        assert report.safe_to_display is False
        assert "couldn't safely verify" in report.final_answer
        assert len(ollama.messages) == 1


def test_reflection_invented_ambiguous_claims_are_rejected_without_rewrite(repo: RootContext) -> None:
    evidence = file_evidence("src/main file.py", 1, 2)
    answer = "A repeated unsupported claim. A repeated unsupported claim."
    ollama = FakeOllama([_reflection({"claim": "invented claim", "reason": "unsupported"})])

    report = asyncio.run(
        verify_and_reflect(repo, "Repository question", answer, evidence, ollama, AgentSettings())
    )

    assert report.reflection_error == "reflection_claim_mapping_failed"
    assert report.final_answer.startswith("I couldn't safely verify")
    assert len(ollama.messages) == 1


def test_general_question_does_not_trigger_reflection_even_with_no_citations(repo: RootContext) -> None:
    ollama = FakeOllama([])

    report = asyncio.run(
        verify_and_reflect(repo, "What is a pull request?", "A proposed change for review.", (), ollama, AgentSettings())
    )

    assert report.safe_to_display
    assert report.final_answer == "A proposed change for review."
    assert report.reflection_attempted is False
    assert ollama.messages == []


def test_repository_question_without_evidence_or_citations_fails_closed(repo: RootContext) -> None:
    ollama = FakeOllama([_reflection({"claim": "The function exists.", "reason": "No evidence."})])

    report = asyncio.run(
        verify_and_reflect(
            repo,
            "Where is the main function?",
            "The function is in src/main.py.",
            (),
            ollama,
            AgentSettings(),
        )
    )

    assert report.safe_to_display is False
    assert "couldn't safely verify" in report.final_answer
    assert report.reflection_attempted
    assert "repository_answer_has_no_verifiable_citation" in report.verification_errors


def test_duplicate_reflection_json_keys_are_rejected(repo: RootContext) -> None:
    evidence = file_evidence("src/main file.py", 1, 1)
    answer = "Supported at `src/main file.py:1`."
    ollama = FakeOllama(['{"unsupported_claims":[],"unsupported_claims":[{}]}'])

    report = asyncio.run(
        verify_and_reflect(repo, "Find it", answer, evidence, ollama, AgentSettings())
    )

    assert report.reflection_error == "reflection_invalid_json"
    assert report.safe_to_display
    assert report.final_answer == answer


def test_verification_exception_never_returns_original_answer(repo: RootContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(verify_module, "extract_citations", lambda answer: (_ for _ in ()).throw(RuntimeError("boom")))

    report = verify_answer(repo, "Secret unsupported statement.", ())

    assert report.safe_to_display is False
    assert report.final_answer != "Secret unsupported statement."
    assert report.verification_errors == ("verification_internal_error",)


def test_commit_is_checked_once_across_reflection_and_final_reverification(
    repo: RootContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit_hash = git(repo.path, "rev-parse", "HEAD").decode().strip()
    calls: list[str] = []

    def exists(context: RootContext, value: str) -> bool:
        del context
        calls.append(value)
        return True

    monkeypatch.setattr(verify_module.gitops, "commit_exists", exists)
    ollama = FakeOllama([_reflection()])
    report = asyncio.run(
        verify_and_reflect(
            repo,
            "What changed?",
            f"Changed in commit {commit_hash}.",
            commit_evidence(commit_hash),
            ollama,
            AgentSettings(),
        )
    )

    assert report.safe_to_display
    assert calls == [commit_hash]


def test_cli_agent_final_path_verifies_before_return_and_records_report(
    repo: RootContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeMcp:
        async def list_tools(self, *, cursor: str | None = None) -> Any:
            del cursor
            schema = {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            }
            return type("Page", (), {"tools": [type("Tool", (), {
                "name": "read_file", "description": "read", "input_schema": schema
            })()], "next_cursor": None})()

        async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
            assert name == "read_file"
            assert arguments == {"path": "src/main file.py"}
            return type("Result", (), {
                "structured_content": {
                    "path": "src/main file.py",
                    "start_line": 1,
                    "end_line": 2,
                    "total_lines": 4,
                    "lines": [{"number": 1, "text": "def answer():"}, {"number": 2, "text": "return"}],
                },
                "content": [],
                "is_error": False,
            })()

    @contextlib.asynccontextmanager
    async def fake_client(parameters: Any):
        assert parameters.command
        yield FakeMcp()

    monkeypatch.setattr(agent_module, "Client", fake_client)
    ollama = FakeOllama(
        [
            json.dumps({"action": "read_file", "args": {"path": "src/main file.py"}}),
            json.dumps({"action": "final", "answer": "The function is here: `src/main file.py:1`."}),
            _reflection(),
        ]
    )

    result = asyncio.run(
        agent_module._run_turn_with_server(
            repo,
            ollama,
            "Where is the function?",
            AgentSettings(),
        )
    )

    assert result.answer == "The function is here: `src/main file.py:1`."
    assert result.verification_report is not None
    assert result.verification_report.safe_to_display
    assert result.verification_report.citation_validity_rate_before == 1.0
    assert result.verification_report.citation_validity_rate_after == 1.0
    assert result.verification_report.reflection_attempted
    assert len(ollama.messages) == 3
