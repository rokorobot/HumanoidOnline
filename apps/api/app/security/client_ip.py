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

from starlette.requests import Request

from app.config import get_settings

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

#: Returned when the peer address is genuinely unavailable (e.g. an ASGI
#: transport with no client). Never fabricated as a plausible-looking address.
UNKNOWN_CLIENT = "unknown"


def parse_trusted_networks(raw: str) -> tuple[IPNetwork, ...]:
    """Parse a comma-separated list of trusted ingress IPs/CIDRs.

    A bare address is treated as a single-host network. Unparseable tokens are
    dropped rather than silently widening trust.
    """
    networks: list[IPNetwork] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            networks.append(ipaddress.ip_network(token, strict=False))
        except ValueError:
            # Fail closed: an unparseable entry grants no trust.
            continue
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


def client_ip_for(request: Request) -> str:
    """Resolve the client address for a live request using current settings."""
    settings = get_settings()
    peer = request.client.host if request.client else None
    forwarded = request.headers.get(settings.forwarded_for_header)
    return resolve_client_ip(peer, forwarded, parse_trusted_networks(settings.trusted_proxy_ips))
