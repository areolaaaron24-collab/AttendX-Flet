from __future__ import annotations

from typing import Any
from supabase import Client

from attendx.core.validators import normalize_name, normalize_sex
from attendx.services.supabase_client import BackendError, safe_message


class ProfileService:
    EDITABLE_COMMON = {"first_name", "last_name", "middle_name", "suffix", "sex"}

    def __init__(self, client: Client):
        self.client = client

    def get(self, user_id: str) -> dict[str, Any]:
        try:
            rows = self.client.table("profiles").select("*").eq("id", user_id).limit(1).execute().data or []
            if not rows:
                raise BackendError("Profile not found or not permitted.")
            return rows[0]
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(f"Could not load profile: {safe_message(exc)}") from exc

    def update_own(self, user_id: str, role: str, changes: dict[str, Any]) -> dict[str, Any]:
        role = role.upper()
        allowed = set(self.EDITABLE_COMMON)
        if role == "STUDENT":
            allowed |= {"course", "year_level", "section"}
        elif role == "TEACHER":
            allowed |= {"department", "office"}
        clean: dict[str, Any] = {}
        for key, value in changes.items():
            if key not in allowed:
                continue
            if key == "sex":
                clean[key] = normalize_sex(value)
            elif key == "first_name":
                clean[key] = normalize_name(value, "First Name")
            elif key == "last_name":
                clean[key] = normalize_name(value, "Last Name")
            elif key == "middle_name":
                clean[key] = normalize_name(value, "Middle Name", False) or ""
            elif key == "suffix":
                clean[key] = normalize_name(value, "Suffix/Extension", False) or ""
            else:
                clean[key] = " ".join(str(value or "").strip().split()) or None
        if not clean:
            raise BackendError("No editable profile fields were supplied.")
        try:
            rows = self.client.table("profiles").update(clean).eq("id", user_id).execute().data or []
            return rows[0] if rows else self.get(user_id)
        except Exception as exc:
            raise BackendError(f"Profile update failed: {safe_message(exc)}") from exc
