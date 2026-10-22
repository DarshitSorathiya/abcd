"""Validated, immutable resource limits for repository operations."""

from __future__ import annotations

from dataclasses import dataclass

from repo_guide.errors import ConfigurationError

DEFAULT_OLLAMA_MODEL = "qwen3:8b"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"


@dataclass(frozen=True, slots=True)
class AgentSettings:
    """Local agent limits and Ollama endpoint configuration."""

    model: str = DEFAULT_OLLAMA_MODEL
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    allow_remote_ollama: bool = False
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 120.0
    max_request_bytes: int = 256_000
    max_response_bytes: int = 256_000
    max_output_tokens: int = 1_024
    max_observation_chars: int = 8_000
    max_context_chars: int = 24_000
    max_steps: int = 8
    tool_timeout_seconds: float = 30.0
    max_tools: int = 64

    def __post_init__(self) -> None:
        if not self.model or len(self.model) > 200:
            raise ConfigurationError("invalid_model", "model name must contain 1 to 200 characters")
        if not self.ollama_base_url:
            raise ConfigurationError("invalid_ollama_url", "Ollama base URL is required")
        if self.connect_timeout_seconds <= 0 or self.read_timeout_seconds <= 0:
            raise ConfigurationError("invalid_limit", "Ollama timeouts must be positive")
        if min(
            self.max_request_bytes,
            self.max_response_bytes,
            self.max_output_tokens,
            self.max_observation_chars,
            self.max_context_chars,
            self.max_steps,
            self.tool_timeout_seconds,
            self.max_tools,
        ) <= 0:
            raise ConfigurationError("invalid_limit", "agent limits must be positive")
        if self.max_steps > 32 or self.max_tools > 256:
            raise ConfigurationError("invalid_limit", "agent step or tool cap is too large")


@dataclass(frozen=True, slots=True)
class SafetyLimits:
    """Conservative caps shared by file and subprocess operations."""

    max_file_bytes: int = 1_000_000
    max_file_lines: int = 200
    max_subprocess_output_bytes: int = 1_000_000
    subprocess_timeout_seconds: float = 5.0
    max_tree_entries: int = 100
    max_search_results: int = 10
    max_log_commits: int = 50
    max_search_query_chars: int = 100
    max_http_timeout_seconds: float = 20.0
    max_http_response_bytes: int = 1_000_000
    max_http_retries: int = 2
    max_issues: int = 10

    def __post_init__(self) -> None:
        if self.max_file_bytes <= 0:
            raise ConfigurationError("invalid_limit", "max_file_bytes must be positive")
        if self.max_file_lines <= 0:
            raise ConfigurationError("invalid_limit", "max_file_lines must be positive")
        if self.max_subprocess_output_bytes <= 0:
            raise ConfigurationError(
                "invalid_limit", "max_subprocess_output_bytes must be positive"
            )
        if self.subprocess_timeout_seconds <= 0:
            raise ConfigurationError(
                "invalid_limit", "subprocess_timeout_seconds must be positive"
            )
        if self.max_tree_entries <= 0:
            raise ConfigurationError("invalid_limit", "max_tree_entries must be positive")
        if self.max_search_results <= 0:
            raise ConfigurationError("invalid_limit", "max_search_results must be positive")
        if self.max_log_commits <= 0:
            raise ConfigurationError("invalid_limit", "max_log_commits must be positive")
        if self.max_search_query_chars <= 0:
            raise ConfigurationError("invalid_limit", "max_search_query_chars must be positive")
        if not 0 < self.max_http_timeout_seconds <= 20:
            raise ConfigurationError(
                "invalid_limit", "max_http_timeout_seconds must be between 0 and 20"
            )
        if self.max_http_response_bytes <= 0:
            raise ConfigurationError("invalid_limit", "max_http_response_bytes must be positive")
        if not 0 <= self.max_http_retries <= 3:
            raise ConfigurationError("invalid_limit", "max_http_retries must be between 0 and 3")
        if not 1 <= self.max_issues <= 10:
            raise ConfigurationError("invalid_limit", "max_issues must be between 1 and 10")