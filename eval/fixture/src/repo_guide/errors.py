"""Application-specific errors for the synthetic sample."""


class GuideError(Exception):
    """An actionable error raised by report operations."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
