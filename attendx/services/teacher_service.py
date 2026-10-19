from __future__ import annotations

from typing import Any
from supabase import Client

from attendx.core.validators import normalize_spaces, validate_time_range
from attendx.services.supabase_client import BackendError, query_by_values, query_paginated, safe_message


class TeacherService:
    """Teacher data adapter for the existing AttendX-Web Supabase schema."""

    def __init__(self, client: Client, teacher_id: str):
        self.client = client
        self.teacher_id = teacher_id

    def subjects(self) -> list[dict[str, Any]]:
        rows = query_paginated(
            lambda: self.client.table("subjects").select("*").order("name"), max_items=10_000
        )
        for row in rows:
            row["subject_name"] = row.get("name", "")
        return rows

    def add_subject(self, name: str) -> dict[str, Any]:
        name = normalize_spaces(name)
        if not name or len(name) > 120:
            raise BackendError("Subject name is required and must be 120 characters or fewer.")
        try:
            rows = self.client.table("subjects").insert({
                "name": name, "created_by": self.teacher_id
            }).execute().data or []
            if not rows:
                raise BackendError("The subject was not created. Check database permissions.")
            rows[0]["subject_name"] = rows[0].get("name", "")
            return rows[0]
        except Exception as exc:
            message = safe_message(exc)
            if "duplicate" in message.lower() or "23505" in message:
                raise BackendError("That subject already exists in the catalog.") from exc
            if isinstance(exc, BackendError):
                raise
            raise BackendError(f"Could not add subject: {message}") from exc

    def update_subject(self, subject_id: str, name: str) -> None:
        name = normalize_spaces(name)
        if not name or len(name) > 120:
            raise BackendError("Subject name is required and must be 120 characters or fewer.")
        try:
            rows = (self.client.table("subjects").update({"name": name})
                    .eq("id", subject_id).select("id,name,created_by").execute().data or [])
            if not rows:
                raise BackendError("Subject not found or not permitted.")
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(f"Could not update subject: {safe_message(exc)}") from exc

    def my_schedules(self) -> list[dict[str, Any]]:
        rows = query_paginated(
            lambda: self.client.table("schedules").select("*").eq("teacher_id", self.teacher_id)
            .order("day").order("start_time").order("id"), max_items=10_000
        )
        return self._enrich_schedules(rows)

    def add_schedule(self, *, course: str, year_level: str, section: str, subject_id: str,
                     day: str, start_time: str, end_time: str) -> dict[str, Any]:
        course, year_level, section = (normalize_spaces(x) for x in (course, year_level, section))
        day = normalize_spaces(day).title()
        if not all((course, year_level, section, subject_id)):
            raise BackendError("Course, year, section, and subject are required.")
        if day not in {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}:
            raise BackendError("Select a valid day of the week.")
        start_time, end_time = validate_time_range(start_time, end_time)
        if len(course) > 120 or len(year_level) > 20 or len(section) > 40:
            raise BackendError("Course, year, or section exceeds the supported length.")
        try:
            subjects = (self.client.table("subjects").select("id,name")
                        .eq("id", subject_id).limit(1).execute().data or [])
            if not subjects:
                raise BackendError("Select a subject from the shared AttendX subject catalog.")
            subject_name = subjects[0]["name"]
            rows = self.client.table("schedules").insert({
                "teacher_id": self.teacher_id,
                "course": course,
                "subject": subject_name,
                "year_level": year_level,
                "section": section,
                "day": day,
                "start_time": start_time,
                "end_time": end_time,
                "status": "ACTIVE",
            }).execute().data or []
            if not rows:
                raise BackendError("Schedule could not be created.")
            return self._enrich_schedules(rows)[0]
        except BackendError:
            raise
        except Exception as exc:
            message = safe_message(exc)
            if "duplicate" in message.lower() or "23505" in message:
                raise BackendError("An identical schedule already exists for this teacher, subject, class, day, and time.") from exc
            raise BackendError(f"Could not create schedule: {message}") from exc

    def delete_schedule(self, schedule_id: str) -> None:
        """Archive a schedule instead of deleting its attendance history."""
        try:
            rows = (self.client.table("schedules").update({"status": "ARCHIVED"})
                    .eq("id", str(schedule_id)).eq("teacher_id", self.teacher_id)
                    .select("id,status").execute().data or [])
            if not rows:
                raise BackendError("Schedule not found or not owned by this teacher.")
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(f"Could not archive schedule: {safe_message(exc)}") from exc

    def class_enrollments(self, schedule_id: str) -> list[dict[str, Any]]:
        enrollments = query_paginated(
            lambda: self.client.table("enrollments").select("id,student_id,schedule_id,joined_at")
            .eq("schedule_id", str(schedule_id)).order("joined_at", desc=True).order("id"),
            max_items=10_000
        )
        if not enrollments:
            return []
        ids = list({str(row["student_id"]) for row in enrollments})
        profiles = query_by_values(
            self.client, "profiles",
            "id,account_id,first_name,middle_name,last_name,suffix,course,year_level,section,sex,status",
            "id", ids
        )
        by_id = {str(row["id"]): row for row in profiles}
        for row in enrollments:
            row["enrolled_at"] = row.get("joined_at", "")
            row["student"] = by_id.get(str(row["student_id"]), {
                "first_name": "Unavailable", "last_name": "profile"
            })
        return enrollments

    def students(self) -> list[dict[str, Any]]:
        schedules = self.my_schedules()
        schedule_ids = {str(row["id"]) for row in schedules}
        if not schedule_ids:
            return []
        enrollments = query_paginated(
            lambda: self.client.table("enrollments").select("id,student_id,schedule_id,joined_at")
            .order("joined_at", desc=True).order("id"), max_items=10_000
        )
        enrollments = [row for row in enrollments if str(row.get("schedule_id")) in schedule_ids]
        student_ids = list({str(row["student_id"]) for row in enrollments})
        if not student_ids:
            return []
        profiles = query_by_values(
            self.client, "profiles",
            "id,account_id,first_name,middle_name,last_name,suffix,course,year_level,section,sex,status",
            "id", student_ids
        )
        pmap = {str(row["id"]): row for row in profiles}
        smap = {str(row["id"]): row for row in schedules}
        result: dict[str, dict[str, Any]] = {}
        for enrollment in enrollments:
            sid = str(enrollment["student_id"])
            if sid not in pmap:
                continue
            if sid not in result:
                result[sid] = {**pmap[sid], "enrollments": []}
                result[sid]["is_active"] = str(result[sid].get("status", "ACTIVE")).upper() == "ACTIVE"
            result[sid]["enrollments"].append({
                **enrollment, "schedule": smap.get(str(enrollment["schedule_id"]), {})
            })
        return sorted(result.values(), key=lambda row: (row.get("last_name") or "", row.get("first_name") or ""))

    def remove_student_from_schedule(self, student_id: str, schedule_id: str) -> None:
        try:
            rows = (self.client.table("enrollments").delete()
                    .eq("student_id", student_id).eq("schedule_id", str(schedule_id))
                    .select("id").execute().data or [])
            if not rows:
                raise BackendError("Enrollment was not found or cannot be removed from this schedule.")
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(f"Could not remove enrollment: {safe_message(exc)}") from exc

    def _enrich_schedules(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for row in rows:
            subject_name = str(row.get("subject") or "")
            row["class"] = {
                "course": row.get("course", ""),
                "year_level": row.get("year_level", ""),
                "section": row.get("section", ""),
            }
            row["subject"] = {"name": subject_name, "subject_name": subject_name}
            row["is_active"] = str(row.get("status", "")).upper() == "ACTIVE"
        return rows
