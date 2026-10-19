from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from supabase import Client

from attendx.services.supabase_client import BackendError, query_by_values, query_paginated, rpc, safe_message


class AttendanceService:
    METHODS = {"QR", "FACE", "FINGERPRINT", "MANUAL"}

    def __init__(self, client: Client, actor_id: str, role: str):
        self.client = client
        self.actor_id = actor_id
        self.role = role.upper()

    def start_session(self, schedule_id: str) -> dict[str, Any]:
        if self.role != "TEACHER":
            raise BackendError("Only the teacher assigned to the schedule can start attendance.")
        token = secrets.token_urlsafe(32)
        result = rpc(self.client, "start_attendance_session", {
            "p_schedule_id": schedule_id,
            "p_session_token": token,
        })
        if isinstance(result, list) and result:
            result = result[0]
        if isinstance(result, dict):
            result["raw_token"] = token
        return result

    def record_qr(self, raw_token: str, schedule_id: str) -> dict[str, Any]:
        if self.role != "TEACHER":
            raise BackendError("Teacher authentication is required to verify a student QR pass.")
        result = rpc(self.client, "record_attendance_by_student_qr", {
            "p_token_text": raw_token,
            "p_schedule_id": schedule_id,
        })
        return self._as_result(result)

    def record_session_qr(self, raw_token: str) -> dict[str, Any]:
        if self.role != "STUDENT":
            raise BackendError("Student authentication is required to submit session QR attendance.")
        result = rpc(self.client, "record_session_qr_attendance", {"p_token_text": raw_token})
        return self._as_result(result)

    def record_biometric(self, student_id: str, schedule_id: str, method: str) -> dict[str, Any]:
        method = method.upper()
        if self.role != "TEACHER":
            raise BackendError("Only an authenticated teacher can submit a verified biometric result.")
        if method not in {"FACE", "FINGERPRINT"}:
            raise BackendError("Unsupported attendance method.")
        return self._as_result(rpc(self.client, "record_biometric_attendance", {
            "p_student_id": student_id, "p_schedule_id": schedule_id, "p_method": method,
        }))

    def record_manual(self, student_id: str, schedule_id: str, reason: str) -> dict[str, Any]:
        if self.role != "TEACHER":
            raise BackendError("Only teachers can record manual attendance corrections.")
        if len((reason or "").strip()) < 10:
            raise BackendError("Enter an audit reason of at least 10 characters.")
        return self._as_result(rpc(self.client, "record_manual_attendance", {
            "p_student_id": student_id,
            "p_schedule_id": schedule_id,
            "p_reason": reason.strip(),
        }))

    def close_session(self, session_id: str) -> dict[str, Any]:
        if self.role != "TEACHER":
            raise BackendError("Only teachers can close their attendance session.")
        return self._as_result(rpc(self.client, "close_attendance_session", {"p_session_id": session_id}))

    def finalize_schedule(self, schedule_id: str, attendance_date: str | None = None) -> dict[str, Any]:
        if self.role != "TEACHER":
            raise BackendError("Only teachers can finalize attendance.")
        return self._as_result(rpc(self.client, "finalize_attendance_session", {
            "p_schedule_id": schedule_id,
            "p_session_date": attendance_date or datetime.now(ZoneInfo("Asia/Manila")).date().isoformat(),
        }))

    def teacher_records(self, schedule_id: str | None = None, attendance_date: str | None = None,
                        limit: int = 500) -> list[dict[str, Any]]:
        bounded_limit = min(max(int(limit), 1), 10_000)
        def make_query():
            query = self.client.table("attendance_records").select("*").order("attendance_date", desc=True).order("attendance_time", desc=True).order("id")
            if schedule_id:
                query = query.eq("schedule_id", schedule_id)
            if attendance_date:
                query = query.eq("attendance_date", attendance_date)
            return query
        records = query_paginated(make_query, page_size=500, max_items=bounded_limit)
        if not records:
            return []
        student_ids = list({r["student_id"] for r in records})
        schedule_ids = list({r["schedule_id"] for r in records})
        profiles = query_by_values(self.client, "profiles", "id,account_id,first_name,middle_name,last_name,suffix,course,year_level,section", "id", student_ids)
        schedules = query_by_values(self.client, "schedules", "*", "id", schedule_ids)
        cmap = {p["id"]: p for p in profiles}
        smap = {s["id"]: s for s in schedules}
        for row in records:
            row["student"] = cmap.get(row["student_id"], {})
            row["schedule"] = smap.get(row["schedule_id"], {})
        return records

    def today_summary(self) -> dict[str, int]:
        from datetime import date, timedelta, datetime
        from zoneinfo import ZoneInfo

        empty_summary = {
            "today": 0,
            "week": 0,
            "month": 0,
            "present": 0,
            "late": 0,
            "late_absent": 0,
            "absent": 0,
        }

        if str(getattr(self, "role", "")).upper() != "TEACHER":
            return empty_summary.copy()

        user_id = getattr(self, "user_id", None)
        if not user_id:
            return empty_summary.copy()

        today = datetime.now(ZoneInfo("Asia/Manila")).date()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        def fetch_pages(query_factory):
            collected = []
            offset = 0
            page_size = 500

            while True:
                response = (
                    query_factory()
                    .range(offset, offset + page_size - 1)
                    .execute()
                )
                page = response.data or []
                collected.extend(page)

                if len(page) < page_size:
                    break

                offset += page_size

            return collected

        schedule_rows = fetch_pages(
            lambda: self.client.table("schedules")
            .select("id")
            .eq("teacher_id", str(user_id))
        )

        schedule_ids = list(dict.fromkeys(
            str(row["id"])
            for row in schedule_rows
            if row.get("id") is not None
        ))

        if not schedule_ids:
            return empty_summary.copy()

        attendance_rows = []

        for start in range(0, len(schedule_ids), 200):
            schedule_chunk = schedule_ids[start:start + 200]

            attendance_rows.extend(
                fetch_pages(
                    lambda chunk=schedule_chunk: self.client
                    .table("attendance")
                    .select("id,schedule_id,attendance_date,status")
                    .in_("schedule_id", chunk)
                    .gte("attendance_date", month_start.isoformat())
                    .lte("attendance_date", today.isoformat())
                )
            )

        summary = empty_summary.copy()

        for row in attendance_rows:
            raw_date = row.get("attendance_date")
            if not raw_date:
                continue

            try:
                attendance_date = date.fromisoformat(str(raw_date)[:10])
            except (TypeError, ValueError):
                continue

            summary["month"] += 1

            if attendance_date >= week_start:
                summary["week"] += 1

            if attendance_date == today:
                summary["today"] += 1

            status = str(row.get("status") or "").upper().replace("-", "_")

            if status == "PRESENT":
                summary["present"] += 1
            elif status == "LATE":
                summary["late"] += 1
            elif status == "LATE_ABSENT":
                summary["late_absent"] += 1
            elif status == "ABSENT":
                summary["absent"] += 1

        return summary

    def _as_result(value: Any) -> dict[str, Any]:
        if isinstance(value, list) and value:
            value = value[0]
        if isinstance(value, dict):
            if value.get("ok") is False:
                raise BackendError(str(value.get("message") or "Attendance could not be recorded."))
            return value
        return {"ok": bool(value), "message": str(value or "Request completed.")}
