"""Application settings (Pydantic v2 foundation).

Values come from the environment (or an optional local `.env`).

**WS8.2 / R7 — the environment contract.** Before WS8.2 `database_url` carried a
development default, so an API booted without `DATABASE_URL` silently pointed at
`humanoid:humanoid@localhost` instead of failing (gap B3). Convenience defaults
now exist **only** when the environment is explicitly development or test.

The detection itself is written to fail safe (WS8-L5):

- `APP_ENV` unset or empty  -> **production** (strict). Never development.
- `APP_ENV` unrecognised    -> **raises**. A typo is loud, not silently strict
  and certainly not silently permissive.
- development / test        -> convenience defaults allowed.
- staging / production      -> every production-required value must be explicit.

The dangerous design would be defaulting to development when the variable is
absent: a production box with a missing or misspelled variable would quietly
re-enable dev credentials. This does the opposite in both directions.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Every environment the application recognises. Anything else is a typo.
ALLOWED_APP_ENVS: tuple[str, ...] = ("development", "test", "staging", "production")

#: Environments where developer-convenience defaults may be used.
RELAXED_APP_ENVS: frozenset[str] = frozenset({"development", "test"})

#: The laptop/docker-compose database. Only ever reachable in a relaxed env.
DEVELOPMENT_DATABASE_URL = (
    "postgresql+psycopg://humanoid:humanoid@localhost:5432/humanoidonline"
)


class ConfigurationError(RuntimeError):
    """Raised when production-required configuration is missing or malformed.

    Deliberately fatal at import: an application that cannot be configured
    correctly must not start serving (WS8-L5).
    """


def normalize_app_env(raw: str | None) -> str:
    """Resolve `APP_ENV`, failing safe in both directions."""
    value = (raw or "").strip()
    if not value:
        # Unset means production. The safe direction: strictness by default,
        # never accidental development.
        return "production"
    lowered = value.lower()
    if lowered not in ALLOWED_APP_ENVS:
        raise ConfigurationError(
            f"APP_ENV={value!r} is not a recognised environment. "
            f"Use one of: {', '.join(ALLOWED_APP_ENVS)}. "
            "Leave it unset only if you intend production."
        )
    return lowered


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # WS8.2 / R7 — explicit environment contract. Unset resolves to production.
    app_env: str = "production"

    # SQLAlchemy URL (note the "+psycopg" driver token). NO default: in a strict
    # environment this must be supplied, and in a relaxed one the development
    # value is filled in by the validator below so the intent stays visible.
    database_url: str | None = None

    # Canonical schema that db/schema.sql installs into.
    db_schema: str = "humanoid"

    api_title: str = "HumanoidOnline API"
    api_version: str = "0.1.0"

    # WS8.2 / R9 — where the governed migration files live, so the application
    # can verify the database is migrated before it serves. The mechanism that
    # guarantees migrations have *run* is WS8.7's; this is the contract.
    migrations_dir: str | None = None

    # ---------------------------------------------------------------- WS8.1 --
    # Security boundaries, governed by the ratified WS8 contract (docs/12) and
    # its frozen Deployment Execution Profile (§6).

    # R1 / DEP P4 — internal admin. Absent credentials mean the admin surface is
    # NOT mounted at all (fail closed, WS8-L5) rather than mounted unprotected.
    # This is B1 *stage 1* only: the production network boundary that puts admin
    # on a separate protected host/listener is realized in WS8.7 (R27) and
    # probed externally in WS8.8 (R29).
    admin_username: str | None = None
    admin_password: str | None = None
    admin_session_secret: str | None = None

    # ------------------------------------------------------------- AGENT-02 --
    # Evidence references (docs/20 §7.1.1). A DEDICATED key: deliberately not the
    # admin session secret, a credential or the database password, so that
    # rotating or compromising one never implicates the other. Base64url of
    # exactly 64 raw bytes (512-bit AES-SIV).
    #
    # Absent by default and fail-closed: without it the agent evidence-reference
    # path raises rather than emitting an unauthenticated token or a raw
    # identifier. There is intentionally no development default — a shipped
    # default key is the same as no key, but harder to notice.
    #
    # `evidence_ref_previous_keys` is "<key_id>:<base64url>[,...]" and exists so a
    # rotation can accept references issued under the outgoing key for a window.
    evidence_ref_key: str | None = None
    evidence_ref_key_id: str = "1"
    evidence_ref_previous_keys: str = ""

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
    # NOTE: there is intentionally no `rate_limit_enabled` switch. R3 is a
    # release-blocking control; per-environment configuration tunes the numbers,
    # it does not permit removing abuse protection from an anonymous mutation
    # endpoint.
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

    # ------------------------------------------------ lead notification -----
    # Operational email to the HumanoidOnline owner when POST /api/commercial-
    # leads creates or extends a lead (app/services/lead_notifications.py). The
    # database write is authoritative and already committed before this ever
    # runs; a notification is a best-effort side channel, never a gate.
    #
    # OFF by default, and only ever active when ALL FOUR of enabled/to/from/key
    # are set — same fail-closed-per-feature doctrine as the admin credentials
    # above (partial/missing config disables the feature, it never blocks the
    # API from starting; see `lead_notifications._notification_ready`).
    lead_notification_enabled: bool = False
    # Comma-separated recipient address(es). Never hard-code an address here.
    lead_notification_to: str | None = None
    lead_notification_from: str | None = None
    # Provider API key. Never logged, never echoed in an error.
    email_api_key: str | None = None
    # Non-secret: the provider's HTTPS endpoint. Defaults to Resend's single
    # send endpoint (https://resend.com/docs/api-reference/emails/send-email) —
    # chosen because a plain POST + Bearer token needs no SDK dependency.
    # Override only when migrating to a different provider.
    email_api_endpoint: str = "https://api.resend.com/emails"

    # -- derived / validated -------------------------------------------------

    @model_validator(mode="after")
    def _apply_environment_contract(self) -> Settings:
        # Normalising here means an unrecognised APP_ENV fails at construction,
        # i.e. at import, i.e. before anything serves a request.
        object.__setattr__(self, "app_env", normalize_app_env(self.app_env))

        if self.database_url is None or not self.database_url.strip():
            if self.is_relaxed:
                object.__setattr__(self, "database_url", DEVELOPMENT_DATABASE_URL)
            else:
                raise ConfigurationError(
                    "DATABASE_URL is required when APP_ENV="
                    f"{self.app_env!r}. Refusing to fall back to the development "
                    "database. Set DATABASE_URL, or set APP_ENV=development for "
                    "local work."
                )
        return self

    @property
    def is_relaxed(self) -> bool:
        """True when developer-convenience defaults are permitted."""
        return self.app_env in RELAXED_APP_ENVS

    @property
    def is_strict(self) -> bool:
        """True for staging and production — everything must be explicit."""
        return not self.is_relaxed

    @property
    def resolved_database_url(self) -> str:
        """`database_url` after the environment contract has been applied."""
        assert self.database_url is not None  # guaranteed by the validator
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
