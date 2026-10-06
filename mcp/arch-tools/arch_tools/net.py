"""Shared HTTP helpers and error types."""

from __future__ import annotations

import json
from typing import Any

import httpx

from . import __version__

USER_AGENT = f"Mozilla/5.0 (compatible; arch-tools/{__version__}; citation-and-retrieval-helper)"


class ToolError(Exception):
    """An error that should be reported to the caller as-is (bad input, missing index, ...)."""

    def __init__(self, message: str, *, hint: str | None = None, data: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.data = data or {}

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"error": self.message}
        if self.hint:
            out["hint"] = self.hint
        out.update(self.data)
        return out


class ServiceError(ToolError):
    """A backing service answered, but with an error or an unusable payload."""


class ServiceUnavailable(ServiceError):
    """A backing service could not be reached at all (connection refused, DNS, timeout)."""


def dumps(obj: Any) -> str:
    """Compact JSON used for every tool output."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:300].strip()
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err)[:300]
        if err:
            return str(err)[:300]
        if payload.get("message"):
            return str(payload["message"])[:300]
    return json.dumps(payload)[:300]


async def request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    json_body: Any = None,
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | float | None = None,
    service: str = "service",
) -> Any:
    """Send a request and decode a JSON response, mapping failures onto ToolError subclasses."""
    kwargs: dict[str, Any] = {"headers": headers}
    if json_body is not None:
        kwargs["json"] = json_body
    if timeout is not None:
        kwargs["timeout"] = timeout
    try:
        response = await client.request(method, url, **kwargs)
    except httpx.TimeoutException as exc:
        raise ServiceUnavailable(f"{service} timed out ({type(exc).__name__}) at {url}") from exc
    except httpx.TransportError as exc:
        raise ServiceUnavailable(f"{service} unreachable at {url}: {exc or type(exc).__name__}") from exc
    if response.status_code >= 400:
        raise ServiceError(
            f"{service} returned HTTP {response.status_code} for {url}: {_error_text(response)}",
            data={"status_code": response.status_code},
        )
    try:
        return response.json()
    except ValueError as exc:
        raise ServiceError(f"{service} returned invalid JSON from {url}") from exc
