"""Small report builder used by the evaluation fixture."""

from repo_guide.auth import validate_identity


def build_report(identity: str, items: list[str], title: str = "Daily report") -> str:
    """Format a report after validating its identity and bounding item count."""
    name = validate_identity(identity)
    selected = items[:20]
    lines = [f"{title}: {name}"]
    lines.extend(f"- {item}" for item in selected)
    return "\n".join(lines)
