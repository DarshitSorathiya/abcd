"""Synthetic identity-input validation; no secrets are stored here."""

from repo_guide.errors import GuideError


def validate_identity(identity: str) -> str:
    """Reject blank or overlong identities before report generation."""
    candidate = identity.strip()
    if not candidate:
        raise GuideError("identity is required")
    if len(candidate) > 80:
        raise GuideError("identity is too long")
    return candidate
