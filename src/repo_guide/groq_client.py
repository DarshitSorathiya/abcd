"""Bounded synchronous client for Groq's hosted OpenAI-compatible chat API."""

from __future__ import annotations

import json
from typing import Any, Protocol, cast

import requests
from requests.exceptions import SSLError

from repo_guide.config import AgentSettings
from repo_guide.errors import AgentError

_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


class _Response(Protocol):
    status_code: int
    headers: Any

    def iter_content(self, chunk_size: int) -> Any: ...

    def close(self) -> None: ...


class _Session(Protocol):
    def post(self, url: str, **kwargs: Any) -> _Response: ...

    def close(self) -> None: ...


class GroqClient:
    """Send bounded chat requests to Groq using an explicit API key."""

    provider = "groq"

    def __init__(
        self,
        settings: AgentSettings,
        api_key: str,
        *,
        session: _Session | None = None,
    ) -> None:
        api_key = api_key.strip()
        if not api_key:
            raise AgentError("groq_api_key_missing", "GROQ_API_KEY must not be empty")
        if len(api_key) > 4_096 or "\r" in api_key or "\n" in api_key:
            raise AgentError("groq_api_key_invalid", "GROQ_API_KEY is invalid")
        self.settings = settings
        self._api_key = api_key
        self._session = session if session is not None else _new_session()
        self._owns_session = session is None

    def chat(self, messages: list[dict[str, str]], *, temperature: float | None = None) -> str:
        """Return assistant text or raise a safe ``AgentError``."""
        if temperature is not None and not 0 <= temperature <= 2:
            raise AgentError("invalid_temperature", "temperature must be between 0 and 2")
        request_body: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "max_completion_tokens": self.settings.max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        if temperature is not None:
            request_body["temperature"] = temperature
        encoded_request = json.dumps(
            request_body, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        if len(encoded_request) > self.settings.max_request_bytes:
            raise AgentError(
                "groq_request_too_large", "Groq request exceeded the configured size limit"
            )

        try:
            response = self._session.post(
                _CHAT_URL,
                json=request_body,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=(self.settings.connect_timeout_seconds, self.settings.read_timeout_seconds),
                allow_redirects=False,
                verify=True,
                stream=True,
            )
        except SSLError as exc:
            raise AgentError("groq_tls_error", "TLS verification for Groq failed") from exc
        except requests.Timeout as exc:
            raise AgentError(
                "groq_timeout", "Groq did not respond within the configured timeout"
            ) from exc
        except requests.RequestException as exc:
            raise AgentError(
                "groq_unavailable", "Groq is unavailable; verify the network connection"
            ) from exc

        with _closing_response(response):
            if response.status_code in {301, 302, 303, 307, 308}:
                raise AgentError("groq_redirect_denied", "Groq endpoint redirects are not followed")
            body = _read_response(response, self.settings.max_response_bytes)
            if response.status_code < 200 or response.status_code >= 300:
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "")
                    if retry_after.isdigit():
                        message = (
                            "Groq rate limit reached (HTTP 429); retry after "
                            f"{int(retry_after)} seconds."
                        )
                    else:
                        message = (
                            "Groq rate limit reached (HTTP 429); wait before retrying."
                        )
                    detail = _error_detail(body, self._api_key)
                    if detail is not None:
                        message += f" Provider detail: {detail}"
                    rate_headers = _rate_limit_headers(response.headers)
                    if rate_headers:
                        message += f" Rate-limit headers: {rate_headers}."
                    else:
                        message += " Check the model's organization-level limits."
                    raise AgentError("groq_rate_limited", message)
                if response.status_code == 413:
                    raise AgentError(
                        "groq_request_too_large",
                        "Groq rejected the request as too large (HTTP 413); reduce the question "
                        "or repository context.",
                    )
                if response.status_code == 400:
                    detail = _error_detail(body, self._api_key)
                    message = "Groq rejected the request (HTTP 400)"
                    if detail is not None:
                        message += f": {detail}"
                    else:
                        message += "; check the selected model and supported request parameters."
                    raise AgentError("groq_http_error", message)
                raise AgentError("groq_http_error", f"Groq returned HTTP {response.status_code}")
            try:
                payload: Any = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise AgentError("groq_invalid_response", "Groq returned malformed JSON") from exc
            if not isinstance(payload, dict):
                raise AgentError("groq_invalid_response", "Groq returned an unexpected response")
            payload_object = cast(dict[str, Any], payload)
            choices = payload_object.get("choices")
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                raise AgentError("groq_invalid_response", "Groq response omitted assistant content")
            choice = cast(dict[str, Any], choices[0])
            raw_message = choice.get("message")
            if not isinstance(raw_message, dict):
                raise AgentError("groq_invalid_response", "Groq response omitted assistant content")
            message = cast(dict[str, Any], raw_message)
            raw_content = message.get("content")
            if not isinstance(raw_content, str):
                raise AgentError("groq_invalid_response", "Groq response omitted assistant content")
            content = raw_content.strip()
            if not content:
                raise AgentError("groq_empty_response", "Groq returned an empty assistant response")
            if len(content.encode("utf-8")) > self.settings.max_response_bytes:
                raise AgentError(
                    "groq_response_too_large", "Groq response exceeded the configured size limit"
                )
            return content

    def close(self) -> None:
        """Close the owned HTTP session, if any."""
        if self._owns_session:
            self._session.close()


def _new_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    return session


def _error_detail(body: bytes, api_key: str) -> str | None:
    try:
        payload: Any = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    payload_object = cast(dict[str, Any], payload)
    error = payload_object.get("error")
    if not isinstance(error, dict):
        return None
    error_object = cast(dict[str, Any], error)
    raw_message = error_object.get("message")
    if not isinstance(raw_message, str):
        return None
    message = raw_message.replace(api_key, "[redacted]")
    message = "".join(character if character.isprintable() else " " for character in message)
    message = " ".join(message.split())
    if not message:
        return None
    return message[:240]


def _rate_limit_headers(headers: Any) -> str:
    labels = (
        ("x-ratelimit-remaining-requests", "remaining requests (daily)"),
        ("x-ratelimit-reset-requests", "request reset"),
        ("x-ratelimit-remaining-tokens", "remaining tokens (per minute)"),
        ("x-ratelimit-reset-tokens", "token reset"),
    )
    values: list[str] = []
    for name, label in labels:
        value = headers.get(name)
        if isinstance(value, str) and value:
            clean_value = "".join(
                character if character.isprintable() else " " for character in value
            )
            clean_value = " ".join(clean_value.split())[:48]
            if clean_value:
                values.append(f"{label}={clean_value}")
    return "; ".join(values)


def _read_response(response: _Response, limit: int) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            if int(content_length) > limit:
                raise AgentError(
                    "groq_response_too_large", "Groq response exceeded the configured size limit"
                )
        except ValueError as exc:
            raise AgentError(
                "groq_invalid_response", "Groq returned an invalid content length"
            ) from exc
    chunks: list[bytes] = []
    size = 0
    try:
        for chunk in response.iter_content(chunk_size=16_384):
            if not chunk:
                continue
            size += len(chunk)
            if size > limit:
                raise AgentError(
                    "groq_response_too_large", "Groq response exceeded the configured size limit"
                )
            chunks.append(chunk)
    except AgentError:
        raise
    except requests.Timeout as exc:
        raise AgentError("groq_timeout", "Groq response timed out") from exc
    except requests.RequestException as exc:
        raise AgentError("groq_unavailable", "Groq response could not be read") from exc
    return b"".join(chunks)


class _closing_response:
    """Close streamed HTTP responses on every result and failure path."""

    def __init__(self, response: _Response) -> None:
        self.response = response

    def __enter__(self) -> _Response:
        return self.response

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        del _exc_type, _exc, _traceback
        self.response.close()
