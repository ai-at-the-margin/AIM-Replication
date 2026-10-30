"""Adapter interface, normalised response type and HTTP transport.

Retries live in the runner, not here: an adapter either returns the raw provider
JSON or raises ``TransportError`` saying whether the failure is retryable.
"""

from __future__ import annotations

import abc
import contextvars
import email.utils
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..settings import Config

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 521, 522, 524, 529}

# Set by the runner around each send so a simulated transport can seed itself per call.
# Real transports ignore it; nothing from it is ever sent to a provider.
CALL_CONTEXT: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("aim_call_context",
                                                                                    default=None)


class TransportError(Exception):
    """An HTTP or network failure. ``retryable`` decides whether the runner retries."""

    def __init__(self, message: str, status: int | None = None, retry_after: float | None = None,
                 body: Any = None, retryable: bool = True):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after
        self.body = body
        self.retryable = retryable


@dataclass
class TransportResponse:
    status: int
    headers: dict[str, str]
    json: Any
    text: str


class Transport(abc.ABC):
    """Minimal async HTTP interface so the simulator can stand in for the network."""

    name = "abstract"

    @abc.abstractmethod
    async def request(self, method: str, url: str, headers: dict[str, str], json_body: Any = None,
                      content: bytes | None = None, files: Any = None, data: Any = None) -> TransportResponse:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


def parse_retry_after(value: str | None) -> float | None:
    """Retry-After is either seconds or an HTTP date."""
    if value is None or value == "":
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        return max(0.0, parsed.timestamp() - time.time())
    except Exception:
        return None


class HttpTransport(Transport):
    name = "http"

    def __init__(self, timeout_s: float = 600.0):
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=30.0))

    async def request(self, method: str, url: str, headers: dict[str, str], json_body: Any = None,
                      content: bytes | None = None, files: Any = None, data: Any = None) -> TransportResponse:
        try:
            response = await self.client.request(method, url, headers=headers, json=json_body,
                                                 content=content, files=files, data=data)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            raise TransportError(f"network error: {exc.__class__.__name__}: {exc}", retryable=True)
        text = response.text
        try:
            payload = response.json()
        except Exception:
            payload = None
        header_map: dict[str, str] = {}
        keys = list(response.headers.keys())
        for i in range(len(keys)):
            header_map[keys[i].lower()] = response.headers.get(keys[i])
        if response.status_code >= 400:
            retry_after = parse_retry_after(header_map.get("retry-after"))
            if retry_after is None:
                retry_after = parse_retry_after(header_map.get("retry-after-ms") and
                                                str(float(header_map["retry-after-ms"]) / 1000.0))
            raise TransportError(
                f"HTTP {response.status_code}: {text[:500]}",
                status=response.status_code,
                retry_after=retry_after,
                body=payload if payload is not None else text[:2000],
                retryable=response.status_code in RETRYABLE_STATUS,
            )
        return TransportResponse(status=response.status_code, headers=header_map, json=payload, text=text)

    async def aclose(self) -> None:
        await self.client.aclose()


@dataclass
class ToolEvent:
    event_idx: int
    provider_event_type: str
    query_text: str | None = None
    query_visible: bool = False
    caller: str | None = None
    result_urls: list[str] = field(default_factory=list)
    error_code: str | None = None
    action_type: str | None = None
    tool_use_id: str | None = None
    executed: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_idx": self.event_idx, "provider_event_type": self.provider_event_type,
            "query_text": self.query_text, "query_visible": self.query_visible, "caller": self.caller,
            "result_urls": self.result_urls, "error_code": self.error_code, "action_type": self.action_type,
            "tool_use_id": self.tool_use_id, "executed": self.executed,
        }


@dataclass
class NormalisedResponse:
    final_text: str
    reasoning_text: str
    tool_events: list[ToolEvent]
    search_count: int
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    model_returned: str | None
    stop_reason: str | None
    refusal_flag: bool
    reasoning_effort: str | None = None
    notes: list[str] = field(default_factory=list)


class ProviderAdapter(abc.ABC):
    """build_request -> send -> normalise (BUILD_BRIEF §6.2)."""

    provider = "abstract"

    def __init__(self, config: Config, transport: Transport, api_key: str | None):
        self.config = config
        self.transport = transport
        self.api_key = api_key
        self.spec = config.provider(self.provider)

    @property
    def base_url(self) -> str:
        import os

        override = os.environ.get(f"AIM_{self.provider.upper()}_BASE_URL", "")
        if override:
            return override.rstrip("/")
        return str(self.spec.get("base_url", "")).rstrip("/")

    @abc.abstractmethod
    def headers(self) -> dict[str, str]:
        raise NotImplementedError

    @abc.abstractmethod
    def build_request(self, prompt_text: str, model_id: str, search_enabled: bool,
                      params: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @abc.abstractmethod
    async def send(self, request: dict[str, Any]) -> dict[str, Any]:
        """Return a raw envelope ``{"responses": [...], ...}`` ready to be written to disk."""
        raise NotImplementedError

    @abc.abstractmethod
    def normalise(self, raw: dict[str, Any]) -> NormalisedResponse:
        raise NotImplementedError

    async def list_models(self) -> list[str]:
        response = await self.transport.request("GET", self.base_url + "/models", self.headers())
        payload = response.json or {}
        rows = payload.get("data", [])
        ids = []
        for i in range(len(rows)):
            if isinstance(rows[i], dict) and rows[i].get("id"):
                ids.append(str(rows[i]["id"]))
        return ids


def merge_extra(request: dict[str, Any], extra: dict[str, Any] | None) -> dict[str, Any]:
    """Overlay per-model request fields; a value of None removes the key."""
    if not extra:
        return request
    keys = list(extra.keys())
    for i in range(len(keys)):
        if extra[keys[i]] is None:
            request.pop(keys[i], None)
        else:
            request[keys[i]] = extra[keys[i]]
    return request


def word_count(text: str | None) -> int:
    if not text:
        return 0
    return len(text.split())
