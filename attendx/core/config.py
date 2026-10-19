from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    # Legacy public anon key used by supabase-py Auth/PostgREST requests.
    # Do not put a service-role or sb_secret key here.
    supabase_key: str
    timezone: str = "Asia/Manila"
    camera_index: int = 0
    camera_width: int = 640
    camera_height: int = 480
    qr_token_ttl_days: int = 180
    fingerprint_port: str = "COM3"
    fingerprint_baudrate: int = 57600
    fingerprint_address: int = 0xFFFFFFFF
    fingerprint_password: int = 0
    exports_dir: Path = ROOT_DIR / "exports"
    log_level: str = "INFO"
    # Optional publishable key used for Supabase Edge Function requests.
    # Kept at the end to preserve the prior positional Settings constructor.
    supabase_publishable_key: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    @classmethod
    def from_env(cls) -> "Settings":
        url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        # supabase-py in this app is used for /auth/v1/token as well as
        # PostgREST. The existing project’s legacy anon key is required for
        # that flow; a newer sb_publishable_ key caused HTTP 401 Invalid API key.
        anon_key = os.getenv("SUPABASE_ANON_KEY", "").strip()
        publishable_key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
        return cls(
            supabase_url=url,
            supabase_key=anon_key or publishable_key,
            supabase_publishable_key=publishable_key,
            timezone=os.getenv("APP_TIMEZONE", "Asia/Manila").strip() or "Asia/Manila",
            camera_index=_int_env("CAMERA_INDEX", 0),
            camera_width=_int_env("CAMERA_WIDTH", 640),
            camera_height=_int_env("CAMERA_HEIGHT", 480),
            qr_token_ttl_days=max(1, _int_env("QR_TOKEN_TTL_DAYS", 180)),
            fingerprint_port=os.getenv("FINGERPRINT_PORT", "COM3").strip() or "COM3",
            fingerprint_baudrate=_int_env("FINGERPRINT_BAUDRATE", 57600),
            fingerprint_address=_int_env("FINGERPRINT_ADDRESS", 0xFFFFFFFF),
            fingerprint_password=_int_env("FINGERPRINT_PASSWORD", 0),
            exports_dir=Path(os.getenv("EXPORTS_DIR", str(ROOT_DIR / "exports"))).expanduser(),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )


def _int_env(key: str, default: int) -> int:
    try:
        raw = os.getenv(key, "").strip()
        return int(raw, 0) if raw else default
    except ValueError:
        return default


def validate_public_key(settings: Settings) -> None:
    if not settings.supabase_url or not settings.supabase_key:
        raise ConfigurationError(
            "Supabase is not fully configured. In .env, set SUPABASE_URL and "
            "SUPABASE_ANON_KEY using the existing AttendX Supabase project's "
            "Project Settings → API Keys → legacy anon/public key. "
            "SUPABASE_PUBLISHABLE_KEY may also be set for Edge Functions."
        )
    if not settings.supabase_url.startswith("https://"):
        raise ConfigurationError("SUPABASE_URL must be the HTTPS URL of your Supabase project.")

    key = settings.supabase_key.strip()
    # A publishable key is not a replacement for the legacy anon JWT in this
    # supabase-py Auth flow; reject it with a setup message rather than letting
    # account creation succeed and sign-in fail later with HTTP 401.
    if key.startswith("sb_publishable_"):
        raise ConfigurationError(
            "SUPABASE_ANON_KEY is missing. The Python Auth client needs the "
            "existing project's legacy anon/public key. Keep SUPABASE_PUBLISHABLE_KEY "
            "for Edge Functions and add SUPABASE_ANON_KEY to .env."
        )

    is_secret = "service_role" in key.lower() or key.startswith("sb_secret_")
    # Legacy Supabase service-role keys are JWTs whose role is encoded in the
    # payload. Decode only to identify the role; this does not validate the JWT.
    parts = key.split(".")
    if len(parts) == 3:
        try:
            payload = parts[1] + "=" * (-len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
            is_secret = is_secret or claims.get("role") == "service_role"
        except (ValueError, UnicodeError, json.JSONDecodeError):
            pass
    if is_secret:
        raise ConfigurationError(
            "A secret/service-role key was supplied to the client. Use only the publishable/anon key."
        )


class ConfigurationError(RuntimeError):
    """Missing or unsafe application configuration."""
