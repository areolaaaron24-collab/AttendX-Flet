from __future__ import annotations

import pytest

from attendx.core.config import ConfigurationError, Settings, validate_public_key
from attendx.services.auth_service import account_email


def test_account_email_matches_existing_web_algorithm() -> None:
    # FNV-1a hash and slug format used by AttendX-Web src/app.js.
    assert account_email("  CS-001  ") == account_email("cs-001")
    assert account_email("Aaron Areola").endswith("@attendx.example.com")
    assert account_email("Aaron Areola").startswith("ax-aaron-areola-")


def test_settings_prefers_legacy_anon_key_for_python_auth(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://ligzoiktrdwcdqpkaudr.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "legacy-anon-public-key")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_public-key")

    settings = Settings.from_env()

    assert settings.supabase_key == "legacy-anon-public-key"
    assert settings.supabase_publishable_key == "sb_publishable_public-key"
    validate_public_key(settings)


def test_publishable_key_alone_gives_actionable_auth_setup_error() -> None:
    settings = Settings(
        supabase_url="https://ligzoiktrdwcdqpkaudr.supabase.co",
        supabase_key="sb_publishable_public-key",
        supabase_publishable_key="sb_publishable_public-key",
    )

    with pytest.raises(ConfigurationError, match="SUPABASE_ANON_KEY"):
        validate_public_key(settings)


def test_service_role_key_is_rejected() -> None:
    settings = Settings(
        supabase_url="https://ligzoiktrdwcdqpkaudr.supabase.co",
        supabase_key="service_role",
    )

    with pytest.raises(ConfigurationError, match="service-role"):
        validate_public_key(settings)
