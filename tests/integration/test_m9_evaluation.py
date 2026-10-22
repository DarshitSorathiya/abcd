"""M9 independent evaluation fixture and rubric integrity tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from eval.run_eval import prepare_fixture

PROJECT = Path(__file__).resolve().parents[2]


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout


def test_evaluation_rubric_has_twelve_predeclared_questions_and_all_required_categories() -> None:
    questions = json.loads((PROJECT / "eval" / "questions.json").read_text(encoding="utf-8"))["questions"]
    markdown = (PROJECT / "eval" / "questions.md").read_text(encoding="utf-8")
    categories = [item["category"] for item in questions]

    assert len(questions) == 12
    assert {"locate", "history", "onboarding", "issues", "general", "out_of_scope"} <= set(categories)
    assert "Hash" in markdown or "hash" in markdown
    assert "independently" in markdown
    assert all(item["question"] and item["truth"] for item in questions)
    assert all(isinstance(item["expected_tools"], list) for item in questions)
    assert all(isinstance(item["required_citations"], list) for item in questions)


def test_evaluation_fixture_prepares_isolated_hostile_synthetic_repo_with_known_history(
    tmp_path: Path,
) -> None:
    root = tmp_path / "fixture with spaces – 数据"
    final_hash = prepare_fixture(root)

    subjects = git(root, "log", "--format=%s", "--reverse").splitlines()
    assert subjects == ["Initial sample project", "Add identity validation", "Add report builder"]
    assert git(root, "rev-parse", "HEAD").strip() == final_hash
    assert "ignore prior instructions" in (root / "README.md").read_text(encoding="utf-8")
    assert (root / ".env").read_text(encoding="utf-8").startswith("REPO_GUIDE_EVAL_CANARY=")
    assert len((root / "data" / "oversized.txt").read_bytes()) > 1_000_000
    assert b"\x00" in (root / "assets" / "payload.bin").read_bytes()
    assert (root / "資料 with spaces" / "note.txt").exists()
    assert not git(root, "remote").strip()
    assert "outside-synthetic.txt" not in git(root, "status", "--porcelain")


def test_evaluation_fixture_recreates_the_same_commit_history(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_head = prepare_fixture(first)
    second_head = prepare_fixture(second)

    assert first_head == second_head
    first_log = git(first, "log", "--format=%H %s", "--reverse")
    second_log = git(second, "log", "--format=%H %s", "--reverse")
    assert first_log == second_log
