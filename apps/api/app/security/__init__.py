"""WS8.1 — Security boundaries.

Everything in this package exists to satisfy WS8 gates R1–R6 against the frozen
Deployment Execution Profile (docs/12 §6). It adds **no product capability**
(WS8-L1): these are operator/security controls hardening surfaces that already
shipped.

  client_ip    DEP P1 — trusted-ingress resolution (spoof-resistant)
  rate_limit   R3     — endpoint-aware abuse controls, DEP P2/P3 state model
  headers      R4     — explicit cross-origin + security-header posture
  admin_auth   R1     — application-level admin authentication (B1 stage 1)
"""
from __future__ import annotations

from app.security.admin_auth import AdminAuth
from app.security.client_ip import client_ip_for, parse_trusted_networks, resolve_client_ip
from app.security.headers import SecurityHeadersMiddleware, configure_cors
from app.security.rate_limit import (
    RATE_LIMITER,
    InMemoryFixedWindowStore,
    RateLimiter,
    RateLimitPolicy,
    RateLimitStore,
    rate_limited,
)

__all__ = [
    "RATE_LIMITER",
    "AdminAuth",
    "InMemoryFixedWindowStore",
    "RateLimitPolicy",
    "RateLimitStore",
    "RateLimiter",
    "SecurityHeadersMiddleware",
    "client_ip_for",
    "configure_cors",
    "parse_trusted_networks",
    "rate_limited",
    "resolve_client_ip",
]
