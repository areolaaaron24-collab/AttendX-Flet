from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from supabase import Client

from attendx.services.supabase_client import (
    BackendError, query_by_values, query_paginated, response_data, rpc, safe_message,
)


class AttendanceService:
    """Attendance adapter for the deployed AttendX-Web tables and RPCs."""

    METHODS = {"QR", "FACE", "FINGERPRINT"}

    def __init__(self, client: Client, actor_id: str, role: str):
        self.client = client
        self.actor_id = actor_id
        self.role = role.upper()

    def start_session(self, schedule_id: str) -> dict[str, Any]:
        if self.role != "TEACHER":
            raise BackendError("Only the assigned teacher can manage attendance.")
        # AttendX-Web's current start-session RPC does not return the session token
        # required by the Flet Student 'Scan Class QR' flow. Never display a fake QR.
        raise BackendError(
            "Teacher session QR is not yet supported by the existing AttendX-Web backend. "
            "Use Attendance Center → Scan Student QR to verify each student's personal QR pass."
        )

    def record_qr(self, raw_token: str, schedule_id: str) -> dict[str, Any]:
        if self.role != "TEACHER":
            raise BackendError("Teacher authentication is required to verify a student QR pass.")
        token = str(raw_token or "").strip()
        if not token or len(token) > 160:
            raise BackendError("QR content is missing or invalid.")
        try:
            response = self.client.functions.invoke(
                "verify-qr",
                invoke_options={"body": {"token": token, "scheduleId": str(schedule_id)}},
            )
            verified = response_data(response)
        except Exception as exc:
            raise BackendError(f"QR verification failed: {safe_message(exc)}") from exc
        if isinstance(verified, list) and verified:
            verified = verified[0]
        student = verified.get("student") if isinstance(verified, dict) else None
        student_id = student.get("id") if isinstance(student, dict) else None
        if not student_id:
            message = verified.get("error") if isinstance(verified, dict) else None
            raise BackendError(str(message or "The server did not verify this QR pass."))
        result = self._as_result(rpc(self.client, "record_attendance", {
            "p_student_id": str(student_id),
            "p_schedule_id": str(schedule_id),
            "p_method": "QR",
        }))
        result.setdefault("student_id", str(student_id))
        result.setdefault("message", f"{student.get('name', 'Student')}: attendance recorded.")
        return result

    def record_session_qr(self, raw_token: str) -> dict[str, Any]:
        if self.role != "STUDENT":
            raise BackendError("Student authentication is required to scan a class session QR.")
        raise BackendError(
            "Student session-QR submission is not yet supported by the existing AttendX-Web backend. "
            "Use your personal QR pass and ask the teacher to scan it."
        )

    def record_biometric(self, student_id: str, schedule_id: str, method: str) -> dict[str, Any]:
        method = method.upper()
        if self.role != "TEACHER":
            raise BackendError("Only an authenticated teacher can submit a verified biometric result.")
        if method not in {"FACE", "FINGERPRINT"}:
            raise BackendError("Unsupported attendance method.")
        result = self._as_result(rpc(self.client, "record_attendance", {
            "p_student_id": str(student_id),
            "p_schedule_id": str(schedule_id),
            "p_method": method,
        }))
        result.setdefault("student_id", str(student_id))
        return result

    def record_manual(self, student_id: str, schedule_id: str, reason: str) -> dict[str, Any]:
        if self.role != "TEACHER":
            raise BackendError("Only teachers can record manual attendance corrections.")
        if len((reason or "").strip()) < 10:
            raise BackendError("Enter an audit reason of at least 10 characters.")
        raise BackendError(
            "Manual attendance correction requires a server-side audited RPC that is not present "
            "in the current AttendX-Web schema. No attendance record was written."
        )

    def close_session(self, session_id: str) -> dict[str, Any]:
        if self.role != "TEACHER":
            raise BackendError("Only teachers can close their attendance session.")
        raise BackendError(
            "Closing a Flet session is not available in the existing AttendX-Web backend yet. "
            "This action did not change the database."
        )

    def finalize_schedule(self, schedule_id: str, attendance_date: str | None = None) -> dict[str, Any]:
        if self.role != "TEACHER":
            raise BackendError("Only teachers can finalize attendance.")
        today = datetime.now(ZoneInfo("Asia/Manila")).date().isoformat()
        if attendance_date and attendance_date != today:
            raise BackendError("The existing AttendX-Web no-show RPC can finalize only the current Manila date.")
        result = self._as_result(rpc(self.client, "mark_absent_students", {
            "p_schedule_id": str(schedule_id),
        }))
        inserted = result.get("inserted", 0)
        result.setdefault("message", f"Attendance finalized. {inserted} student(s) marked ABSENT.")
        return result

    def teacher_records(self, schedule_id: str | None = None, attendance_date: str | None = None,
                        limit: int = 500) -> list[dict[str, Any]]:
        bounded_limit = min(max(int(limit), 1), 10_000)

        def make_query():
            query = (self.client.table("attendance").select("*")
                     .order("attendance_date", desc=True)
                     .order("attendance_time", desc=True).order("id"))
            if schedule_id:
                query = query.eq("schedule_id", str(schedule_id))
            if attendance_date:
                query = query.eq("attendance_date", attendance_date)
            return query

        records = query_paginated(make_query, page_size=500, max_items=bounded_limit)
        if not records:
            return []
        student_ids = list({str(row["student_id"]) for row in records})
        schedule_ids = list({str(row["schedule_id"]) for row in records})
        profiles = query_by_values(
            self.client, "profiles",
            "id,account_id,first_name,middle_name,last_name,suffix,course,year_level,section,status",
            "id", student_ids
        )
        schedules = query_by_values(self.client, "schedules", "*", "id", schedule_ids)
        pmap = {str(row["id"]): row for row in profiles}
        smap = {str(row["id"]): row for row in schedules}
        for row in records:
            row["student"] = pmap.get(str(row["student_id"]), {})
            row["schedule"] = smap.get(str(row["schedule_id"]), {})
            row["status"] = str(row.get("status", "")).replace("LATE-ABSENT", "LATE_ABSENT")
        return records

    def today_summary(self) -> dict[str, int]:
        from datetime import date, timedelta

        summary = {
            "today": 0, "week": 0, "month": 0,
            "present": 0, "late": 0, "late_absent": 0, "absent": 0,
        }
        if self.role != "TEACHER":
            return summary
        today = datetime.now(ZoneInfo("Asia/Manila")).date()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        schedule_rows = query_paginated(
            lambda: self.client.table("schedules").select("id").eq("teacher_id", self.actor_id),
            max_items=10_000
        )
        schedule_ids = [str(row["id"]) for row in schedule_rows if row.get("id") is not None]
        for start in range(0, len(schedule_ids), 200):
            chunk = schedule_ids[start:start + 200]
            rows = query_paginated(
                lambda chunk=chunk: self.client.table("attendance")
                .select("attendance_date,status").in_("schedule_id", chunk)
                .gte("attendance_date", month_start.isoformat()).lte("attendance_date", today.isoformat()),
                max_items=20_000
            )
            for row in rows:
                try:
                    attendance_date = date.fromisoformat(str(row.get("attendance_date"))[:10])
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

    @staticmethod
    def _as_result(value: Any) -> dict[str, Any]:
        if isinstance(value, list) and value:
            value = value[0]
        if isinstance(value, dict):
            if value.get("ok") is False:
                raise BackendError(str(value.get("message") or value.get("error") or "Attendance could not be recorded."))
            return value
        return {"ok": bool(value), "message": str(value or "Request completed.")}
