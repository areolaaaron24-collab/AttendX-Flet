"""Documentation-only entry point for SQLite migration; see scripts/export_sqlite_migration.py."""
from pathlib import Path


def default_legacy_database() -> Path:
    return Path(__file__).resolve().parents[2] / "legacy_sqlite" / "attendance.db"
