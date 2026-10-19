from __future__ import annotations

from typing import Any
from supabase import Client

from attendx.services.supabase_client import BackendError, query_by_values, query_data, query_paginated, safe_message


class StudentService:
    """Student data adapter for the existing AttendX-Web Supabase schema."""

    def __init__(self, client: Client, student_id: str, profile: dict[str, Any] | None = None):
        self.client = client
        self.student_id = student_id
        self.profile = profile

    def _own_profile(self) -> dict[str, Any]:
        if self.profile:
            profile = self.profile
        else:
            rows = query_data(
                self.client.table("profiles")
                .select("id,role,course,year_level,section,status")
                .eq("id", self.student_id).limit(1)
            )
            if not rows:
                raise BackendError("Your student profile could not be loaded.")
            profile = rows[0]
            self.profile = profile
        if str(profile.get("role", "")).lower() != "student":
            raise BackendError("This portal requires a student account.")
        if str(profile.get("status", "ACTIVE")).upper() in {"INACTIVE", "DROPPED"}:
            raise BackendError("This student account is inactive or dropped.")
        return profile

    def available_schedules(self) -> list[dict[str, Any]]:
        enrolled = self.enrolled_schedule_ids()
        rows = query_paginated(
            lambda: self.client.table("schedules").select("*").eq("status", "ACTIVE")
            .order("day").order("start_time").order("id"), max_items=10_000
        )
        profile = self._own_profile()
        rows = [row for row in rows if str(row["id"]) not in enrolled]
        rows = self._enrich(rows)
        return [
            row for row in rows
            if str(row.get("course", "")).strip().casefold() == str(profile.get("course", "")).strip().casefold()
            and str(row.get("year_level", "")).strip().casefold() == str(profile.get("year_level", "")).strip().casefold()
            and str(row.get("section", "")).strip().casefold() == str(profile.get("section", "")).strip().casefold()
        ]

    def enrolled_schedule_ids(self) -> set[str]:
        rows = query_paginated(
            lambda: self.client.table("enrollments").select("schedule_id")
            .eq("student_id", self.student_id).order("schedule_id"), max_items=10_000
        )
        return {str(row["schedule_id"]) for row in rows}

    def my_schedules(self) -> list[dict[str, Any]]:
        enrollments = query_paginated(
            lambda: self.client.table("enrollments").select("schedule_id,joined_at")
            .eq("student_id", self.student_id).order("joined_at", desc=True).order("schedule_id"),
            max_items=10_000
        )
        ids = [str(row["schedule_id"]) for row in enrollments]
        if not ids:
            return []
        rows = query_by_values(self.client, "schedules", "*", "id", ids)
        rows.sort(key=lambda row: (row.get("day") or "", row.get("start_time") or ""))
        return self._enrich(rows)

    def enroll(self, schedule_id: str) -> None:
        try:
            self.client.table("enrollments").insert({
                "student_id": self.student_id, "schedule_id": str(schedule_id),
            }).execute()
        except Exception as exc:
            message = safe_message(exc)
            if "duplicate" in message.lower() or "23505" in message:
                raise BackendError("You are already enrolled in this subject/class.") from exc
            raise BackendError(f"Could not enroll in the selected subject: {message}") from exc

    def unenroll(self, schedule_id: str) -> None:
        try:
            rows = (self.client.table("enrollments").delete()
                    .eq("student_id", self.student_id).eq("schedule_id", str(schedule_id))
                    .select("id").execute().data or [])
            if not rows:
                raise BackendError("Enrollment not found or removal is not permitted.")
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(f"Could not remove subject: {safe_message(exc)}") from exc

    def attendance_records(self, limit: int = 500) -> list[dict[str, Any]]:
        bounded_limit = min(max(int(limit), 1), 10_000)
        records = query_paginated(
            lambda: self.client.table("attendance").select("*").eq("student_id", self.student_id)
            .order("attendance_date", desc=True).order("attendance_time", desc=True).order("id"),
            max_items=bounded_limit,
        )
        schedule_ids = list({str(row["schedule_id"]) for row in records if row.get("schedule_id") is not None})
        schedules = query_by_values(self.client, "schedules", "*", "id", schedule_ids) if schedule_ids else []
        schedules = self._enrich(schedules)
        schedule_map = {str(row["id"]): row for row in schedules}
        for row in records:
            row["schedule"] = schedule_map.get(str(row.get("schedule_id")), {})
        return records

    def attendance_summary(self) -> dict[str, Any]:
        records = self.attendance_records(limit=10_000)
        total = len(records)
        statuses = [str(row.get("status", "")).upper().replace("-", "_") for row in records]
        present = sum(status == "PRESENT" for status in statuses)
        late = sum(status == "LATE" for status in statuses)
        late_absent = sum(status == "LATE_ABSENT" for status in statuses)
        absent = sum(status == "ABSENT" for status in statuses)
        attended = present + late
        pct = attended / total * 100 if total else 0.0
        return {"total": total, "present": present, "late": late, "late_absent": late_absent,
                "absent": absent, "attended": attended, "percentage": round(pct, 1)}

    def _enrich(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        teacher_ids = list({str(row["teacher_id"]) for row in rows if row.get("teacher_id")})
        teachers = query_by_values(
            self.client, "attendx_teacher_directory",
            "id,first_name,middle_name,last_name,suffix,department", "id", teacher_ids
        ) if teacher_ids else []
        tmap = {str(row["id"]): row for row in teachers}
        for row in rows:
            subject_name = str(row.get("subject") or "")
            row["class"] = {
                "course": row.get("course", ""),
                "year_level": row.get("year_level", ""),
                "section": row.get("section", ""),
            }
            row["subject"] = {"name": subject_name, "subject_name": subject_name}
            row["teacher"] = tmap.get(str(row.get("teacher_id")), {})
            row["is_active"] = str(row.get("status", "")).upper() == "ACTIVE"
        return rows
