"""Configuration loading for the synthetic evaluation package."""

DEFAULTS = {"title": "Daily report", "max_items": 20}


def load_settings(environment: dict[str, str]) -> dict[str, str | int]:
    """Load supported settings, preserving defaults when values are absent."""
    settings = DEFAULTS.copy()
    if "REPORT_TITLE" in environment:
        settings["title"] = environment["REPORT_TITLE"]
    return settings
