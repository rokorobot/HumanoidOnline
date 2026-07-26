"""R3 — endpoint-aware abuse controls for the two public write paths.

Ratified shape (docs/12 §11 D7): *endpoint-aware, never one arbitrary global
number*. Each protected endpoint gets two tiers keyed by resolved client IP:

  burst      a short window catching rapid repeated submission
  sustained  a long window catching low-and-slow drip flooding

Two constraints from the contract shape this module:

**WS8-L10 — anonymity is preserved.** These endpoints stay anonymous. No
authentication, identity, cookie or fingerprint is introduced to solve abuse.

**DEP P2/P3 — state model.** MVP v0.1 is a *singleton* API instance, so
process-local counters are permitted — but only behind
:class:`RateLimitStore`, so shared/durable state can replace them *before* any
horizontal scaling. Scaling without that replacement is a defect, not a
deployment choice; :class:`InMemoryFixedWindowStore` is explicitly not
multi-process correct.

A legitimate retry must not be mistaken for abuse. The burst tier is sized to
leave room for the WS7 create-or-extend flow (a repeat submission by the same
buyer is a *feature*, not an attack), and R3's tests prove that.
"""
from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException, Request, status

from app.config import get_settings
from app.security.client_ip import client_ip_for


class RateLimitStore(Protocol):
    """Counter storage behind which the limiter is insulated (DEP P3).

    Implementations must be safe for concurrent use within one process.
    """

    def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        """Record a hit and return ``(count_in_window, seconds_until_reset)``."""

    def reset(self) -> None:
        """Drop all counters (test/operational support)."""


class InMemoryFixedWindowStore:
    """Process-local fixed-window counters.

    Permitted **only** under the frozen singleton topology (DEP P2). This is
    not correct across processes or hosts: replacing it with a shared store is
    a precondition of horizontal replication, not an optimisation.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._windows: dict[str, tuple[float, int]] = {}

    def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        now = self._clock()
        with self._lock:
            started_at, count = self._windows.get(key, (now, 0))
            if now - started_at >= window_seconds:
                started_at, count = now, 0
            count += 1
            self._windows[key] = (started_at, count)
        # Retry-After is always a whole number of seconds, at least 1, and never
        # longer than the window itself.
        retry_after = max(1, math.ceil(window_seconds - (now - started_at)))
        return count, min(retry_after, window_seconds)

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()


@dataclass(frozen=True)
class RateLimitPolicy:
    """Per-endpoint limits. Both tiers are enforced; the burst tier is checked
    first so a flood is refused as early as possible."""

    name: str
    burst_limit: int
    burst_window_seconds: int
    sustained_limit: int
    sustained_window_seconds: int


class RateLimiter:
    def __init__(self, store: RateLimitStore | None = None) -> None:
        self._store: RateLimitStore = store or InMemoryFixedWindowStore()
        self._policies: dict[str, RateLimitPolicy] = {}

    # -- configuration ------------------------------------------------------
    def set_policy(self, policy: RateLimitPolicy) -> None:
        self._policies[policy.name] = policy

    def policy(self, name: str) -> RateLimitPolicy | None:
        return self._policies.get(name)

    def load_from_settings(self) -> None:
        """(Re)load every policy from current settings."""
        s = get_settings()
        self.set_policy(
            RateLimitPolicy(
                name="buyer_requirements",
                burst_limit=s.buyer_requirements_burst,
                burst_window_seconds=s.buyer_requirements_burst_window_s,
                sustained_limit=s.buyer_requirements_sustained,
                sustained_window_seconds=s.buyer_requirements_sustained_window_s,
            )
        )
        self.set_policy(
            RateLimitPolicy(
                name="commercial_leads",
                burst_limit=s.commercial_leads_burst,
                burst_window_seconds=s.commercial_leads_burst_window_s,
                sustained_limit=s.commercial_leads_sustained,
                sustained_window_seconds=s.commercial_leads_sustained_window_s,
            )
        )

    def reset(self) -> None:
        self._store.reset()

    # -- enforcement --------------------------------------------------------
    def check(self, policy_name: str, client_ip: str) -> None:
        """Raise ``429`` with ``Retry-After`` when either tier is exceeded."""
        policy = self._policies.get(policy_name)
        if policy is None:
            return

        for tier, limit, window in (
            ("burst", policy.burst_limit, policy.burst_window_seconds),
            ("sustained", policy.sustained_limit, policy.sustained_window_seconds),
        ):
            count, retry_after = self._store.hit(
                f"{policy_name}:{tier}:{client_ip}", window
            )
            if count > limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        "Too many requests. This endpoint is rate limited to protect "
                        "the service; please retry after the indicated interval."
                    ),
                    # Never echo the client address or any submitted field back:
                    # the response carries no PII (R5).
                    headers={"Retry-After": str(retry_after)},
                )


#: Module-level limiter. Singleton to match DEP P2; tests reset it per-test.
RATE_LIMITER = RateLimiter()
RATE_LIMITER.load_from_settings()


def rate_limited(policy_name: str) -> Callable[[Request], None]:
    """FastAPI dependency enforcing `policy_name` for the decorated route."""

    def dependency(request: Request) -> None:
        if not get_settings().rate_limit_enabled:
            return
        RATE_LIMITER.check(policy_name, client_ip_for(request))

    return dependency
