"""WS8.2 / R7 — the environment contract, tested adversarially.

Gap B3: `database_url` carried a development default, so an API booted without
`DATABASE_URL` silently pointed at `humanoid:humanoid@localhost` rather than
failing. Closing that is easy; closing it *safely* is the interesting part.

The failure mode worth designing against is not "production forgot a variable".
It is **"production was misclassified as development"** — because that
re-enables every convenience default at once. So the tests below spend most of
their effort on the classifier itself: unset, empty, whitespace, wrong case,
near-misses, and plausible typos must never resolve to a relaxed environment.
"""
from __future__ import annotations

import pytest

from app.config import (
    ALLOWED_APP_ENVS,
    DEVELOPMENT_DATABASE_URL,
    RELAXED_APP_ENVS,
    ConfigurationError,
    Settings,
    normalize_app_env,
)

EXPLICIT_URL = "postgresql+psycopg://user:pw@db.internal:5432/humanoidonline"


def _settings(monkeypatch, **env) -> Settings:
    """Construct Settings from a controlled environment only."""
    for key in ("APP_ENV", "DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


# ---- the classifier: fail safe in BOTH directions -------------------------


def test_unset_environment_is_production_never_development():
    """The whole point. An absent variable must not unlock dev defaults."""
    assert normalize_app_env(None) == "production"
    assert normalize_app_env("") == "production"
    assert normalize_app_env("   ") == "production"


@pytest.mark.parametrize(
    "typo",
    [
        "developmnt",   # transposed
        "developement", # doubled
        "dev",          # abbreviation
        "devel",
        "local",
        "prod",         # plausible but not in the allowlist
        "prd",
        "stage",
        "testing",
        "Production ",  # trailing space + case, but 'production' is valid...
    ],
)
def test_unrecognised_environment_raises_rather_than_guessing(typo):
    """A typo must be loud. Silently treating it as production would also be
    'safe', but it would hide a real misconfiguration until something subtler
    broke; silently treating it as development would be a disaster."""
    if typo.strip().lower() in ALLOWED_APP_ENVS:
        assert normalize_app_env(typo) == typo.strip().lower()
        return
    with pytest.raises(ConfigurationError) as exc:
        normalize_app_env(typo)
    assert "not a recognised environment" in str(exc.value)


def test_no_typo_can_reach_a_relaxed_environment():
    """Exhaustive-ish: nothing outside the allowlist may be classified relaxed."""
    for candidate in ("developmnt", "dev", "prod", "", None, "PRODUCTION", "TEST"):
        try:
            resolved = normalize_app_env(candidate)
        except ConfigurationError:
            continue  # loud failure is an acceptable outcome
        if candidate is not None and candidate.strip().lower() in RELAXED_APP_ENVS:
            assert resolved in RELAXED_APP_ENVS
        else:
            assert resolved not in RELAXED_APP_ENVS, (candidate, resolved)


def test_case_is_normalised_for_recognised_values():
    assert normalize_app_env("PRODUCTION") == "production"
    assert normalize_app_env(" Development ") == "development"


# ---- B3: no silent development database in a strict environment -----------


def test_production_without_database_url_refuses_to_start(monkeypatch):
    with pytest.raises(ConfigurationError) as exc:
        _settings(monkeypatch)  # nothing set at all -> production
    message = str(exc.value)
    assert "DATABASE_URL is required" in message
    # Actionable: it says what to do, not just what went wrong.
    assert "APP_ENV=development" in message


def test_staging_without_database_url_also_refuses(monkeypatch):
    with pytest.raises(ConfigurationError):
        _settings(monkeypatch, APP_ENV="staging")


def test_production_never_falls_back_to_the_development_database(monkeypatch):
    """The specific B3 regression: the dev URL must be unreachable in strict envs."""
    with pytest.raises(ConfigurationError):
        _settings(monkeypatch, APP_ENV="production")
    explicit = _settings(monkeypatch, APP_ENV="production", DATABASE_URL=EXPLICIT_URL)
    assert explicit.resolved_database_url == EXPLICIT_URL
    assert explicit.resolved_database_url != DEVELOPMENT_DATABASE_URL


def test_blank_database_url_is_treated_as_absent(monkeypatch):
    with pytest.raises(ConfigurationError):
        _settings(monkeypatch, APP_ENV="production", DATABASE_URL="   ")


@pytest.mark.parametrize("env", sorted(RELAXED_APP_ENVS))
def test_relaxed_environments_keep_the_convenience_default(env, monkeypatch):
    settings = _settings(monkeypatch, APP_ENV=env)
    assert settings.resolved_database_url == DEVELOPMENT_DATABASE_URL
    assert settings.is_relaxed and not settings.is_strict


@pytest.mark.parametrize("env", ["staging", "production"])
def test_strict_environments_are_flagged_strict(env, monkeypatch):
    settings = _settings(monkeypatch, APP_ENV=env, DATABASE_URL=EXPLICIT_URL)
    assert settings.is_strict and not settings.is_relaxed


def test_explicit_url_always_wins_even_in_development(monkeypatch):
    settings = _settings(monkeypatch, APP_ENV="development", DATABASE_URL=EXPLICIT_URL)
    assert settings.resolved_database_url == EXPLICIT_URL


def test_unrecognised_app_env_fails_at_settings_construction(monkeypatch):
    """Not just the helper — the whole Settings object must refuse to build,
    which is what makes this a boot failure rather than a latent bug."""
    with pytest.raises(ConfigurationError):
        _settings(monkeypatch, APP_ENV="developmnt", DATABASE_URL=EXPLICIT_URL)
