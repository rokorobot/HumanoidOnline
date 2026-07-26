"""WS8.1 / R3 — endpoint-aware abuse controls, and DEP P1 trusted ingress.

Two things must both be true, and they pull in opposite directions:

  1. A flood is refused (429 + Retry-After), per-endpoint, and a client cannot
     escape its limit by forging a forwarding header.
  2. A *legitimate* repeat is not mistaken for abuse. WS7's create-or-extend
     flow means the same buyer submitting again is a feature; if hardening
     broke that, WS8 would have shipped a regression disguised as security.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.config import Settings
from app.security.client_ip import (
    UNKNOWN_CLIENT,
    InvalidTrustedIngressError,
    parse_trusted_networks,
    resolve_client_ip,
)
from app.security.rate_limit import (
    RATE_LIMITER,
    InMemoryFixedWindowStore,
    RateLimiter,
    RateLimitPolicy,
    UnknownRateLimitPolicyError,
    rate_limited,
)

# --------------------------------------------------------------------------
# DEP P1 — trusted-ingress resolution (the anti-spoofing rule)
# --------------------------------------------------------------------------


def test_forwarding_header_from_untrusted_peer_is_ignored():
    """The adversarial case: a client that reaches us directly forges XFF.

    If this ever resolves to the forged value, the rate limiter can be bypassed
    with one header, and traffic can be attributed to someone else's address.
    """
    resolved = resolve_client_ip(
        peer="203.0.113.9",
        forwarded_value="1.2.3.4",
        trusted=parse_trusted_networks("10.0.0.1"),
    )
    assert resolved == "203.0.113.9"


def test_forwarding_header_ignored_when_no_ingress_is_trusted():
    """Empty trust list (the shipped default) means headers are never believed."""
    resolved = resolve_client_ip(
        peer="203.0.113.9", forwarded_value="1.2.3.4", trusted=parse_trusted_networks("")
    )
    assert resolved == "203.0.113.9"


def test_forwarding_header_honoured_from_trusted_ingress():
    resolved = resolve_client_ip(
        peer="10.0.0.1",
        forwarded_value="198.51.100.7",
        trusted=parse_trusted_networks("10.0.0.1"),
    )
    assert resolved == "198.51.100.7"


def test_chain_walks_right_to_left_skipping_trusted_hops():
    """With two trusted proxies in front, the client is the first untrusted
    entry from the right — not merely 'the leftmost', which a client can pad."""
    resolved = resolve_client_ip(
        peer="10.0.0.1",
        forwarded_value="9.9.9.9, 198.51.100.7, 10.0.0.2",
        trusted=parse_trusted_networks("10.0.0.0/24"),
    )
    assert resolved == "198.51.100.7"


def test_malformed_trusted_ingress_config_fails_loudly():
    """A mistyped CIDR must not be silently dropped.

    Dropping it looks safe (it only narrows trust) but it converts "resolve
    individual clients behind this proxy" into "trust nobody", collapsing every
    user onto the proxy address and rate-limiting them as one client — the
    shared-egress false positive, at proxy scale, presenting as an outage
    rather than a configuration error.
    """
    with pytest.raises(InvalidTrustedIngressError) as exc:
        parse_trusted_networks("10.0.0.0/8, garbage-not-an-ip")
    assert "garbage-not-an-ip" in str(exc.value)

    # Empty stays a deliberate, valid decision: trust no ingress.
    assert parse_trusted_networks("") == ()
    assert parse_trusted_networks("  ,  ") == ()


def test_cidr_trust_and_fallbacks():
    trusted = parse_trusted_networks("10.0.0.0/8")
    assert len(trusted) == 1
    # All-trusted chain -> fall back to the peer, never to a trusted proxy.
    assert resolve_client_ip("10.1.2.3", "10.4.5.6", trusted) == "10.1.2.3"
    # Malformed entry ends the walk instead of reaching for a nicer address.
    assert resolve_client_ip("10.1.2.3", "1.2.3.4, not-an-ip", trusted) == "10.1.2.3"
    # No peer at all is reported honestly, never fabricated.
    assert resolve_client_ip(None, "1.2.3.4", trusted) == UNKNOWN_CLIENT


# --------------------------------------------------------------------------
# Limiter mechanics
# --------------------------------------------------------------------------


def _limiter(**policy) -> tuple[RateLimiter, dict[str, float]]:
    clock = {"t": 0.0}
    limiter = RateLimiter(store=InMemoryFixedWindowStore(clock=lambda: clock["t"]))
    limiter.set_policy(RateLimitPolicy(**policy))
    return limiter, clock


def test_burst_tier_refuses_with_429_and_retry_after():
    limiter, _ = _limiter(
        name="ep", burst_limit=2, burst_window_seconds=60,
        sustained_limit=100, sustained_window_seconds=3600,
    )
    limiter.check("ep", "203.0.113.1")
    limiter.check("ep", "203.0.113.1")
    with pytest.raises(HTTPException) as exc:
        limiter.check("ep", "203.0.113.1")
    assert exc.value.status_code == 429
    retry_after = exc.value.headers["Retry-After"]
    assert retry_after.isdigit() and 1 <= int(retry_after) <= 60


def test_limits_are_per_client_not_global():
    limiter, _ = _limiter(
        name="ep", burst_limit=1, burst_window_seconds=60,
        sustained_limit=100, sustained_window_seconds=3600,
    )
    limiter.check("ep", "203.0.113.1")
    # A different client is unaffected by the first client's exhaustion.
    limiter.check("ep", "203.0.113.2")


def test_window_rolls_over():
    limiter, clock = _limiter(
        name="ep", burst_limit=1, burst_window_seconds=60,
        sustained_limit=100, sustained_window_seconds=3600,
    )
    limiter.check("ep", "203.0.113.1")
    clock["t"] = 61.0
    limiter.check("ep", "203.0.113.1")  # new window, allowed again


def test_sustained_tier_catches_drip_flooding_under_the_burst_limit():
    """Low-and-slow traffic never trips the burst window; the long window is
    what stops it. This is why one global number is not sufficient."""
    limiter, clock = _limiter(
        name="ep", burst_limit=5, burst_window_seconds=60,
        sustained_limit=3, sustained_window_seconds=3600,
    )
    for i in range(3):
        clock["t"] = i * 120.0  # one request every two minutes
        limiter.check("ep", "203.0.113.1")
    clock["t"] = 3 * 120.0
    with pytest.raises(HTTPException) as exc:
        limiter.check("ep", "203.0.113.1")
    assert exc.value.status_code == 429


def test_unknown_policy_fails_closed_at_check_time():
    """A misspelled policy must refuse the request, not serve it unprotected."""
    limiter, _ = _limiter(
        name="ep", burst_limit=1, burst_window_seconds=60,
        sustained_limit=1, sustained_window_seconds=3600,
    )
    with pytest.raises(UnknownRateLimitPolicyError):
        limiter.check("no-such-policy", "203.0.113.1")


def test_unknown_policy_is_rejected_at_wiring_time():
    """Better still: the typo never reaches production, because declaring the
    dependency raises at import. `rate_limited("commercial_lead")` (singular) is
    exactly the mistake that would otherwise disable R3 for that route."""
    with pytest.raises(UnknownRateLimitPolicyError) as exc:
        rate_limited("commercial_lead")
    assert "commercial_leads" in str(exc.value)


def test_every_protected_route_declares_a_registered_policy():
    """Guards against the same drift arriving via a new route later."""
    for name in ("buyer_requirements", "commercial_leads"):
        assert RATE_LIMITER.policy(name) is not None


def test_429_body_and_headers_carry_no_pii():
    """R5: the refusal must not echo the client address or submitted fields."""
    limiter, _ = _limiter(
        name="ep", burst_limit=1, burst_window_seconds=60,
        sustained_limit=100, sustained_window_seconds=3600,
    )
    limiter.check("ep", "203.0.113.55")
    with pytest.raises(HTTPException) as exc:
        limiter.check("ep", "203.0.113.55")
    rendered = f"{exc.value.detail} {exc.value.headers}"
    assert "203.0.113.55" not in rendered


# --------------------------------------------------------------------------
# Wiring: the dependency, on a real ASGI app
# --------------------------------------------------------------------------


@pytest.fixture
def tight_app():
    """A miniature app carrying the same dependency the real write paths use."""
    app = FastAPI()

    @app.post("/leads", dependencies=[Depends(rate_limited("commercial_leads"))])
    def leads() -> dict[str, str]:
        return {"ok": "yes"}

    RATE_LIMITER.reset()
    RATE_LIMITER.set_policy(
        RateLimitPolicy(
            name="commercial_leads", burst_limit=3, burst_window_seconds=60,
            sustained_limit=100, sustained_window_seconds=3600,
        )
    )
    yield TestClient(app)
    RATE_LIMITER.reset()


def test_endpoint_returns_429_with_retry_after_header(tight_app):
    for _ in range(3):
        assert tight_app.post("/leads").status_code == 200
    blocked = tight_app.post("/leads")
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"].isdigit()


def test_legitimate_repeat_submission_is_not_treated_as_abuse(tight_app):
    """WS7 create-or-extend: the same buyer submitting again is legitimate.

    The burst tier must leave room for it — a retry inside the limit is a 200,
    not a 429. (The full create-or-extend semantics stay covered by
    `test_commercial_leads.py`; this asserts hardening did not break them.)
    """
    first = tight_app.post("/leads")
    retry = tight_app.post("/leads")
    assert (first.status_code, retry.status_code) == (200, 200)


def test_there_is_no_global_disable_switch():
    """R3 is release-blocking: environments tune the numbers, they do not get to
    remove abuse control from an anonymous mutation endpoint. A previous
    revision shipped `rate_limit_enabled` and a test that blessed turning
    protection off; both are gone, and this asserts they stay gone."""
    assert not hasattr(Settings(_env_file=None), "rate_limit_enabled")
    source = (Path(__file__).resolve().parents[1] / "app" / "security" / "rate_limit.py").read_text(
        encoding="utf-8"
    )
    assert "rate_limit_enabled" not in source


def test_spoofed_forwarding_header_cannot_buy_a_fresh_budget(tight_app):
    """End-to-end anti-spoofing: exhaust the limit, then rotate X-Forwarded-For.

    TestClient's peer is not configured as trusted ingress, so every request
    must still be attributed to the same client and stay refused.
    """
    for _ in range(3):
        tight_app.post("/leads")
    for spoof in ("1.2.3.4", "5.6.7.8", "9.10.11.12"):
        blocked = tight_app.post("/leads", headers={"X-Forwarded-For": spoof})
        assert blocked.status_code == 429
