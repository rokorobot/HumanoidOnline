"""Application settings (Pydantic v2 foundation).

Values come from the environment (or an optional local `.env`). The default
`database_url` matches docker-compose.yml so a laptop works out of the box; CI
overrides it via the DATABASE_URL environment variable.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # SQLAlchemy URL (note the "+psycopg" driver token). Matches docker-compose.yml.
    database_url: str = (
        "postgresql+psycopg://humanoid:humanoid@localhost:5432/humanoidonline"
    )
    # Canonical schema that db/schema.sql installs into.
    db_schema: str = "humanoid"

    api_title: str = "HumanoidOnline API"
    api_version: str = "0.1.0"

    # ---------------------------------------------------------------- WS8.1 --
    # Security boundaries. All of the following are governed by the ratified
    # WS8 contract (docs/12) and its frozen Deployment Execution Profile (§6).
    #
    # NOTE: `database_url` above still carries a development default. That is
    # gap B3 and it is deliberately NOT fixed here — B3/B4 belong to WS8.2.

    # R1 / DEP P4 — internal admin. Absent credentials mean the admin surface is
    # NOT mounted at all (fail closed, WS8-L5) rather than mounted unprotected.
    # This is B1 *stage 1* only: the production network boundary that puts admin
    # on a separate protected host/listener is realized in WS8.7 (R27) and
    # probed externally in WS8.8 (R29).
    admin_username: str | None = None
    admin_password: str | None = None
    admin_session_secret: str | None = None

    # DEP P1 — trusted ingress. Comma-separated IPs/CIDRs whose forwarding
    # headers may be believed. EMPTY (the default) means *no* ingress is trusted
    # and every forwarding header is ignored, so a client cannot spoof its
    # source address. Frozen as trust semantics, never as a hop count.
    trusted_proxy_ips: str = ""
    forwarded_for_header: str = "x-forwarded-for"

    # R4 — cross-origin posture, explicit rather than implicit (WS8-L9). EMPTY
    # (the default) is a deliberate strict same-origin policy: no CORS
    # middleware is installed and no Access-Control-Allow-Origin is ever sent.
    cors_allowed_origins: str = ""
    # TLS terminates at the ingress (WS8.7), so HSTS is opt-in — a non-TLS
    # environment must never advertise it.
    enable_hsts: bool = False

    # R3 — endpoint-aware abuse controls (§11 D7: never one global number).
    # Two tiers per endpoint: a short *burst* window catching rapid repeated
    # submission, and a long *sustained* window catching drip flooding.
    #
    # Sizing rationale. These limits key on client IP, and IP is a *shared*
    # identifier: an office, campus or mobile carrier NAT presents many genuine
    # buyers as one address. A tight burst window therefore misclassifies real
    # demand as abuse and breaks Journey B — the product's commercial funnel —
    # for exactly the enterprise buyers it is meant to serve. R3 requires that
    # legitimate use is *not* refused, so the burst tier is sized for shared
    # egress and the sustained tier does the real anti-flood work. (An initial
    # 5/60s burst was rejected during WS8.1 verification: it returned 429 to
    # ordinary wizard traffic in the e2e run. Kept as a cautionary note.)
    rate_limit_enabled: bool = True
    buyer_requirements_burst: int = 20
    buyer_requirements_burst_window_s: int = 60
    buyer_requirements_sustained: int = 120
    buyer_requirements_sustained_window_s: int = 3600
    # Stricter than buyer-intent: this endpoint captures PII and is the
    # commercial conversion seam, and a genuine buyer submits it far less often
    # than they iterate on requirements.
    commercial_leads_burst: int = 10
    commercial_leads_burst_window_s: int = 60
    commercial_leads_sustained: int = 60
    commercial_leads_sustained_window_s: int = 3600


@lru_cache
def get_settings() -> Settings:
    return Settings()
