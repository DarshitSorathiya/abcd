"""Safe, structured errors shared by repository safety code."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(eq=False)
class RepoGuideError(Exception):
    """An actionable error that is safe to return to an MCP client."""

    code: str
    message: str

    def __str__(self) -> str:
        return self.message

    def as_dict(self) -> dict[str, dict[str, str]]:
        """Return a stable structured representation without internal details."""
        return {"error": {"code": self.code, "message": self.message}}


class RootResolutionError(RepoGuideError):
    """The configured root could not be safely resolved."""


class PathPolicyError(RepoGuideError):
    """A requested repository path violates path or file policy."""


class ConfigurationError(RepoGuideError):
    """A safety limit is invalid."""


class AgentError(RepoGuideError):
    """A safe Ollama, MCP-agent, or action-validation failure."""