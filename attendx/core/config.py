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

    @property
    def is_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    @classmethod
    def from_env(cls) -> "Settings":
        url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        key = (
            os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
            or os.getenv("SUPABASE_ANON_KEY", "").strip()
        )
        return cls(
            supabase_url=url,
            supabase_key=key,
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
    if not settings.is_configured:
        raise ConfigurationError(
            "Supabase is not configured. Copy .env.example to .env and set "
            "SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY."
        )
    if not settings.supabase_url.startswith("https://"):
        raise ConfigurationError("SUPABASE_URL must be the HTTPS URL of your Supabase project.")
    key = settings.supabase_key.strip()
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
