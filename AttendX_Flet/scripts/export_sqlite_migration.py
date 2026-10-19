#!/usr/bin/env python3
"""Export legacy AttendX SQLite records to sanitized CSVs without credentials/biometrics.

Example:
  python scripts/export_sqlite_migration.py --db "C:\\SchoolAttendanceSystem\\attendance.db" --out migration_export

This utility never writes passwords/password hashes, QR tokens, face encodings, fingerprint
sensor IDs, session tokens, or old audit payloads. Review warnings.csv before importing.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def pick(row: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in row and row[key] is not None and str(row[key]).strip() != "":
            return row[key]
    return default


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def table_exists(db: sqlite3.Connection, table: str) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND lower(name)=lower(?)", (table,)).fetchone() is not None


def read_table(db: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    if not table_exists(db, table):
        return []
    quoted = '"' + table.replace('"', '""') + '"'
    db.row_factory = sqlite3.Row
    return [dict(row) for row in db.execute(f"SELECT * FROM {quoted}").fetchall()]


def status_norm(value: Any) -> str | None:
    s = norm(value).upper().replace("-", " ").replace("_", " ")
    s = " ".join(s.split())
    if s in {"PRESENT", "P"}:
        return "PRESENT"
    if s in {"LATE", "TARDY"}:
        return "LATE"
    if s in {"LATE ABSENT", "LATEABSENT", "LATE ABSENT (COUNTED ABSENT)"}:
        return "LATE_ABSENT"
    if s in {"ABSENT", "A"}:
        return "ABSENT"
    return None


def method_norm(value: Any) -> str:
    method = norm(value).upper().replace("-", "_").replace(" ", "_")
    return method if method in {"QR", "FACE", "FINGERPRINT", "SYSTEM", "MANUAL"} else "MANUAL"


def export(database: Path, output: Path) -> dict[str, Any]:
    if not database.is_file():
        raise FileNotFoundError(f"SQLite file not found: {database}")
    output.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    warnings: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    try:
        students = read_table(db, "students")
        teachers = read_table(db, "teachers")
        schedules = read_table(db, "schedules")
        enrollments = read_table(db, "student_classes")
        attendance = read_table(db, "attendance")
        counts.update({"legacy_students_seen": len(students), "legacy_teachers_seen": len(teachers),
                       "legacy_schedules_seen": len(schedules), "legacy_enrollments_seen": len(enrollments),
                       "legacy_attendance_seen": len(attendance)})
        accounts: list[dict[str, Any]] = []
        account_id_by_legacy_student: dict[str, str] = {}
        account_id_by_legacy_teacher: dict[str, str] = {}
        legacy_keys: Counter[tuple[str, str]] = Counter()
        all_account_keys: Counter[str] = Counter()

        for role, rows, target_map in (
            ("STUDENT", students, account_id_by_legacy_student),
            ("TEACHER", teachers, account_id_by_legacy_teacher),
        ):
            for row in rows:
                legacy_pk = norm(pick(row, "id", "student_id", "teacher_pk"))
                raw_account_id = norm(pick(row, "school_id", "teacher_id", "account_id", "account_number", "id"))
                account_id = raw_account_id.lower()
                if not account_id:
                    warnings.append({"table": role.lower(), "legacy_row_id": legacy_pk, "warning": "Missing account ID; row was not exported."})
                    continue
                legacy_keys[(role, legacy_pk)] += 1
                all_account_keys[account_id] += 1
                target_map[legacy_pk] = account_id
                name = norm(pick(row, "name", "full_name"))
                first = norm(pick(row, "first_name"))
                last = norm(pick(row, "last_name"))
                middle = norm(pick(row, "middle_name"))
                suffix = norm(pick(row, "suffix", "extension"))
                sex = norm(pick(row, "sex")).title()
                if sex not in {"Male", "Female"}:
                    warnings.append({"table": role.lower(), "legacy_row_id": legacy_pk, "warning": f"Sex value {sex!r} needs manual review before creating a new account."})
                if (not first or not last) and name:
                    warnings.append({"table": role.lower(), "legacy_row_id": legacy_pk, "warning": "Full name was not split automatically; review first_name and last_name before account recreation."})
                status = norm(pick(row, "status", "student_status", default="ACTIVE")).upper()
                accounts.append({
                    "legacy_row_id": legacy_pk,
                    "legacy_account_id": account_id,
                    "role": role,
                    "first_name": first,
                    "last_name": last,
                    "middle_name": middle,
                    "suffix": suffix,
                    "sex": sex,
                    "course": norm(pick(row, "course", "program")) if role == "STUDENT" else "",
                    "year_level": norm(pick(row, "year", "year_level")) if role == "STUDENT" else "",
                    "section": norm(pick(row, "section")) if role == "STUDENT" else "",
                    "department": norm(pick(row, "department")) if role == "TEACHER" else "",
                    "office": norm(pick(row, "office")) if role == "TEACHER" else "",
                    "legacy_status": status,
                })

        for account_id, count in all_account_keys.items():
            if count > 1:
                warnings.append({"table": "accounts", "legacy_row_id": account_id, "warning": "Account ID appears more than once across original records/roles. Resolve this before importing because target IDs are globally unique."})

        # Lookup old teacher foreign keys: a legacy schedule usually references teachers.id.
        teacher_account_by_ref = dict(account_id_by_legacy_teacher)
        for row in teachers:
            for key in ("teacher_id", "school_id", "account_id"):
                if row.get(key) not in (None, ""):
                    teacher_account_by_ref[norm(row[key])] = account_id_by_legacy_teacher.get(norm(row.get("id")), norm(row[key]).lower())

        schedules_out: list[dict[str, Any]] = []
        schedule_ids: set[str] = set()
        for row in schedules:
            legacy_schedule_id = norm(pick(row, "id", "schedule_id"))
            teacher_ref = norm(pick(row, "teacher_id", "teacher_account_id"))
            teacher_account_id = teacher_account_by_ref.get(teacher_ref, teacher_ref.lower())
            subject = norm(pick(row, "subject", "subject_name"))
            day = norm(pick(row, "day", "day")).title()
            start = norm(pick(row, "start_time"))
            end = norm(pick(row, "end_time"))
            if not legacy_schedule_id:
                warnings.append({"table": "schedules", "legacy_row_id": "", "warning": "Schedule has no legacy ID; row skipped."})
                continue
            if legacy_schedule_id in schedule_ids:
                warnings.append({"table": "schedules", "legacy_row_id": legacy_schedule_id, "warning": "Duplicate legacy schedule ID; row skipped."})
                continue
            schedule_ids.add(legacy_schedule_id)
            if not teacher_account_id or not subject or day not in {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"} or not start or not end:
                warnings.append({"table": "schedules", "legacy_row_id": legacy_schedule_id, "warning": "Missing teacher mapping, subject, day, or time; row exported for review but import builder will reject it."})
            schedules_out.append({
                "legacy_schedule_id": legacy_schedule_id,
                "teacher_account_id": teacher_account_id,
                "course": norm(pick(row, "course", "program")),
                "year_level": norm(pick(row, "year", "year_level")),
                "section": norm(pick(row, "section")),
                "subject_name": subject,
                "day": day,
                "start_time": start,
                "end_time": end,
            })
        valid_schedule_ids = {r["legacy_schedule_id"] for r in schedules_out}

        enrollment_out: list[dict[str, Any]] = []
        for row in enrollments:
            student_ref = norm(pick(row, "student_id"))
            schedule_id = norm(pick(row, "schedule_id"))
            account_id = account_id_by_legacy_student.get(student_ref, student_ref.lower())
            if not account_id or schedule_id not in valid_schedule_ids:
                warnings.append({"table": "student_classes", "legacy_row_id": norm(pick(row, "id", "")), "warning": "Student or schedule reference could not be mapped; enrollment row skipped."})
                continue
            enrollment_out.append({"legacy_account_id": account_id, "role": "STUDENT", "legacy_schedule_id": schedule_id})

        attendance_out: list[dict[str, Any]] = []
        for row in attendance:
            legacy_row_id = norm(pick(row, "id"))
            student_ref = norm(pick(row, "student_id"))
            schedule_id = norm(pick(row, "schedule_id"))
            account_id = account_id_by_legacy_student.get(student_ref, student_ref.lower())
            status = status_norm(pick(row, "status"))
            date_value = norm(pick(row, "attendance_date"))[:10]
            time_value = norm(pick(row, "attendance_time"))
            if not account_id or schedule_id not in valid_schedule_ids or not status or not date_value or not time_value:
                warnings.append({"table": "attendance", "legacy_row_id": legacy_row_id, "warning": "Attendance row missing a mapped student/schedule, valid status, date, or time; row skipped."})
                continue
            attendance_out.append({
                "legacy_row_id": legacy_row_id,
                "legacy_account_id": account_id,
                "role": "STUDENT",
                "legacy_schedule_id": schedule_id,
                "attendance_date": date_value,
                "attendance_time": time_value,
                "status": status,
                "method": method_norm(pick(row, "method")),
            })

        write_csv(output / "accounts.csv", ["legacy_row_id", "legacy_account_id", "role", "first_name", "last_name", "middle_name", "suffix", "sex", "course", "year_level", "section", "department", "office", "legacy_status"], accounts)
        write_csv(output / "schedules.csv", ["legacy_schedule_id", "teacher_account_id", "course", "year_level", "section", "subject_name", "day", "start_time", "end_time"], schedules_out)
        write_csv(output / "enrollments.csv", ["legacy_account_id", "role", "legacy_schedule_id"], enrollment_out)
        write_csv(output / "attendance.csv", ["legacy_row_id", "legacy_account_id", "role", "legacy_schedule_id", "attendance_date", "attendance_time", "status", "method"], attendance_out)
        write_csv(output / "warnings.csv", ["table", "legacy_row_id", "warning"], warnings)

        sensitive = {}
        for table in ("students", "teachers", "qr_codes", "face_data", "fingerprints", "attendance_sessions", "login_history", "audit_logs"):
            sensitive[table] = len(read_table(db, table))
        summary = {
            "source_database": str(database.resolve()),
            "target_backend": "Supabase PostgreSQL; accounts must be recreated via Supabase Auth/AttendX registration before data import",
            "exported": {"accounts": len(accounts), "schedules": len(schedules_out), "enrollments": len(enrollment_out), "attendance": len(attendance_out), "warnings": len(warnings)},
            "legacy_rows_seen": dict(counts),
            "rows_reviewed_but_not_exported_as_sensitive_data": {
                "qr_codes_tokens_and_paths": sensitive["qr_codes"],
                "face_data_file_paths_or_encodings": sensitive["face_data"],
                "fingerprint_sensor_ids": sensitive["fingerprints"],
                "attendance_sessions_raw_tokens": sensitive["attendance_sessions"],
                "login_history_personal_snapshots": sensitive["login_history"],
                "audit_log_payloads": sensitive["audit_logs"],
            },
            "credentials_exported": False,
            "biometric_or_qr_secrets_exported": False,
            "next_step": "Review warnings.csv, recreate Auth users, prepare account_map.csv if IDs change, then run scripts/build_import_sql.py.",
        }
        (output / "migration_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        (output / "MIGRATION_README.txt").write_text(
            "AttendX SQLite migration export\n\n"
            "This pack is sanitized. Password hashes, raw QR tokens, camera/face data, fingerprint sensor IDs, session tokens, and audit payloads are intentionally excluded.\n"
            "1. Review warnings.csv before importing.\n"
            "2. Recreate accounts through the new AttendX/Supabase Auth flow. The old SHA-256 password hashes are not migrated.\n"
            "3. If a legacy Account ID changes, create account_map.csv with columns legacy_account_id,role,target_account_id.\n"
            "4. Run scripts/build_import_sql.py to generate SQL for schedules, enrollments, and attendance only.\n"
            "5. Back up the new Supabase database before running the generated SQL. Run it with a privileged database connection and inspect any raised exception.\n"
            "6. Do not commit this folder: it contains student records.\n",
            encoding="utf-8",
        )
    finally:
        db.close()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="Path to the source SQLite attendance.db")
    parser.add_argument("--out", type=Path, default=Path("migration_export"), help="Output folder (default: ./migration_export)")
    args = parser.parse_args()
    summary = export(args.db, args.out)
    print(json.dumps(summary, indent=2))
    print(f"\nReview {args.out / 'warnings.csv'} before continuing. Sensitive fields were not exported.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
