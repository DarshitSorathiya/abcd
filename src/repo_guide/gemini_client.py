"""Bounded synchronous client for Google's streamed Gemini API."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, Protocol, cast
from urllib.parse import quote

import requests
from requests.exceptions import SSLError

from repo_guide.config import AgentSettings
from repo_guide.errors import AgentError

_API_ORIGIN = "https://generativelanguage.googleapis.com/v1beta/models/"
_MODEL_PATTERN = re.compile(r"gemini-[A-Za-z0-9._-]{1,180}\Z")


class _Response(Protocol):
    status_code: int
    headers: Any

    def iter_content(self, chunk_size: int) -> Any: ...

    def close(self) -> None: ...


class _Session(Protocol):
    def post(self, url: str, **kwargs: Any) -> _Response: ...

    def close(self) -> None: ...


class GeminiClient:
    """Send bounded JSON-mode chat requests to the fixed Gemini API endpoint."""

    provider = "gemini"

    def __init__(
        self,
        settings: AgentSettings,
        api_key: str,
        *,
        session: _Session | None = None,
        on_response_chunk: Callable[[], None] | None = None,
    ) -> None:
        api_key = api_key.strip()
        if not api_key:
            raise AgentError("gemini_api_key_missing", "GEMINI_API_KEY must not be empty")
        if len(api_key) > 4_096 or "\r" in api_key or "\n" in api_key:
            raise AgentError("gemini_api_key_invalid", "GEMINI_API_KEY is invalid")
        if not _MODEL_PATTERN.fullmatch(settings.model):
            raise AgentError("gemini_model_invalid", "Gemini model ID has an invalid format")
        self.settings = settings
        self._api_key = api_key
        self._url = f"{_API_ORIGIN}{quote(settings.model, safe='-._')}:streamGenerateContent"
        self._session = session if session is not None else _new_session()
        self._owns_session = session is None
        self._on_response_chunk = on_response_chunk

    def chat(self, messages: list[dict[str, str]], *, temperature: float | None = None) -> str:
        """Return assistant text or raise a safe ``AgentError``."""
        if temperature is not None and not 0 <= temperature <= 2:
            raise AgentError("invalid_temperature", "temperature must be between 0 and 2")
        system_parts: list[dict[str, str]] = []
        contents: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            text = message.get("content")
            if not isinstance(text, str):
                raise AgentError("gemini_invalid_messages", "Gemini messages must contain text")
            if role == "system":
                system_parts.append({"text": text})
            elif role in {"user", "assistant"}:
                contents.append(
                    {
                        "role": "model" if role == "assistant" else "user",
                        "parts": [{"text": text}],
                    }
                )
            else:
                raise AgentError("gemini_invalid_messages", "Gemini message role is unsupported")
        if not contents:
            raise AgentError("gemini_invalid_messages", "Gemini request requires user content")

        request_body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": self.settings.max_output_tokens,
                "responseMimeType": "application/json",
            },
        }
        if self.settings.model.startswith("gemini-3"):
            request_body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "low"}
        if system_parts:
            request_body["systemInstruction"] = {"parts": system_parts}
        if temperature is not None:
            request_body["generationConfig"]["temperature"] = temperature
        encoded_request = json.dumps(
            request_body, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        if len(encoded_request) > self.settings.max_request_bytes:
            raise AgentError(
                "gemini_request_too_large", "Gemini request exceeded the configured size limit"
            )

        try:
            response = self._session.post(
                self._url,
                json=request_body,
                headers={
                    "x-goog-api-key": self._api_key,
                    "Content-Type": "application/json",
                },
                params={"alt": "sse"},
                timeout=(self.settings.connect_timeout_seconds, self.settings.read_timeout_seconds),
                allow_redirects=False,
                verify=True,
                stream=True,
            )
        except SSLError as exc:
            raise AgentError("gemini_tls_error", "TLS verification for Gemini failed") from exc
        except requests.Timeout as exc:
            raise AgentError(
                "gemini_timeout", "Gemini did not respond within the configured timeout"
            ) from exc
        except requests.RequestException as exc:
            raise AgentError(
                "gemini_unavailable", "Gemini is unavailable; verify the network connection"
            ) from exc

        with _closing_response(response):
            if response.status_code in {301, 302, 303, 307, 308}:
                raise AgentError(
                    "gemini_redirect_denied", "Gemini endpoint redirects are not followed"
                )
            if response.status_code < 200 or response.status_code >= 300:
                body = _read_response(response, self.settings.max_response_bytes)
                detail = _error_detail(body, self._api_key)
                message = f"Gemini returned HTTP {response.status_code}"
                if detail is not None:
                    message += f": {detail}"
                raise AgentError("gemini_http_error", message)
            return _read_sse_response(
                response,
                self.settings.max_response_bytes,
                self._api_key,
                on_response_chunk=self._on_response_chunk,
            )

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
    return message[:240] or None


def _read_response(response: _Response, limit: int) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            if int(content_length) > limit:
                raise AgentError(
                    "gemini_response_too_large",
                    "Gemini response exceeded the configured size limit",
                )
        except ValueError as exc:
            raise AgentError(
                "gemini_invalid_response", "Gemini returned an invalid content length"
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
                    "gemini_response_too_large",
                    "Gemini response exceeded the configured size limit",
                )
            chunks.append(chunk)
    except AgentError:
        raise
    except requests.Timeout as exc:
        raise AgentError("gemini_timeout", "Gemini response timed out") from exc
    except requests.RequestException as exc:
        raise AgentError("gemini_unavailable", "Gemini response could not be read") from exc
    return b"".join(chunks)


def _read_sse_response(
    response: _Response,
    limit: int,
    api_key: str,
    *,
    on_response_chunk: Callable[[], None] | None,
) -> str:
    buffer = bytearray()
    data_lines: list[bytes] = []
    text_parts: list[str] = []
    response_size = 0
    result_size = 0
    received_event = False
    notified = False

    def consume_event() -> None:
        nonlocal notified, result_size, received_event
        if not data_lines:
            return
        event = b"\n".join(data_lines)
        data_lines.clear()
        if event == b"[DONE]":
            return
        try:
            payload: Any = json.loads(event)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AgentError(
                "gemini_invalid_response", "Gemini returned malformed streamed JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise AgentError(
                "gemini_invalid_response", "Gemini returned an unexpected streamed response"
            )
        payload_object = cast(dict[str, Any], payload)
        received_event = True
        if not notified and on_response_chunk is not None:
            on_response_chunk()
            notified = True
        error = payload_object.get("error")
        if isinstance(error, dict):
            detail = _error_detail(json.dumps(payload_object).encode("utf-8"), api_key)
            message = "Gemini returned an error in its streamed response"
            if detail is not None:
                message += f": {detail}"
            raise AgentError("gemini_http_error", message)
        raw_candidates = payload_object.get("candidates")
        if not isinstance(raw_candidates, list) or not raw_candidates:
            return
        candidates = cast(list[Any], raw_candidates)
        if not isinstance(candidates[0], dict):
            return
        candidate = cast(dict[str, Any], candidates[0])
        content = candidate.get("content")
        if not isinstance(content, dict):
            return
        content_object = cast(dict[str, Any], content)
        raw_parts = content_object.get("parts")
        if not isinstance(raw_parts, list):
            return
        parts = cast(list[Any], raw_parts)
        for part in parts:
            if not isinstance(part, dict):
                continue
            part_object = cast(dict[str, Any], part)
            part_text = part_object.get("text")
            if isinstance(part_text, str):
                text = part_text
                result_size += len(text.encode("utf-8"))
                if result_size > limit:
                    raise AgentError(
                        "gemini_response_too_large",
                        "Gemini response exceeded the configured size limit",
                    )
                text_parts.append(text)

    try:
        for chunk in response.iter_content(chunk_size=4_096):
            if not chunk:
                continue
            response_size += len(chunk)
            if response_size > limit:
                raise AgentError(
                    "gemini_response_too_large",
                    "Gemini response exceeded the configured size limit",
                )
            buffer.extend(chunk)
            while b"\n" in buffer:
                line, _, remainder = buffer.partition(b"\n")
                buffer = bytearray(remainder)
                line = bytes(line).removesuffix(b"\r")
                if not line:
                    consume_event()
                elif line.startswith(b"data:"):
                    value = line[5:]
                    data_lines.append(value[1:] if value.startswith(b" ") else value)
        if buffer:
            line = bytes(buffer).removesuffix(b"\r")
            if line.startswith(b"data:"):
                value = line[5:]
                data_lines.append(value[1:] if value.startswith(b" ") else value)
        consume_event()
    except AgentError:
        raise
    except requests.Timeout as exc:
        raise AgentError("gemini_timeout", "Gemini response timed out") from exc
    except requests.RequestException as exc:
        raise AgentError("gemini_unavailable", "Gemini response could not be read") from exc

    if not received_event:
        raise AgentError("gemini_invalid_response", "Gemini returned no streamed response events")
    result = "".join(text_parts).strip()
    if not result:
        raise AgentError("gemini_empty_response", "Gemini returned an empty assistant response")
    return result


class _closing_response:
    def __init__(self, response: _Response) -> None:
        self._response = response

    def __enter__(self) -> _Response:
        return self._response

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback
        self._response.close()
