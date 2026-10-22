"""Bounded synchronous client for Ollama's local ``/api/chat`` endpoint."""

from __future__ import annotations

import ipaddress
import json
from typing import Any, Protocol, cast
from urllib.parse import urlsplit

import requests
from requests.exceptions import SSLError

from repo_guide.config import AgentSettings
from repo_guide.errors import AgentError


class _Response(Protocol):
    status_code: int
    headers: Any

    def iter_content(self, chunk_size: int) -> Any: ...

    def close(self) -> None: ...


class _Session(Protocol):
    def post(self, url: str, **kwargs: Any) -> _Response: ...

    def close(self) -> None: ...


class OllamaClient:
    """POST bounded chat requests to one validated Ollama endpoint.

    Construction performs no I/O. Remote endpoints require explicit opt-in;
    redirects, environment proxies, credentials, and oversized bodies are refused.
    """

    def __init__(self, settings: AgentSettings, *, session: _Session | None = None) -> None:
        self.settings = settings
        self._url = _validated_chat_url(settings.ollama_base_url, settings.allow_remote_ollama)
        self._session = session if session is not None else _new_session()
        self._owns_session = session is None

    def chat(self, messages: list[dict[str, str]], *, temperature: float | None = None) -> str:
        """Return assistant text or raise a safe ``AgentError``."""
        options: dict[str, int | float] = {"num_predict": self.settings.max_output_tokens}
        if temperature is not None:
            if not 0 <= temperature <= 2:
                raise AgentError("invalid_temperature", "temperature must be between 0 and 2")
            options["temperature"] = temperature
        request_body = {
            "model": self.settings.model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": options,
        }
        encoded_request = json.dumps(request_body, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        if len(encoded_request) > self.settings.max_request_bytes:
            raise AgentError("ollama_request_too_large", "Ollama request exceeded the configured size limit")

        try:
            response = self._session.post(
                self._url,
                json=request_body,
                headers={"Content-Type": "application/json"},
                timeout=(self.settings.connect_timeout_seconds, self.settings.read_timeout_seconds),
                allow_redirects=False,
                verify=True,
                stream=True,
            )
        except SSLError as exc:
            raise AgentError("ollama_tls_error", "TLS verification for Ollama failed") from exc
        except requests.Timeout as exc:
            raise AgentError("ollama_timeout", "Ollama did not respond within the configured timeout") from exc
        except requests.RequestException as exc:
            raise AgentError(
                "ollama_unavailable",
                "Ollama is unavailable; start the local service and verify its configured URL",
            ) from exc

        with _closing_response(response):
            if response.status_code in {301, 302, 303, 307, 308}:
                raise AgentError("ollama_redirect_denied", "Ollama endpoint redirects are not followed")
            body = _read_response(response, self.settings.max_response_bytes)
            if response.status_code == 404:
                raise AgentError(
                    "ollama_model_missing",
                    f"Ollama could not find model {self.settings.model!r}; install that model locally first",
                )
            if response.status_code < 200 or response.status_code >= 300:
                code = "ollama_model_missing" if _response_mentions_missing_model(body) else "ollama_http_error"
                message = (
                    f"Ollama could not find model {self.settings.model!r}; install that model locally first"
                    if code == "ollama_model_missing"
                    else f"Ollama returned HTTP {response.status_code}"
                )
                raise AgentError(code, message)
            try:
                payload: Any = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise AgentError("ollama_invalid_response", "Ollama returned malformed JSON") from exc
            if not isinstance(payload, dict):
                raise AgentError("ollama_invalid_response", "Ollama returned an unexpected response")
            payload_object = cast(dict[str, Any], payload)
            raw_message = payload_object.get("message")
            if not isinstance(raw_message, dict):
                raise AgentError("ollama_invalid_response", "Ollama response omitted assistant content")
            message = cast(dict[str, Any], raw_message)
            raw_content = message.get("content")
            if not isinstance(raw_content, str):
                raise AgentError("ollama_invalid_response", "Ollama response omitted assistant content")
            content = raw_content.strip()
            if not content:
                raise AgentError("ollama_empty_response", "Ollama returned an empty assistant response")
            if len(content.encode("utf-8")) > self.settings.max_response_bytes:
                raise AgentError("ollama_response_too_large", "Ollama response exceeded the configured size limit")
            return content

    def close(self) -> None:
        """Close the owned HTTP session, if any."""
        if self._owns_session:
            self._session.close()

    def __enter__(self) -> OllamaClient:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback
        self.close()


def _validated_chat_url(base_url: str, allow_remote: bool) -> str:
    try:
        parsed = urlsplit(base_url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise AgentError("invalid_ollama_url", "configured Ollama URL is malformed") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise AgentError("invalid_ollama_url", "Ollama URL must be an origin without credentials or path")

    local = hostname.casefold() == "localhost"
    try:
        local = local or ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        pass
    if local:
        if parsed.scheme != "http":
            raise AgentError("invalid_ollama_url", "loopback Ollama endpoint must use HTTP")
    elif not allow_remote or parsed.scheme != "https":
        raise AgentError(
            "remote_ollama_not_allowed",
            "remote Ollama requires explicit opt-in and an HTTPS endpoint",
        )
    if port is not None and not 1 <= port <= 65_535:
        raise AgentError("invalid_ollama_url", "Ollama port is invalid")
    return f"{parsed.scheme}://{parsed.netloc}/api/chat"


def _new_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    return session


def _read_response(response: _Response, limit: int) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            if int(content_length) > limit:
                raise AgentError("ollama_response_too_large", "Ollama response exceeded the configured size limit")
        except ValueError as exc:
            raise AgentError("ollama_invalid_response", "Ollama returned an invalid content length") from exc
    chunks: list[bytes] = []
    size = 0
    try:
        for chunk in response.iter_content(chunk_size=16_384):
            if not chunk:
                continue
            size += len(chunk)
            if size > limit:
                raise AgentError(
                    "ollama_response_too_large", "Ollama response exceeded the configured size limit"
                )
            chunks.append(chunk)
    except AgentError:
        raise
    except requests.Timeout as exc:
        raise AgentError("ollama_timeout", "Ollama response timed out") from exc
    except requests.RequestException as exc:
        raise AgentError("ollama_unavailable", "Ollama response could not be read") from exc
    return b"".join(chunks)


def _response_mentions_missing_model(body: bytes) -> bool:
    try:
        payload: Any = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    error = cast(dict[str, Any], payload).get("error")
    return isinstance(error, str) and "model" in error.casefold() and "not found" in error.casefold()


class _closing_response:
    """Close streamed HTTP responses on every result and failure path."""

    def __init__(self, response: _Response) -> None:
        self.response = response

    def __enter__(self) -> _Response:
        return self.response

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        del _exc_type, _exc, _traceback
        self.response.close()
