"""Unauthenticated, bounded public GitHub issue discovery."""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Protocol, cast
from urllib.parse import urlsplit

import requests
from requests.exceptions import SSLError

from repo_guide import gitops
from repo_guide.errors import RepoGuideError
from repo_guide.root import Capability, RootContext

_API_ORIGIN = "https://api.github.com"
_API_VERSION = "2022-11-28"
_USER_AGENT = "Repo-Guide/0.1.0 (read-only repository onboarding assistant)"
_CONNECT_TIMEOUT_SECONDS = 5.0
_RETRY_WAIT_CAP_SECONDS = 5.0
_MAX_TITLE_CHARS = 500
_MAX_LABELS_PER_ISSUE = 20
_MAX_LABEL_CHARS = 100
_REMOTE_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


@dataclass(frozen=True, slots=True)
class GitHubRemote:
    """Validated GitHub owner/repository path components."""

    owner: str
    repository: str


@dataclass(frozen=True, slots=True)
class GitHubIssue:
    """Safe issue fields returned to callers; issue bodies are never fetched."""

    number: int
    title: str
    labels: tuple[str, ...]
    html_url: str


@dataclass(frozen=True, slots=True)
class IssueListResult:
    """One bounded page of public issues and primary rate-limit status."""

    issues: tuple[GitHubIssue, ...]
    rate_limit_remaining: int | None
    truncated: bool


class _Response(Protocol):
    status_code: int
    headers: Any

    def iter_content(self, chunk_size: int) -> Any: ...

    def close(self) -> None: ...


class _Session(Protocol):
    def get(self, url: str, **kwargs: Any) -> _Response: ...

    def close(self) -> None: ...


def parse_github_remote(remote_url: str) -> GitHubRemote:
    """Parse common github.com HTTPS, SSH URL, or scp-style remotes safely."""
    if not remote_url or len(remote_url) > 2_048:
        raise RepoGuideError("unsupported_github_remote", "GitHub remote is missing or malformed")
    if any(ord(character) < 32 for character in remote_url) or "%" in remote_url:
        raise RepoGuideError("unsupported_github_remote", "GitHub remote contains invalid path data")

    owner_repo: str
    if remote_url.startswith("https://"):
        try:
            parsed = urlsplit(remote_url)
            valid_authority = (
                parsed.hostname is not None
                and parsed.hostname.casefold() == "github.com"
                and parsed.port in (None, 443)
            )
        except ValueError:
            valid_authority = False
            parsed = urlsplit("https://invalid.invalid")
        if (
            parsed.scheme != "https"
            or not valid_authority
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise RepoGuideError("unsupported_github_remote", "only public github.com remotes are supported")
        owner_repo = parsed.path.removeprefix("/")
    elif remote_url.startswith("ssh://"):
        try:
            parsed = urlsplit(remote_url)
            valid_authority = (
                parsed.hostname is not None
                and parsed.hostname.casefold() == "github.com"
                and parsed.port in (None, 22)
            )
        except ValueError:
            valid_authority = False
            parsed = urlsplit("ssh://invalid@invalid.invalid")
        if (
            parsed.scheme != "ssh"
            or not valid_authority
            or parsed.username != "git"
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise RepoGuideError("unsupported_github_remote", "only standard github.com SSH remotes are supported")
        owner_repo = parsed.path.removeprefix("/")
    elif remote_url.startswith("git@github.com:"):
        owner_repo = remote_url.removeprefix("git@github.com:")
    else:
        raise RepoGuideError("unsupported_github_remote", "only public github.com remotes are supported")

    if owner_repo.endswith(".git"):
        owner_repo = owner_repo[:-4]
    parts = owner_repo.split("/")
    if len(parts) != 2 or any(not _valid_remote_component(part) for part in parts):
        raise RepoGuideError("unsupported_github_remote", "GitHub remote must identify exactly owner/repository")
    return GitHubRemote(parts[0], parts[1])


def discover_github_remote(context: RootContext) -> GitHubRemote:
    """Select origin first, otherwise the first safe configured GitHub remote."""
    context.require_capability(Capability.GITHUB_ISSUES)
    remotes = gitops.configured_remotes(context)
    ordered = sorted(remotes, key=lambda item: (item[0] != "origin", item[0].casefold()))
    for _, remote_url in ordered:
        try:
            return parse_github_remote(remote_url)
        except RepoGuideError:
            continue
    if not remotes:
        raise RepoGuideError("github_remote_missing", "no Git remote is configured for this repository")
    raise RepoGuideError(
        "github_remote_unsupported",
        "no configured Git remote points to a supported public github.com repository",
    )


def list_issues(
    context: RootContext,
    *,
    state: str = "open",
    label: str | None = None,
    limit: int = 10,
    session: _Session | None = None,
    sleep: Any = time.sleep,
    random_value: Any = random.random,
) -> IssueListResult:
    """Fetch one bounded, unauthenticated public issue page; never fetch issue bodies."""
    _validate_issue_arguments(context, state, label, limit)
    remote = discover_github_remote(context)
    http = session or _new_session()
    url = f"{_API_ORIGIN}/repos/{remote.owner}/{remote.repository}/issues"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _API_VERSION,
        "User-Agent": _USER_AGENT,
    }
    params: dict[str, str | int] = {"state": state, "per_page": limit, "page": 1}
    if label:
        params["labels"] = label

    retries = context.limits.max_http_retries
    try:
        for attempt in range(retries + 1):
            try:
                response = http.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=(min(_CONNECT_TIMEOUT_SECONDS, context.limits.max_http_timeout_seconds),
                             context.limits.max_http_timeout_seconds),
                    allow_redirects=False,
                    verify=True,
                    stream=True,
                )
            except SSLError as exc:
                raise RepoGuideError("github_tls_error", "TLS verification for GitHub failed") from exc
            except requests.Timeout as exc:
                if attempt < retries:
                    _sleep_backoff(attempt, sleep, random_value)
                    continue
                raise RepoGuideError("github_timeout", "GitHub API request timed out after bounded retries") from exc
            except requests.RequestException as exc:
                if attempt < retries:
                    _sleep_backoff(attempt, sleep, random_value)
                    continue
                raise RepoGuideError("github_network_error", "GitHub API request failed after bounded retries") from exc

            with _closing_response(response):
                remaining = _parse_remaining(response.headers)
                if response.status_code in {301, 302, 303, 307, 308}:
                    raise RepoGuideError("github_redirect_denied", "GitHub API redirects are not followed")
                if response.status_code in {429, 403} and _rate_limit_exhausted(response.headers, remaining):
                    _respect_rate_reset(response.headers, sleep)
                    raise RepoGuideError("github_rate_limited", "GitHub's unauthenticated API rate limit is exhausted")
                if response.status_code == 403 and response.headers.get("Retry-After") is not None:
                    if attempt < retries:
                        _sleep_retry_after(response.headers, attempt, sleep, random_value)
                        continue
                    raise RepoGuideError("github_rate_limited", "GitHub API secondary rate limit is active")
                if response.status_code == 429:
                    if attempt < retries:
                        _sleep_retry_after(response.headers, attempt, sleep, random_value)
                        continue
                    raise RepoGuideError("github_rate_limited", "GitHub API returned a rate-limit response")
                if response.status_code in {500, 502, 503, 504}:
                    if attempt < retries:
                        _sleep_backoff(attempt, sleep, random_value)
                        continue
                    raise RepoGuideError("github_server_error", "GitHub API remained unavailable after bounded retries")
                if response.status_code == 403:
                    raise RepoGuideError("github_forbidden", "GitHub denied this public API request")
                if response.status_code == 404:
                    raise RepoGuideError("github_not_found", "the public GitHub repository was not found")
                if response.status_code == 422:
                    raise RepoGuideError("github_invalid_request", "GitHub rejected the issue query parameters")
                if response.status_code != 200:
                    raise RepoGuideError("github_api_error", f"GitHub API returned HTTP {response.status_code}")

                try:
                    body = _read_bounded_body(response, context.limits.max_http_response_bytes)
                except requests.Timeout as exc:
                    if attempt < retries:
                        _sleep_backoff(attempt, sleep, random_value)
                        continue
                    raise RepoGuideError("github_timeout", "GitHub response timed out after bounded retries") from exc
                except requests.RequestException as exc:
                    if attempt < retries:
                        _sleep_backoff(attempt, sleep, random_value)
                        continue
                    raise RepoGuideError("github_network_error", "GitHub response failed after bounded retries") from exc
                try:
                    payload: Any = json.loads(body)
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise RepoGuideError("github_invalid_json", "GitHub returned malformed JSON") from exc
                if not isinstance(payload, list):
                    raise RepoGuideError("github_invalid_response", "GitHub returned an unexpected issue response")
                payload_items = cast(list[Any], payload)
                issues = _parse_issues(payload_items, remote, limit)
                has_next = "rel=\"next\"" in str(response.headers.get("Link", ""))
                return IssueListResult(
                    tuple(issues), remaining, has_next or len(payload_items) >= limit
                )
    finally:
        if session is None:
            http.close()  # type: ignore[attr-defined]

    raise RepoGuideError("github_api_error", "GitHub request did not complete")


def _validate_issue_arguments(context: RootContext, state: str, label: str | None, limit: int) -> None:
    if state not in {"open", "closed", "all"}:
        raise RepoGuideError("invalid_state", "state must be open, closed, or all")
    if label is not None and (
        not label.strip()
        or len(label) > 100
        or any(ord(character) < 32 for character in label)
    ):
        raise RepoGuideError("invalid_label", "label must be 1–100 printable characters")
    if isinstance(limit, bool) or not 1 <= limit <= context.limits.max_issues:
        raise RepoGuideError("invalid_issue_limit", "limit must be positive and within the configured maximum")


def _valid_remote_component(component: str) -> bool:
    return bool(
        component
        and component not in {".", ".."}
        and _REMOTE_COMPONENT.fullmatch(component)
        and not component.startswith("-")
        and not component.endswith(".")
    )


def _new_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    return session


def _read_bounded_body(response: _Response, limit: int) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            if int(content_length) > limit:
                raise RepoGuideError("github_response_too_large", "GitHub response exceeded the configured size limit")
        except ValueError as exc:
            raise RepoGuideError("github_invalid_response", "GitHub returned an invalid content length") from exc
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=16_384):
        if not chunk:
            continue
        total += len(chunk)
        if total > limit:
            raise RepoGuideError("github_response_too_large", "GitHub response exceeded the configured size limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _parse_issues(payload: list[Any], remote: GitHubRemote, limit: int) -> list[GitHubIssue]:
    issues: list[GitHubIssue] = []
    for raw_item in payload:
        if not isinstance(raw_item, dict) or "pull_request" in raw_item:
            continue
        item = cast(dict[str, Any], raw_item)
        number = item.get("number")
        title = item.get("title")
        labels = item.get("labels")
        if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
            continue
        if not isinstance(title, str) or not isinstance(labels, list):
            continue
        label_items = cast(list[Any], labels)
        safe_label_values: list[str] = []
        for raw_label in label_items[:_MAX_LABELS_PER_ISSUE]:
            if not isinstance(raw_label, dict):
                continue
            label_item = cast(dict[str, Any], raw_label)
            label_name = label_item.get("name")
            if isinstance(label_name, str):
                safe_label_values.append(label_name[:_MAX_LABEL_CHARS])
        safe_labels = tuple(safe_label_values)
        issues.append(
            GitHubIssue(
                number=number,
                title=title[:_MAX_TITLE_CHARS],
                labels=safe_labels,
                html_url=f"https://github.com/{remote.owner}/{remote.repository}/issues/{number}",
            )
        )
        if len(issues) >= limit:
            break
    return issues


def _parse_remaining(headers: Any) -> int | None:
    value = headers.get("X-RateLimit-Remaining")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _rate_limit_exhausted(headers: Any, remaining: int | None) -> bool:
    return remaining == 0 or (
        headers.get("X-RateLimit-Resource") == "core" and headers.get("X-RateLimit-Remaining") == "0"
    )


def _respect_rate_reset(headers: Any, sleep: Any) -> None:
    reset = headers.get("X-RateLimit-Reset")
    try:
        delay = float(reset) - time.time() if reset is not None else 0
    except (TypeError, ValueError):
        return
    if 0 < delay <= _RETRY_WAIT_CAP_SECONDS:
        sleep(delay)


def _sleep_retry_after(headers: Any, attempt: int, sleep: Any, random_value: Any) -> None:
    value = headers.get("Retry-After")
    try:
        requested = max(0.0, float(value)) if value is not None else 0.0
    except (TypeError, ValueError):
        try:
            reset_at = parsedate_to_datetime(str(value))
            if reset_at.tzinfo is None:
                reset_at = reset_at.replace(tzinfo=timezone.utc)
            requested = max(0.0, (reset_at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            requested = 0.0
    delay = min(max(requested, _backoff_delay(attempt, random_value)), _RETRY_WAIT_CAP_SECONDS)
    sleep(delay)


def _sleep_backoff(attempt: int, sleep: Any, random_value: Any) -> None:
    sleep(_backoff_delay(attempt, random_value))


def _backoff_delay(attempt: int, random_value: Any) -> float:
    base = min(0.25 * (2**attempt), _RETRY_WAIT_CAP_SECONDS)
    return min(base + max(0.0, min(float(random_value()), 1.0)) * 0.25, _RETRY_WAIT_CAP_SECONDS)


class _closing_response:
    """Close streamed responses on every status, parse, and exception path."""

    def __init__(self, response: _Response) -> None:
        self.response = response

    def __enter__(self) -> _Response:
        return self.response

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.response.close()
