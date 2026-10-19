from __future__ import annotations

from typing import Any
from supabase import Client

from attendx.services.supabase_client import BackendError, query_by_values, query_data, query_paginated, safe_message


class StudentService:
    def __init__(self, client: Client, student_id: str, profile: dict[str, Any] | None = None):
        self.client = client
        self.student_id = student_id
        self.profile = profile

    def _own_profile(self) -> dict[str, Any]:
        if self.profile:
            return self.profile
        rows = query_data(
            self.client.table("profiles").select("id,role,course,year_level,section,is_active")
            .eq("id", self.student_id).limit(1)
        )
        if not rows or rows[0].get("role") != "STUDENT":
            raise BackendError("Your active student profile could not be loaded.")
        self.profile = rows[0]
        return self.profile

    def available_schedules(self) -> list[dict[str, Any]]:
        enrolled = self.enrolled_schedule_ids()
        rows = query_paginated(
            lambda: self.client.table("schedules").select("*").eq("is_active", True)
            .order("day").order("start_time").order("id"), max_items=10_000
        )
        rows = [r for r in rows if r["id"] not in enrolled]
        rows = self._enrich(rows)
        profile = self._own_profile()
        return [row for row in rows if
                str((row.get("class") or {}).get("course", "")).strip().casefold() == str(profile.get("course", "")).strip().casefold()
                and str((row.get("class") or {}).get("year_level", "")).strip().casefold() == str(profile.get("year_level", "")).strip().casefold()
                and str((row.get("class") or {}).get("section", "")).strip().casefold() == str(profile.get("section", "")).strip().casefold()]

    def enrolled_schedule_ids(self) -> set[str]:
        rows = query_paginated(
            lambda: self.client.table("class_enrollments").select("schedule_id")
            .eq("student_id", self.student_id).order("schedule_id"), max_items=10_000
        )
        return {row["schedule_id"] for row in rows}

    def my_schedules(self) -> list[dict[str, Any]]:
        enrollments = query_paginated(
            lambda: self.client.table("class_enrollments").select("schedule_id,enrolled_at")
            .eq("student_id", self.student_id).order("enrolled_at", desc=True).order("schedule_id"), max_items=10_000
        )
        ids = [row["schedule_id"] for row in enrollments]
        if not ids:
            return []
        rows = query_by_values(self.client, "schedules", "*", "id", ids)
        rows.sort(key=lambda row: (row.get("day") or "", row.get("start_time") or ""))
        return self._enrich(rows)

    def enroll(self, schedule_id: str) -> None:
        try:
            self.client.table("class_enrollments").insert({
                "student_id": self.student_id, "schedule_id": schedule_id,
            }).execute()
        except Exception as exc:
            message = safe_message(exc)
            if "duplicate" in message.lower() or "23505" in message:
                raise BackendError("You are already enrolled in this subject/class.") from exc
            raise BackendError(f"Could not enroll in the selected subject: {message}") from exc

    def unenroll(self, schedule_id: str) -> None:
        try:
            rows = self.client.table("class_enrollments").delete().eq("student_id", self.student_id).eq("schedule_id", schedule_id).select("id").execute().data or []
            if not rows:
                raise BackendError("Enrollment not found or removal is not permitted.")
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(f"Could not remove subject: {safe_message(exc)}") from exc

    def attendance_records(self, limit: int = 500) -> list[dict[str, Any]]:
        bounded_limit = min(max(int(limit), 1), 10_000)
        records = query_paginated(
            lambda: self.client.table("attendance_records").select("*").eq("student_id", self.student_id)
            .order("attendance_date", desc=True).order("attendance_time", desc=True).order("id"),
            max_items=bounded_limit,
        )
        schedule_ids = list({row["schedule_id"] for row in records if row.get("schedule_id") is not None})
        schedules = query_by_values(self.client, "schedules", "*", "id", schedule_ids) if schedule_ids else []
        classes_ids = list({row["class_id"] for row in schedules if row.get("class_id")})
        subject_ids = list({row["subject_id"] for row in schedules if row.get("subject_id")})
        classes = query_by_values(self.client, "classes", "*", "id", classes_ids) if classes_ids else []
        subjects = query_by_values(self.client, "subjects", "*", "id", subject_ids) if subject_ids else []
        cmap = {row["id"]: row for row in classes}
        smap = {row["id"]: row for row in subjects}
        for schedule in schedules:
            schedule["class"] = cmap.get(schedule.get("class_id"), {})
            schedule["subject"] = smap.get(schedule.get("subject_id"), {})
        schedule_map = {row["id"]: row for row in schedules}
        for row in records:
            row["schedule"] = schedule_map.get(row.get("schedule_id"), {})
        return records

    def attendance_summary(self) -> dict[str, Any]:
        records = self.attendance_records(limit=10_000)
        total = len(records)
        present = sum(r.get("status") == "PRESENT" for r in records)
        late = sum(r.get("status") == "LATE" for r in records)
        late_absent = sum(r.get("status") == "LATE_ABSENT" for r in records)
        absent = sum(r.get("status") == "ABSENT" for r in records)
        attended = present + late
        pct = (attended / total * 100) if total else 0.0
        return {"total": total, "present": present, "late": late, "late_absent": late_absent,
                "absent": absent, "attended": attended, "percentage": round(pct, 1)}

    def _enrich(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        class_ids = list({row["class_id"] for row in rows if row.get("class_id")})
        subject_ids = list({row["subject_id"] for row in rows if row.get("subject_id")})
        teacher_ids = list({row["teacher_id"] for row in rows if row.get("teacher_id")})
        classes = query_by_values(self.client, "classes", "*", "id", class_ids) if class_ids else []
        subjects = query_by_values(self.client, "subjects", "*", "id", subject_ids) if subject_ids else []
        teachers = query_by_values(self.client, "teacher_directory", "id,first_name,middle_name,last_name", "id", teacher_ids) if teacher_ids else []
        cmap, smap, tmap = {c["id"]: c for c in classes}, {s["id"]: s for s in subjects}, {t["id"]: t for t in teachers}
        for row in rows:
            row["class"] = cmap.get(row.get("class_id"), {})
            row["subject"] = smap.get(row.get("subject_id"), {})
            row["teacher"] = tmap.get(row.get("teacher_id"), {})
        return rows
