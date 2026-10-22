"""Minimal package metadata and console-entry-point smoke coverage."""

from importlib.metadata import distribution

import repo_guide


def test_package_version_is_available() -> None:
    assert repo_guide.__version__ == "0.1.0"


def test_both_console_scripts_are_registered() -> None:
    scripts = {entry_point.name for entry_point in distribution("repo-guide").entry_points}

    assert {"repo-guide", "repo-guide-mcp"} <= scripts
