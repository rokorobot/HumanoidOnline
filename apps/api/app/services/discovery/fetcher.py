"""Shared bounded HTTP fetcher for discovery acquisition (Stage B).

The ONLY module under apps/api/app allowed to issue acquisition requests. HTTP
GET only: no browser, no JavaScript, no rendering (docs/16 §20). Adapters and
the runner never touch the network directly, so etiquette cannot be opted out
of (docs/16 §12/§13):

- the exact docs/16 user agent, never a browser impersonation string;
- per-host minimum interval (>= 2 s) with an injectable clock and sleep, raised
  (never lowered) to a robots.txt `Crawl-delay` when the site states a longer one;
- redirects are never followed automatically: every hop is re-checked by a
  caller-supplied policy (host/path + robots) and the chain is bounded;
- bounded timeout and response-body size (streamed; oversize bodies discarded);
- at most 2 retries with increasing backoff, only for transport errors,
  timeouts and 5xx — never for 4xx, never for a block;
- a kill switch checked before every request.

`httpx` is imported here (runner-only `discovery` dependency group); nothing on
the public API request path imports this module.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import httpx

USER_AGENT = "HumanoidOnlineMarketBot/0.1 (+https://humanoidonline.com/crawler-policy)"
RETRIEVAL_METHOD = "HTTP_GET"

#: docs/16 §13 minimums/maxima. Limits may be tightened, never loosened.
MIN_INTERVAL_FLOOR_SECONDS = 2.0
PAGE_CAP_CEILING = 200
MAX_RETRIES_CEILING = 2


class KillSwitchEngaged(RuntimeError):
    """The operator's kill switch is on; no further request may be issued."""


@dataclass(frozen=True)
class FetchLimits:
    min_interval_seconds: float = MIN_INTERVAL_FLOOR_SECONDS
    page_cap: int = PAGE_CAP_CEILING
    timeout_seconds: float = 20.0
    max_body_bytes: int = 5 * 1024 * 1024
    max_redirects: int = 5
    max_retries: int = MAX_RETRIES_CEILING
    backoff_base_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.min_interval_seconds < MIN_INTERVAL_FLOOR_SECONDS:
            raise ValueError("min_interval_seconds may not go below 2 s (docs/16 §13)")
        if not 1 <= self.page_cap <= PAGE_CAP_CEILING:
            raise ValueError(f"page_cap must be between 1 and {PAGE_CAP_CEILING}")
        if not 0 <= self.max_retries <= MAX_RETRIES_CEILING:
            raise ValueError(f"max_retries must be between 0 and {MAX_RETRIES_CEILING}")
        if self.max_redirects < 0 or self.max_body_bytes <= 0 or self.timeout_seconds <= 0:
            raise ValueError("redirect, body and timeout limits must be positive")

    def as_manifest(self) -> dict:
        return {
            "min_interval_seconds": self.min_interval_seconds,
            "page_cap": self.page_cap,
            "timeout_seconds": self.timeout_seconds,
            "max_body_bytes": self.max_body_bytes,
            "max_redirects": self.max_redirects,
            "max_retries": self.max_retries,
            "backoff_base_seconds": self.backoff_base_seconds,
        }


@dataclass
class Response:
    """One final HTTP outcome after retries. `body` is None unless 2xx and within cap."""

    url: str
    status: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes | None = None
    error_class: str | None = None  # transport | timeout | body_too_large


@dataclass
class RedirectedResponse:
    """The end of a bounded redirect chain."""

    requested_url: str
    final_url: str
    response: Response
    #: Set when a hop was refused: (refused location, reason). Nothing was fetched there.
    refused: tuple[str, str] | None = None
    too_many_redirects: bool = False


class HttpFetcher:
    def __init__(
        self,
        *,
        limits: FetchLimits | None = None,
        transport: httpx.BaseTransport | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        kill_switch: Callable[[], bool] = lambda: False,
    ) -> None:
        self.limits = limits or FetchLimits()
        self._monotonic = monotonic
        self._sleep = sleep
        self._kill_switch = kill_switch
        self._last_request_at: dict[str, float] = {}
        self._host_interval: dict[str, float] = {}
        self._client = httpx.Client(
            transport=transport,
            follow_redirects=False,
            timeout=httpx.Timeout(self.limits.timeout_seconds),
            headers={"User-Agent": USER_AGENT},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpFetcher:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- etiquette ---------------------------------------------------------
    def honour_crawl_delay(self, host: str, seconds: float | None) -> float:
        """Raise `host`'s minimum interval to a robots `Crawl-delay`. It can only
        slow the fetcher down: a delay below the floor, or below a delay already
        honoured this run, changes nothing. Returns the effective interval."""
        key = host.lower()
        current = self.interval_for(key)
        if seconds is not None and seconds > current:
            self._host_interval[key] = float(seconds)
        return self.interval_for(key)

    def interval_for(self, host: str) -> float:
        return max(self.limits.min_interval_seconds, self._host_interval.get(host.lower(), 0.0))

    def _wait_for_host(self, url: str) -> None:
        if self._kill_switch():
            raise KillSwitchEngaged("kill switch engaged")
        host = (urlsplit(url).hostname or "").lower()
        last = self._last_request_at.get(host)
        if last is not None:
            remaining = self.interval_for(host) - (self._monotonic() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at[host] = self._monotonic()

    # -- one request with bounded retries -----------------------------------
    def get(self, url: str, headers: dict[str, str] | None = None) -> Response:
        attempt = 0
        while True:
            self._wait_for_host(url)
            response = self._get_once(url, headers or {})
            transient = response.error_class in ("transport", "timeout") or (
                response.status is not None and response.status >= 500
            )
            if not transient or attempt >= self.limits.max_retries:
                return response
            self._sleep(self.limits.backoff_base_seconds * (2 ** attempt))
            attempt += 1

    def _get_once(self, url: str, headers: dict[str, str]) -> Response:
        try:
            with self._client.stream("GET", url, headers=headers) as raw:
                result = Response(
                    url=url, status=raw.status_code,
                    headers={k.lower(): v for k, v in raw.headers.items()},
                )
                if not 200 <= raw.status_code < 300:
                    return result
                declared = raw.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > self.limits.max_body_bytes:
                    result.error_class = "body_too_large"
                    return result
                chunks: list[bytes] = []
                size = 0
                for chunk in raw.iter_bytes():
                    size += len(chunk)
                    if size > self.limits.max_body_bytes:
                        result.error_class = "body_too_large"
                        return result
                    chunks.append(chunk)
                result.body = b"".join(chunks)
                return result
        except httpx.TimeoutException:
            return Response(url=url, error_class="timeout")
        except httpx.TransportError:
            return Response(url=url, error_class="transport")

    # -- bounded, policy-checked redirects ---------------------------------
    def get_following(
        self,
        url: str,
        headers: dict[str, str] | None,
        hop_refusal: Callable[[str], str | None],
    ) -> RedirectedResponse:
        """GET `url`, following at most `max_redirects` hops. Every hop's target
        must pass `hop_refusal` (None = allowed) BEFORE it is requested; a
        refused hop ends the chain with nothing fetched there."""
        current = url
        for _ in range(self.limits.max_redirects + 1):
            response = self.get(current, headers if current == url else None)
            location = response.headers.get("location")
            if response.status not in (301, 302, 303, 307, 308) or not location:
                return RedirectedResponse(url, current, response)
            target = urljoin(current, location)
            reason = hop_refusal(target)
            if reason:
                return RedirectedResponse(url, current, response, refused=(target, reason))
            current = target
        return RedirectedResponse(url, current, response, too_many_redirects=True)
