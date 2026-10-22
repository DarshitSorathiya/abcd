"""Run the pre-grounded question set against an installed local Ollama model."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from repo_guide import __version__
from repo_guide.agent import run_question
from repo_guide.config import DEFAULT_OLLAMA_BASE_URL, DEFAULT_OLLAMA_MODEL, AgentSettings
from repo_guide.errors import AgentError
from repo_guide.ollama_client import OllamaClient
from repo_guide.root import resolve_root

_PROJECT = Path(__file__).resolve().parents[1]
_QUESTIONS = _PROJECT / "eval" / "questions.json"
_FIXTURE = _PROJECT / "eval" / "fixture"
_FIXED_DATES = (
    "2026-10-19T12:00:00+0000",
    "2026-10-20T12:00:00+0000",
    "2026-10-21T12:00:00+0000",
)
_COMMITS = (
    ("Initial sample project", ("README.md", "pyproject.toml", "src/repo_guide/__init__.py", "src/repo_guide/config.py", "src/repo_guide/errors.py")),
    ("Add identity validation", ("src/repo_guide/auth.py",)),
    ("Add report builder", ("docs/SETUP.md", ".env", "src/repo_guide/misleading.py", "src/repo_guide/report.py")),
)


def prepare_fixture(destination: Path) -> str:
    """Create the synthetic repository with known, ordered local history."""
    shutil.copytree(_FIXTURE, destination)
    subprocess.run(["git", "-C", str(destination), "init", "--quiet"], check=True, shell=False)
    for index, (subject, paths) in enumerate(_COMMITS):
        subprocess.run(["git", "-C", str(destination), "add", "--", *paths], check=True, shell=False)
        date = _FIXED_DATES[index]
        environment = {
            **os.environ,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "Repo Guide Evaluation",
            "GIT_AUTHOR_EMAIL": "evaluation@example.invalid",
            "GIT_COMMITTER_NAME": "Repo Guide Evaluation",
            "GIT_COMMITTER_EMAIL": "evaluation@example.invalid",
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_DATE": date,
        }
        subprocess.run(
            ["git", "-C", str(destination), "-c", "core.hooksPath=/dev/null", "commit", "--quiet", "-m", subject],
            check=True,
            shell=False,
            env=environment,
        )
        (destination / "assets").mkdir(exist_ok=True)
        (destination / "assets" / "payload.bin").write_bytes(b"\x00\x01synthetic-binary")
        (destination / "data").mkdir(exist_ok=True)
        (destination / "data" / "oversized.txt").write_text("x" * 1_100_000, encoding="utf-8")
        (destination / "資料 with spaces").mkdir(exist_ok=True)
        (destination / "資料 with spaces" / "note.txt").write_text("synthetic unicode path\n", encoding="utf-8")
        outside_target = destination.parent / "outside-synthetic.txt"
        outside_target.write_text("synthetic outside canary", encoding="utf-8")
        try:
            (destination / "escape-link.txt").symlink_to(outside_target)
        except OSError:
            # Symlink behavior is additionally exercised by platform-marked security tests.
            pass
    return subprocess.run(
        ["git", "-C", str(destination), "rev-parse", "HEAD"],
        check=True,
        shell=False,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _tool_names(evidence: tuple[dict[str, Any], ...]) -> list[str]:
    return [
        str(item["tool"])
        for item in evidence
        if item.get("tool") not in {"agent_validation", "agent_guard"}
    ]


def _contains_expected(answer: str, terms: list[str]) -> bool:
    folded = answer.casefold()
    return all(term.casefold() in folded for term in terms)


def _tool_decisions(expected: list[str], actual: list[str]) -> tuple[int, int]:
    """Score ordered tool choices; an empty expected/actual pair is one direct-answer decision."""
    if not expected and not actual:
        return 1, 1
    scored = max(len(expected), len(actual))
    correct = sum(
        expected[index] == actual[index]
        for index in range(min(len(expected), len(actual)))
    )
    return correct, scored


def _run_one(context: Any, question: str, settings: AgentSettings) -> dict[str, Any]:
    start = time.perf_counter()
    ollama = OllamaClient(settings)
    try:
        result = asyncio.run(run_question(context, ollama, question, settings))
        elapsed_ms = (time.perf_counter() - start) * 1000
        report = result.verification_report
        return {
            "answer": result.answer,
            "tools_called": _tool_names(result.evidence),
            "steps": result.steps,
            "incomplete": result.incomplete,
            "latency_ms": round(elapsed_ms, 2),
            "citation_total_before": report.total_extracted_citations if report else None,
            "citation_valid_before": report.valid_citations_before_sanitization if report else None,
            "citation_rate_before": report.citation_validity_rate_before if report else None,
            "citation_total_after": report.citations_checked_after_sanitization if report else None,
            "citation_valid_after": report.valid_citations_after_sanitization if report else None,
            "citation_rate_after": report.citation_validity_rate_after if report else None,
            "verification_safe": report.safe_to_display if report else None,
            "verification_errors": list(report.verification_errors) if report else [],
            "failure_category": None,
        }
    except AgentError as exc:
        return {
            "answer": "",
            "tools_called": [],
            "steps": 0,
            "incomplete": True,
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            "citation_total_before": None,
            "citation_valid_before": None,
            "citation_rate_before": None,
            "citation_total_after": None,
            "citation_valid_after": None,
            "citation_rate_after": None,
            "verification_safe": False,
            "verification_errors": [exc.code],
            "failure_category": _failure_category(exc.code),
        }
    except Exception:
        return {
            "answer": "",
            "tools_called": [],
            "steps": 0,
            "incomplete": True,
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            "citation_total_before": None,
            "citation_valid_before": None,
            "citation_rate_before": None,
            "citation_total_after": None,
            "citation_valid_after": None,
            "citation_rate_after": None,
            "verification_safe": False,
            "verification_errors": ["evaluation_operational_error"],
            "failure_category": "operational failure",
        }
    finally:
        ollama.close()


def _failure_category(code: str) -> str:
    if code.startswith("ollama"):
        return "Ollama failure"
    if code.startswith("git") or code.startswith("github"):
        return "GitHub API failure" if code.startswith("github") else "MCP/repository operational failure"
    if code.startswith("reflection") or code.startswith("verification"):
        return "verification or sanitization defect"
    if code.startswith("mcp"):
        return "MCP transport failure"
    return "invalid model response or agent action"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Repo Guide's fixed-ground-truth local model evaluation.")
    parser.add_argument("--model", default=os.environ.get("REPO_GUIDE_MODEL", DEFAULT_OLLAMA_MODEL))
    parser.add_argument("--ollama-url", default=os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL))
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--output", type=Path, help="optional JSON results output path")
    args = parser.parse_args()
    settings = AgentSettings(model=args.model, ollama_base_url=args.ollama_url, max_steps=args.max_steps)
    questions: dict[str, Any] = json.loads(_QUESTIONS.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="repo-guide-eval-") as temporary:
        fixture_path = Path(temporary) / "fixture with spaces – 数据"
        head = prepare_fixture(fixture_path)
        context = resolve_root(fixture_path, environ={}, home=Path(temporary) / "other-home")
        for case in questions["questions"]:
            observation = _run_one(context, case["question"], settings)
            expected_terms = case["required_terms"]
            decisions_correct, decisions_scored = _tool_decisions(
                case["expected_tools"], observation["tools_called"]
            )
            answer_ok = _contains_expected(observation["answer"], expected_terms)
            required_citations_ok = all(
                citation in observation["answer"] for citation in case["required_citations"]
            )
            records.append(
                {
                    "id": case["id"],
                    "category": case["category"],
                    "expected_behavior": case["truth"],
                    "tools_called": observation["tools_called"],
                    "tool_decisions_correct": decisions_correct,
                    "tool_decisions_scored": decisions_scored,
                    "answer_correct_by_required_terms": answer_ok,
                    "required_citation_styles_present": required_citations_ok,
                    "answer": observation["answer"],
                    **{key: value for key, value in observation.items() if key not in {"tools_called", "answer"}},
                }
            )

    scored_decisions = sum(int(item["tool_decisions_scored"]) for item in records)
    correct_decisions = sum(int(item["tool_decisions_correct"]) for item in records)
    answer_correct = sum(bool(item["answer_correct_by_required_terms"]) for item in records)
    before_total = sum(item["citation_total_before"] or 0 for item in records)
    before_valid = sum(item["citation_valid_before"] or 0 for item in records)
    after_total = sum(item["citation_total_after"] or 0 for item in records)
    after_valid = sum(item["citation_valid_after"] or 0 for item in records)
    latencies = sorted(float(item["latency_ms"]) for item in records)
    metrics = {
        "questions_total": len(records),
        "tool_decisions_scored": scored_decisions,
        "tool_decisions_correct": correct_decisions,
        "tool_selection_accuracy": correct_decisions / scored_decisions if scored_decisions else None,
        "tool_selection_definition": "correct ordered tool/no-tool decisions divided by max(expected, actual) decision slots per question; empty expected and actual lists count as one correct direct-answer decision",
        "answer_correct_by_required_terms": answer_correct,
        "required_term_coverage_proxy": answer_correct / len(records) if records else None,
        "manual_answer_correctness": None,
        "manual_answer_correctness_note": "Must be scored independently by reviewing each answer against eval/questions.md; automated term coverage is only a proxy.",
                "required_citation_style_matches": sum(
                    bool(record["required_citation_styles_present"]) for record in records
                ),
        "citation_validity_before": before_valid / before_total if before_total else None,
        "citation_validity_after": after_valid / after_total if after_total else None,
        "citation_denominator_before": before_total,
        "citation_denominator_after": after_total,
        "median_latency_ms": _median(latencies),
        "p95_latency_ms": _percentile(latencies, 0.95),
        "failure_count": sum(item["failure_category"] is not None for item in records),
        "model": settings.model,
        "application_version": __version__,
        "fixture_head": head,
        "date_utc": datetime.now(UTC).isoformat(),
        "ollama_version": _ollama_version(),
    }
    result = {"metrics": metrics, "questions": records}
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    middle = len(values) // 2
    if len(values) % 2:
        return round(values[middle], 2)
    return round((values[middle - 1] + values[middle]) / 2, 2)


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    rank = max(1, int((len(values) * quantile) + 0.999999))
    return round(values[min(rank, len(values)) - 1], 2)


def _ollama_version() -> str | None:
    executable = shutil.which("ollama")
    if executable is None:
        return None
    try:
        result = subprocess.run(
            [executable, "--version"],
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (result.stdout or result.stderr).decode("utf-8", errors="replace").strip()
    return text[:200] if result.returncode == 0 and text else None


if __name__ == "__main__":
    raise SystemExit(main())
