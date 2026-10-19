from __future__ import annotations

from datetime import datetime
from typing import Any
from supabase import Client

from attendx.core.validators import normalize_spaces, validate_time_range
from attendx.services.supabase_client import BackendError, query_by_values, query_data, query_paginated, safe_message


class TeacherService:
    def __init__(self, client: Client, teacher_id: str):
        self.client = client
        self.teacher_id = teacher_id

    def subjects(self) -> list[dict[str, Any]]:
        return query_paginated(lambda: self.client.table("subjects").select("*").order("subject_name"), max_items=10_000)

    def add_subject(self, name: str) -> dict[str, Any]:
        name = normalize_spaces(name)
        if not name or len(name) > 120:
            raise BackendError("Subject name is required and must be 120 characters or fewer.")
        try:
            rows = self.client.table("subjects").insert({"subject_name": name, "created_by": self.teacher_id}).execute().data or []
            if not rows:
                raise BackendError("The subject was not created. Check database permissions.")
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
            rows = self.client.table("subjects").update({"subject_name": name}).eq("id", subject_id).select("id,subject_name,created_by").execute().data or []
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
            classes = self.client.table("classes").select("id").eq("course", course).eq("year_level", year_level).eq("section", section).limit(1).execute().data or []
            if classes:
                class_id = classes[0]["id"]
            else:
                created = self.client.table("classes").insert({
                    "course": course, "year_level": year_level, "section": section,
                }).execute().data or []
                if not created:
                    raise BackendError("Class details could not be saved.")
                class_id = created[0]["id"]
            rows = self.client.table("schedules").insert({
                "teacher_id": self.teacher_id,
                "class_id": class_id,
                "subject_id": subject_id,
                "day": day,
                "start_time": start_time,
                "end_time": end_time,
                "is_active": True,
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
        """Archive a schedule instead of cascade-deleting its attendance history."""
        try:
            rows = (self.client.table("schedules").update({"is_active": False})
                    .eq("id", schedule_id).eq("teacher_id", self.teacher_id).select("id,is_active").execute().data or [])
            if not rows:
                raise BackendError("Schedule not found or not owned by this teacher.")
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(f"Could not archive schedule: {safe_message(exc)}") from exc

    def class_enrollments(self, schedule_id: str) -> list[dict[str, Any]]:
        enrollments = query_paginated(
            lambda: self.client.table("class_enrollments").select("id,student_id,schedule_id,enrolled_at")
            .eq("schedule_id", schedule_id).order("enrolled_at", desc=True).order("id"), max_items=10_000
        )
        if not enrollments:
            return []
        ids = list({row["student_id"] for row in enrollments})
        profiles = query_by_values(
            self.client, "profiles", "id,account_id,first_name,middle_name,last_name,suffix,course,year_level,section,sex,is_active", "id", ids
        )
        by_id = {p["id"]: p for p in profiles}
        for row in enrollments:
            row["student"] = by_id.get(row["student_id"], {"first_name": "Unavailable", "last_name": "profile"})
        return enrollments

    def students(self) -> list[dict[str, Any]]:
        schedules = self.my_schedules()
        schedule_ids = [row["id"] for row in schedules]
        if not schedule_ids:
            return []
        schedule_id_set = set(schedule_ids)
        enrollments = query_paginated(
            lambda: self.client.table("class_enrollments").select("id,student_id,schedule_id,enrolled_at")
            .order("enrolled_at", desc=True).order("id"), max_items=10_000
        )
        enrollments = [enrollment for enrollment in enrollments if enrollment.get("schedule_id") in schedule_id_set]
        student_ids = list({row["student_id"] for row in enrollments})
        if not student_ids:
            return []
        profiles = query_by_values(
            self.client, "profiles", "id,account_id,first_name,middle_name,last_name,suffix,course,year_level,section,sex,is_active", "id", student_ids
        )
        pmap = {p["id"]: p for p in profiles}
        smap = {s["id"]: s for s in schedules}
        result: dict[str, dict[str, Any]] = {}
        for enrollment in enrollments:
            sid = enrollment["student_id"]
            if sid not in pmap:
                continue
            if sid not in result:
                result[sid] = {**pmap[sid], "enrollments": []}
            result[sid]["enrollments"].append({**enrollment, "schedule": smap.get(enrollment["schedule_id"], {})})
        return sorted(result.values(), key=lambda p: (p.get("last_name") or "", p.get("first_name") or ""))

    def remove_student_from_schedule(self, student_id: str, schedule_id: str) -> None:
        try:
            rows = self.client.table("class_enrollments").delete().eq("student_id", student_id).eq("schedule_id", schedule_id).select("id").execute().data or []
            if not rows:
                raise BackendError("Enrollment was not found or cannot be removed from this schedule.")
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(f"Could not remove enrollment: {safe_message(exc)}") from exc

    def _enrich_schedules(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        class_ids = list({row["class_id"] for row in rows if row.get("class_id")})
        subject_ids = list({row["subject_id"] for row in rows if row.get("subject_id")})
        classes = query_by_values(self.client, "classes", "*", "id", class_ids) if class_ids else []
        subjects = query_by_values(self.client, "subjects", "*", "id", subject_ids) if subject_ids else []
        cmap, smap = {c["id"]: c for c in classes}, {s["id"]: s for s in subjects}
        for row in rows:
            row["class"] = cmap.get(row.get("class_id"), {})
            row["subject"] = smap.get(row.get("subject_id"), {})
        return rows
