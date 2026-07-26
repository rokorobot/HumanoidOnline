"""DEP P1 — trusted-ingress client-IP resolution.

The frozen Deployment Execution Profile (docs/12 §6, P1) states:

> Forwarding headers are trusted **only** when they arrive from an explicitly
> configured trusted ingress. Forwarding headers supplied directly by a client
> are **ignored — never parsed as truth**.

This is deliberately *not* a numeric hop count. A hop count is spoofable exactly
when the trust boundary is unstated: a client that can reach the application
directly can prepend as many fake entries as the count skips. Trust is therefore
anchored to the **peer address**, and only then is the forwarding chain walked.

Getting this wrong is not cosmetic — it is a rate-limit bypass (R3) and, worse,
a way to attribute one client's traffic to another's address.
"""
from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from functools import lru_cache

from starlette.requests import Request

from app.config import get_settings

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

#: Returned when the peer address is genuinely unavailable (e.g. an ASGI
#: transport with no client). Never fabricated as a plausible-looking address.
UNKNOWN_CLIENT = "unknown"


class InvalidTrustedIngressError(ValueError):
    """Raised when `TRUSTED_PROXY_IPS` is set but not parseable."""


def parse_trusted_networks(raw: str) -> tuple[IPNetwork, ...]:
    """Parse a comma-separated list of trusted ingress IPs/CIDRs.

    Three cases, deliberately distinguished:

    - **empty** -> trust no ingress. A real decision, and the safe default.
    - **valid** -> use exactly those networks.
    - **non-empty but malformed** -> raise. Never silently reinterpret.

    Dropping bad entries looks conservative — it can only *narrow* trust — but
    it is operationally dangerous. A single mistyped CIDR silently converts
    "trust this ingress and resolve individual clients" into "trust nobody",
    which collapses every user behind the proxy onto the proxy's own address and
    rate-limits them as one client. That is the shared-egress false positive
    already found during WS8.1 verification, at proxy scale, and it would appear
    as a mysterious outage rather than a configuration error.
    """
    tokens = [token.strip() for token in raw.split(",")]
    tokens = [token for token in tokens if token]
    if not tokens:
        return ()

    networks: list[IPNetwork] = []
    invalid: list[str] = []
    for token in tokens:
        try:
            networks.append(ipaddress.ip_network(token, strict=False))
        except ValueError:
            invalid.append(token)

    if invalid:
        raise InvalidTrustedIngressError(
            "TRUSTED_PROXY_IPS is set but contains unparseable entries: "
            f"{', '.join(repr(entry) for entry in invalid)}. "
            "Fix the value, or clear it to trust no ingress."
        )
    return tuple(networks)


def _is_trusted(address: str, trusted: Iterable[IPNetwork]) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in trusted)


def resolve_client_ip(
    peer: str | None,
    forwarded_value: str | None,
    trusted: Iterable[IPNetwork],
) -> str:
    """Resolve the effective client address under DEP P1.

    - No peer address at all -> ``UNKNOWN_CLIENT``.
    - Peer is **not** trusted ingress -> the peer address, and the forwarding
      header is ignored entirely. This is the anti-spoofing rule.
    - Peer **is** trusted ingress -> walk the forwarding chain right-to-left and
      return the first address that is not itself trusted ingress. If every
      entry is trusted (or the header is absent/garbage), fall back to the peer.
    """
    if not peer:
        return UNKNOWN_CLIENT

    trusted = tuple(trusted)
    if not trusted or not _is_trusted(peer, trusted):
        return peer

    if not forwarded_value:
        return peer

    for candidate in reversed([part.strip() for part in forwarded_value.split(",")]):
        if not candidate:
            continue
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            # A malformed entry ends the walk: everything to its left is
            # unverifiable, so we do not keep reaching for a "nicer" address.
            return peer
        if not _is_trusted(candidate, trusted):
            return candidate

    return peer


@lru_cache(maxsize=8)
def _cached_trusted_networks(raw: str) -> tuple[IPNetwork, ...]:
    """Parse once per distinct configuration value (this runs per request)."""
    return parse_trusted_networks(raw)


def validate_trusted_ingress_config() -> tuple[IPNetwork, ...]:
    """Parse the configured trust list at startup so a malformed value fails to
    boot rather than surfacing as a 500 on the first request."""
    return _cached_trusted_networks(get_settings().trusted_proxy_ips)


def client_ip_for(request: Request) -> str:
    """Resolve the client address for a live request using current settings."""
    settings = get_settings()
    peer = request.client.host if request.client else None
    forwarded = request.headers.get(settings.forwarded_for_header)
    return resolve_client_ip(
        peer, forwarded, _cached_trusted_networks(settings.trusted_proxy_ips)
    )
