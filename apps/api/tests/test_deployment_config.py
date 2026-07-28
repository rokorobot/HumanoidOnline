"""WS8.7 / R26 + R27 — the deployment configuration is asserted, not assumed.

The frozen DEP is realized by configuration, so configuration is where it can
silently regress. In particular the public listener's `/admin*` 404 rule is
**load-bearing**: with the admin surface mounted on the single FastAPI instance
(DEP P2 forbids a second one), a typo in that rule would expose the admin login
to the public internet. A comment cannot prevent that; this test can.

These are static checks on committed files — they need no Docker, no network and
no VPS, so they run in ordinary CI. They do **not** replace R27 (the boundary
physically realized and human-attested) or R29 (the external probe from outside
the deployment); they stop the config drifting between those gates.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
CADDYFILE = ROOT / "deploy" / "Caddyfile"
COMPOSE = ROOT / "docker-compose.prod.yml"
API_DOCKERFILE = ROOT / "apps" / "api" / "Dockerfile"
ENV_EXAMPLE = ROOT / ".env.production.example"

#: Caddy's statically assigned address on the production network. This exact
#: value is what FastAPI sees as the ASGI peer, so it is what DEP P1 trusts.
CADDY_ADDRESS = "172.30.0.2"


def _read(path: pathlib.Path) -> str:
    if not path.exists():  # pragma: no cover - guards a rename/move
        pytest.fail(f"missing deployment artifact: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _block(source: str, opener: str) -> str:
    """Return the text inside the brace-block introduced by ``opener``."""
    start = source.index(opener) + len(opener)
    depth = 1
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index]
    raise AssertionError(f"unbalanced braces after {opener!r}")


@pytest.fixture(scope="module")
def caddyfile() -> str:
    return _read(CADDYFILE)


@pytest.fixture(scope="module")
def public_listener(caddyfile: str) -> str:
    return _block(caddyfile, "{$SITE_DOMAIN} {")


@pytest.fixture(scope="module")
def admin_listener(caddyfile: str) -> str:
    return _block(caddyfile, ":8001 {")


# --------------------------------------------------------------------------- #
# DEP P4 — the admin boundary
# --------------------------------------------------------------------------- #
def test_public_listener_refuses_admin(public_listener: str) -> None:
    """The public ingress must not route /admin* — it answers 404 itself.

    The single `/admin*` prefix also covers SQLAdmin's assets: it mounts at
    base_url="/admin" and serves files from "/admin/statics/*".
    """
    handle = _block(public_listener, "handle /admin* {")
    assert "respond 404" in handle
    assert "reverse_proxy" not in handle, "public /admin must never proxy anywhere"


def test_admin_is_reachable_only_on_the_protected_listener(
    admin_listener: str,
) -> None:
    assert "handle /admin* {" in admin_listener
    assert "import to_api" in _block(admin_listener, "handle /admin* {")


def test_admin_listener_is_published_on_loopback_only() -> None:
    compose = _read(COMPOSE)
    assert '"127.0.0.1:8001:8001"' in compose, (
        "the admin listener must bind host loopback only; a bare 8001:8001 "
        "would publish it on every interface"
    )
    assert '"8001:8001"' not in compose


def _service_of(compose_lines: list[str], index: int) -> str:
    """Name of the compose service that the given line belongs to."""
    for line in reversed(compose_lines[: index + 1]):
        if line.startswith("  ") and not line.startswith("   ") and line.rstrip().endswith(":"):
            return line.strip().rstrip(":")
    return "<unknown>"


def test_only_caddy_publishes_ports() -> None:
    """API, web and database must be unreachable except through the proxy."""
    lines = _read(COMPOSE).splitlines()
    publishing = {
        _service_of(lines, i)
        for i, line in enumerate(lines)
        if line.strip() == "ports:"
    }
    assert publishing == {"caddy"}, (
        f"only the proxy may publish host ports; found: {sorted(publishing)}"
    )


# --------------------------------------------------------------------------- #
# DEP P1 — trusted ingress
# --------------------------------------------------------------------------- #
def test_forwarded_for_is_replaced_not_appended(caddyfile: str) -> None:
    """A client-supplied X-Forwarded-For must never survive to the API."""
    assert "header_up X-Forwarded-For {remote_host}" in caddyfile


def test_trusted_proxy_is_exactly_the_caddy_address() -> None:
    env = _read(ENV_EXAMPLE)
    assert f"TRUSTED_PROXY_IPS={CADDY_ADDRESS}/32" in env, (
        "DEP P1 trusts exactly the proxy's address on the production network — "
        "not the VPS public IP and not a broad CIDR"
    )
    compose = _read(COMPOSE)
    assert f"ipv4_address: {CADDY_ADDRESS}" in compose


def test_uvicorn_does_not_interpret_proxy_headers() -> None:
    """resolve_client_ip() must remain the sole trust authority (DEP P1)."""
    dockerfile = _read(API_DOCKERFILE)
    assert '"--no-proxy-headers"' in dockerfile
    # The name may appear in a comment (it is documented as forbidden); what must
    # never appear is an actual assignment enabling it.
    directives = [
        line for line in dockerfile.splitlines() if not line.lstrip().startswith("#")
    ]
    assert not any("FORWARDED_ALLOW_IPS" in line for line in directives), (
        "FORWARDED_ALLOW_IPS would let uvicorn rewrite the peer address from a "
        "forwarding header, defeating DEP P1"
    )
    compose = _read(COMPOSE)
    assert "FORWARDED_ALLOW_IPS" not in compose


# --------------------------------------------------------------------------- #
# DEP P2 / P3 — singleton application instance
# --------------------------------------------------------------------------- #
def test_single_api_instance_and_worker() -> None:
    dockerfile = _read(API_DOCKERFILE)
    assert '"--workers", "1"' in dockerfile
    compose = _read(COMPOSE)
    assert "deploy:" not in compose and "replicas:" not in compose, (
        "DEP P2 freezes a singleton FastAPI instance for MVP v0.1; replication "
        "invalidates the process-local abuse-control state (P3)"
    )


# --------------------------------------------------------------------------- #
# Startup ordering + HSTS placement
# --------------------------------------------------------------------------- #
def test_migrations_gate_application_start() -> None:
    compose = _read(COMPOSE)
    assert "service_completed_successfully" in compose
    assert "db/bootstrap.py" in compose, (
        "the migrate step must run the ONE governed bootstrap path (R10 / D6)"
    )


def test_hsts_on_public_surface_but_never_on_the_loopback_admin(
    public_listener: str, admin_listener: str
) -> None:
    assert "Strict-Transport-Security" in public_listener
    assert "Strict-Transport-Security" not in admin_listener, (
        "advertising HSTS over http://127.0.0.1 would poison the operator's "
        "browser for all of localhost"
    )


# --------------------------------------------------------------------------- #
# Secrets hygiene
# --------------------------------------------------------------------------- #
def test_env_template_ships_no_values_for_secrets() -> None:
    env = _read(ENV_EXAMPLE)
    for key in (
        "POSTGRES_PASSWORD",
        "ADMIN_USERNAME",
        "ADMIN_PASSWORD",
        "ADMIN_SESSION_SECRET",
        "ACME_EMAIL",
        "RELEASE_SHA",
    ):
        for line in env.splitlines():
            if line.startswith(f"{key}="):
                value = line.split("=", 1)[1].split("#", 1)[0].strip()
                assert value == "", f"{key} must ship empty in the template"


# --------------------------------------------------------------------------- #
# Automatic HTTPS on the public surface (review blocker 1)
# --------------------------------------------------------------------------- #
def test_automatic_https_redirects_are_not_globally_disabled(caddyfile: str) -> None:
    """A global `auto_https disable_redirects` would switch off the automatic
    HTTP->HTTPS redirect for the PUBLIC site too, leaving a plain-HTTP entry
    point on the internet. The admin listener does not need it: a bare-port site
    address (`:8001`) is served over HTTP without Caddy attempting ACME."""
    directives = [
        line for line in caddyfile.splitlines() if not line.lstrip().startswith("#")
    ]
    body = "\n".join(directives)
    assert "auto_https" not in body, (
        "automatic HTTPS (and its HTTP->HTTPS redirect) must stay enabled for the "
        "public site"
    )
    assert "disable_redirects" not in body


def test_admin_listener_is_a_bare_port_so_it_stays_plain_http(
    caddyfile: str, admin_listener: str
) -> None:
    """Plain HTTP on loopback is intentional — SSH provides the channel — and it
    must be achieved by addressing, not by weakening global TLS behaviour."""
    assert "\n:8001 {" in caddyfile, "admin site address must be a bare port"
    assert "tls " not in admin_listener
    # Re-asserted here so the two halves of blocker 1 fail independently.
    assert "Strict-Transport-Security" not in admin_listener


# --------------------------------------------------------------------------- #
# Readiness wired INTO the ingress (review blocker 4)
# --------------------------------------------------------------------------- #
def test_ingress_actively_health_checks_the_api_readiness_endpoint(
    caddyfile: str,
) -> None:
    """Exposing /ready is not the same as using it: Caddy must poll it and take
    the upstream out of rotation when a dependency (Postgres) is down."""
    proxy = _block(caddyfile, "(to_api) {")
    assert "health_uri /ready" in proxy, "ingress must probe /ready, not just /health"
    assert "health_interval" in proxy and "health_timeout" in proxy, (
        "health checking must be bounded"
    )
    assert "health_status 2xx" in proxy


def test_liveness_and_readiness_keep_their_distinct_roles() -> None:
    """/health stays dependency-free liveness (container HEALTHCHECK); /ready is
    the dependency-aware probe the proxy uses."""
    dockerfile = _read(API_DOCKERFILE)
    directives = [
        line for line in dockerfile.splitlines() if not line.lstrip().startswith("#")
    ]
    body = chr(10).join(directives)
    assert "/health" in body, "container liveness probe should use /health"
    assert "/ready" not in body, (
        "the container HEALTHCHECK must not depend on the database"
    )
    caddyfile = _read(CADDYFILE)
    assert "handle /ready" in caddyfile and "handle /health" in caddyfile


def test_public_ingress_starts_only_after_the_application_is_healthy() -> None:
    """Ingress must not accept traffic before the API passed its own startup
    checks — which include the migration-state verification (WS8.2 / R9)."""
    lines = _read(COMPOSE).splitlines()
    started = [
        i for i, line in enumerate(lines) if line.strip() == "condition: service_started"
    ]
    offenders = {_service_of(lines, i) for i in started}
    assert offenders == set(), (
        f"these services start before their dependency is healthy: {sorted(offenders)}"
    )
    compose = _read(COMPOSE)
    # The migrate gate itself is unchanged.
    assert "service_completed_successfully" in compose


# --------------------------------------------------------------------------- #
# Base-image pinning fails closed (review blocker 2)
# --------------------------------------------------------------------------- #
def test_build_args_have_no_mutable_default_base_image() -> None:
    """A default like `python:3.12-slim` would let a production build succeed
    against whatever that tag points at today."""
    for path, arg in (
        (API_DOCKERFILE, "PYTHON_IMAGE"),
        (ROOT / "apps" / "web" / "Dockerfile", "NODE_IMAGE"),
    ):
        source = _read(path)
        declarations = [
            line.strip()
            for line in source.splitlines()
            if line.strip().startswith(f"ARG {arg}")
        ]
        assert declarations == [f"ARG {arg}"], (
            f"{arg} must be declared with NO default, got: {declarations}"
        )


def test_compose_requires_explicit_runtime_image_pins() -> None:
    compose = _read(COMPOSE)
    for var in ("POSTGRES_IMAGE", "CADDY_IMAGE"):
        assert f"${{{var}:?" in compose, (
            f"{var} must be a REQUIRED compose variable (`:?`), not a default"
        )
        assert f"${{{var}:-" not in compose, f"{var} must not have a fallback default"


def test_env_template_ships_all_four_image_pins_blank() -> None:
    """Digest examples belong in comments; a real value here would be a mutable
    tag waiting to be shipped."""
    env = _read(ENV_EXAMPLE)
    for key in ("PYTHON_IMAGE", "NODE_IMAGE", "POSTGRES_IMAGE", "CADDY_IMAGE"):
        assigned = [
            line for line in env.splitlines() if line.startswith(f"{key}=")
        ]
        assert assigned == [f"{key}="], f"{key} must ship blank, got: {assigned}"
