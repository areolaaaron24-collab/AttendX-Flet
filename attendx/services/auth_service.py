from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

import httpx

from attendx.core.config import Settings
from attendx.core.validators import RegistrationData
from attendx.services.supabase_client import BackendError, safe_message

log = logging.getLogger(__name__)


def account_email(account_id: str) -> str:
    """Match accountEmail() from the existing AttendX-Web src/app.js."""
    normalized = " ".join(str(account_id or "").strip().split())[:40].lower()
    value = 2166136261
    for character in normalized:
        value ^= ord(character)
        value = (value * 16777619) & 0xFFFFFFFF

    slug = unicodedata.normalize("NFKD", normalized)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"^-+|-+$", "", slug)[:36] or "account"

    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    number = value
    encoded = "0" if number == 0 else ""
    while number:
        number, remainder = divmod(number, 36)
        encoded = digits[remainder] + encoded

    return f"ax-{slug}-{encoded}@attendx.example.com"


def _member(obj: Any, name: str) -> Any:
    """Read SDK fields across supported response object shapes."""
    if isinstance(obj, dict):
        if name in obj:
            return obj[name]
        data = obj.get("data")
        if isinstance(data, dict):
            return data.get(name)
        return getattr(data, name, None)

    value = getattr(obj, name, None)
    if value is not None:
        return value

    data = getattr(obj, "data", None)
    if isinstance(data, dict):
        return data.get(name)
    return getattr(data, name, None)


class AuthService:
    """Authentication adapter for the existing AttendX-Web Supabase project."""

    def __init__(self, client, settings: Settings):
        self.client = client
        self.settings = settings

    def _invoke(self, function_name: str, body: dict[str, Any]) -> dict[str, Any]:
        url = (
            self.settings.supabase_url.rstrip("/")
            + "/functions/v1/"
            + function_name
        )
        # Use the publishable key for Edge Functions where configured; Auth/PostgREST
        # uses the legacy anon key through the Supabase Python client.
        key = self.settings.supabase_publishable_key or self.settings.supabase_key
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

        try:
            response = httpx.post(
                url,
                headers=headers,
                json=body,
                timeout=httpx.Timeout(25.0, connect=8.0),
            )
            try:
                payload = response.json()
            except ValueError:
                payload = {}

            if response.status_code >= 400:
                message = (
                    payload.get("error")
                    or payload.get("message")
                    or f"AttendX server returned HTTP {response.status_code}."
                )
                raise BackendError(str(message)[:500])

            if not isinstance(payload, dict):
                raise BackendError("AttendX returned an invalid server response.")
            return payload

        except BackendError:
            raise
        except httpx.TimeoutException as exc:
            raise BackendError(
                "AttendX server timed out. Check internet connectivity and retry."
            ) from exc
        except httpx.HTTPError as exc:
            raise BackendError(
                f"Cannot reach AttendX Supabase: {safe_message(exc)}"
            ) from exc

    def register(
        self,
        data: RegistrationData,
        teacher_invite_code: str = "",
    ) -> dict[str, Any]:
        role = str(data.role).upper()
        if role not in {"TEACHER", "STUDENT"}:
            raise BackendError("Only Teacher and Student accounts are allowed.")

        invite_code = (teacher_invite_code or "").strip()
        if role == "TEACHER" and not invite_code:
            raise BackendError(
                "Enter the teacher invitation code from the AttendX administrator."
            )

        payload = {
            "accountId": data.account_id,
            "role": role.lower(),
            "password": data.password,
            "firstName": data.first_name,
            "lastName": data.last_name,
            "middleName": data.middle_name or "",
            "suffix": data.suffix or "",
            "sex": data.sex,
            "teacherInviteCode": invite_code,
            "course": data.course or "",
            "year": data.year_level or "",
            "section": data.section or "",
            "department": data.department or "",
            "office": data.office or "",
        }

        result = self._invoke("account-register", payload)
        if result.get("ok") is not True:
            raise BackendError(
                str(result.get("error") or result.get("message")
                    or "AttendX did not confirm account creation.")
            )

        # Existing account-register returns {ok, accountId, message};
        # it does not return an authenticated session.
        try:
            return self.login(data.account_id, data.password, role)
        except Exception as exc:
            raise BackendError(
                "The server confirmed account creation, but sign-in failed. "
                "Do not register the same account again. Try Sign In with the "
                "same Account ID and password. Details: " + safe_message(exc)
            ) from exc

    def login(
        self,
        account_id: str,
        password: str,
        role: str,
    ) -> dict[str, Any]:
        expected_role = str(role).upper()
        if expected_role not in {"TEACHER", "STUDENT"}:
            raise BackendError("Only Teacher and Student portals are supported.")

        try:
            # Do not call a nonexistent account-id-login Edge Function.
            # The existing Web app derives this internal email and signs in directly.
            response = self.client.auth.sign_in_with_password({
                "email": account_email(account_id),
                "password": password,
            })

            session = _member(response, "session")
            user = _member(response, "user")

            # Some SDK versions expose the current session through get_session().
            if session is None:
                try:
                    current = self.client.auth.get_session()
                    session = _member(current, "session")
                    if session is None and getattr(current, "access_token", None):
                        session = current
                except Exception:
                    session = None

            if session is None:
                raise BackendError(
                    "Supabase Auth returned no session. Verify the Account ID, "
                    "password, confirmed account status, and Supabase Auth response."
                )

            user_id = _member(user, "id") if user is not None else None
            if not user_id:
                user_id = _member(_member(session, "user"), "id")

            # Fetch the user from Auth if the sign-in response didn't expose its ID.
            if not user_id:
                try:
                    user_response = self.client.auth.get_user()
                    user_obj = _member(user_response, "user")
                    user_id = _member(user_obj, "id") if user_obj is not None else None
                except Exception:
                    user_id = None

            if not user_id:
                raise BackendError(
                    "A session was returned, but the authenticated user ID is missing."
                )

            result = (
                self.client.table("profiles")
                .select("*")
                .eq("id", str(user_id))
                .limit(1)
                .execute()
            )
            profiles = result.data or []
            if not profiles:
                raise BackendError(
                    "Sign-in succeeded, but no readable profile was found. "
                    "Check that this Auth user has a matching profiles row "
                    "and that the existing Supabase RLS policy permits reading it."
                )

            profile = dict(profiles[0])
            actual_role = str(profile.get("role", "")).upper()
            if actual_role != expected_role:
                self.sign_out()
                raise BackendError(
                    "This account belongs to a different portal. Select the "
                    "correct Teacher or Student portal."
                )

            status = str(profile.get("status") or "ACTIVE").upper()
            if status in {"INACTIVE", "DROPPED"}:
                self.sign_out()
                raise BackendError(
                    "This account is inactive or dropped. Contact the AttendX administrator."
                )

            # Flet controller uses uppercase role names; the database stores lowercase.
            profile["role"] = actual_role
            return profile

        except BackendError:
            raise
        except Exception as exc:
            message = safe_message(exc)
            if "invalid api key" in message.lower() or ("401" in message and "api key" in message.lower()):
                raise BackendError(
                    "Supabase rejected the client API key. In the existing Supabase project, "
                    "copy the legacy anon/public key from Project Settings → API Keys into "
                    "SUPABASE_ANON_KEY in your local .env. Do not use service_role or sb_secret keys."
                ) from exc
            if "invalid login credentials" in message.lower():
                raise BackendError(
                    "Invalid Account ID or password. If the account was just "
                    "created, try signing in again rather than registering again."
                ) from exc
            log.warning("AttendX login failed: %s", message)
            raise BackendError(f"AttendX sign-in failed: {message}") from exc

    def request_password_reset(self, account_id: str, role: str) -> None:
        raise BackendError(
            "Automatic password recovery isn't configured for the existing "
            "AttendX-Web accounts. Ask the administrator to recover this account."
        )

    def update_password(self, new_password: str) -> None:
        try:
            self.client.auth.update_user({"password": new_password})
        except Exception as exc:
            raise BackendError(f"Password update failed: {safe_message(exc)}") from exc

    def sign_out(self) -> None:
        try:
            self.client.auth.sign_out()
        except Exception:
            log.exception("Supabase sign-out encountered an error")