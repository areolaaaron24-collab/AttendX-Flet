from __future__ import annotations

import re
from dataclasses import dataclass


class ValidationError(ValueError):
    """A user-correctable input error."""


def normalize_spaces(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def normalize_account_id(value: str | None) -> str:
    result = normalize_spaces(value)
    if not result:
        raise ValidationError("Account ID is required.")
    if len(result) > 64:
        raise ValidationError("Account ID must be 64 characters or fewer.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", result):
        raise ValidationError("Use letters, numbers, dot, underscore, or hyphen for the Account ID.")
    return result.lower()


def normalize_name(value: str | None, label: str, required: bool = True) -> str | None:
    result = normalize_spaces(value)
    if required and not result:
        raise ValidationError(f"{label} is required.")
    if not required and not result:
        return None
    if any(ch.isdigit() for ch in result):
        raise ValidationError(f"{label} must not contain numbers.")
    if len(result) > 80:
        raise ValidationError(f"{label} must be 80 characters or fewer.")
    return result


def normalize_sex(value: str | None) -> str:
    result = normalize_spaces(value).title()
    if result not in {"Male", "Female"}:
        raise ValidationError("Select Male or Female.")
    return result


def validate_password(password: str, confirm: str | None = None) -> str:
    if len(password or "") < 8:
        raise ValidationError("Password must contain at least 8 characters.")
    if len(password) > 128:
        raise ValidationError("Password must be 128 characters or fewer.")
    if confirm is not None and password != confirm:
        raise ValidationError("Passwords do not match.")
    return password


def validate_recovery_email(value: str | None) -> str | None:
    result = normalize_spaces(value)
    if not result:
        return None
    if len(result) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", result):
        raise ValidationError("Enter a valid recovery email address, or leave it blank.")
    return result.lower()


def validate_time_range(start_time: str, end_time: str) -> tuple[str, str]:
    pattern = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$")
    if not pattern.fullmatch(start_time or "") or not pattern.fullmatch(end_time or ""):
        raise ValidationError("Enter times in 24-hour HH:MM format.")
    start = start_time[:5]
    end = end_time[:5]
    if end <= start:
        raise ValidationError("End time must be later than start time. Overnight schedules are not supported.")
    return start, end


@dataclass(frozen=True)
class RegistrationData:
    account_id: str
    role: str
    password: str
    first_name: str
    last_name: str
    middle_name: str | None
    suffix: str | None
    sex: str
    recovery_email: str | None = None
    course: str | None = None
    year_level: str | None = None
    section: str | None = None
    department: str | None = None
    office: str | None = None

    @classmethod
    def build(cls, **values: str | None) -> "RegistrationData":
        role = normalize_spaces(values.get("role")).upper()
        if role not in {"TEACHER", "STUDENT"}:
            raise ValidationError("Only Teacher and Student accounts are allowed.")
        password = validate_password(values.get("password") or "", values.get("confirm_password"))
        common = dict(
            account_id=normalize_account_id(values.get("account_id")),
            role=role,
            password=password,
            first_name=normalize_name(values.get("first_name"), "First Name"),
            last_name=normalize_name(values.get("last_name"), "Last Name"),
            middle_name=normalize_name(values.get("middle_name"), "Middle Name", False),
            suffix=normalize_name(values.get("suffix"), "Suffix/Extension", False),
            sex=normalize_sex(values.get("sex")),
            recovery_email=validate_recovery_email(values.get("recovery_email")),
        )
        if role == "STUDENT":
            common.update(
                course=normalize_spaces(values.get("course")),
                year_level=normalize_spaces(values.get("year_level")),
                section=normalize_spaces(values.get("section")),
            )
            if not common["course"] or not common["year_level"] or not common["section"]:
                raise ValidationError("Course, Year, and Section are required for students.")
        else:
            common.update(
                department=normalize_spaces(values.get("department")) or None,
                office=normalize_spaces(values.get("office")) or None,
            )
        return cls(**common)
