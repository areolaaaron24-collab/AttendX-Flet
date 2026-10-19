#!/usr/bin/env python3
"""Build reviewable PostgreSQL import SQL from the sanitized AttendX CSV export.

This never creates accounts or imports credentials/biometrics. Each target profile must
already exist in Supabase Auth/`public.profiles`.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date, time
from pathlib import Path
from typing import Any

ALLOWED_ROLES = {"TEACHER", "STUDENT"}
ALLOWED_DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}
ALLOWED_STATUSES = {"PRESENT", "LATE", "LATE_ABSENT", "ABSENT"}
ALLOWED_METHODS = {"QR", "FACE", "FINGERPRINT", "SYSTEM", "MANUAL"}


def read_csv(path: Path, required: tuple[str, ...] = ()) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Required migration CSV was not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = set(reader.fieldnames or [])
        missing = [key for key in required if key not in fields]
        if missing:
            raise ValueError(f"{path.name} is missing required columns: {', '.join(missing)}")
        return [{str(k): (v or "").strip() for k, v in row.items() if k is not None} for row in reader]


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def load_account_map(path: Path | None) -> dict[tuple[str, str], str]:
    if path is None:
        return {}
    rows = read_csv(path, ("legacy_account_id", "role", "target_account_id"))
    output: dict[tuple[str, str], str] = {}
    for row_number, row in enumerate(rows, start=2):
        role = row["role"].upper()
        old = row["legacy_account_id"].lower()
        new = row["target_account_id"].lower()
        if role not in ALLOWED_ROLES or not old or not new:
            raise ValueError(f"Invalid account mapping at {path.name}:{row_number}")
        key = (role, old)
        if key in output and output[key] != new:
            raise ValueError(f"Conflicting mappings for {role} account {old!r}")
        output[key] = new
    return output


def remap(account_id: str, role: str, mapping: dict[tuple[str, str], str]) -> str:
    account = (account_id or "").strip().lower()
    role = (role or "").strip().upper()
    if role not in ALLOWED_ROLES:
        raise ValueError(f"Unsupported account role {role!r}; only Teacher and Student are allowed.")
    if not account:
        raise ValueError(f"A {role} row contains an empty account ID.")
    return mapping.get((role, account), account)


def values(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> str:
    if not rows:
        return "(SELECT " + ", ".join("NULL::text AS " + c for c in columns) + " WHERE false)"
    rendered = []
    for row in rows:
        rendered.append("(" + ", ".join(sql_literal(row.get(col)) for col in columns) + ")")
    return "(VALUES\n      " + ",\n      ".join(rendered) + "\n    ) AS src(" + ", ".join(columns) + ")"


def build(export_dir: Path, output_file: Path, account_map_path: Path | None = None) -> dict[str, Any]:
    accounts = read_csv(export_dir / "accounts.csv", ("legacy_account_id", "role"))
    schedules = read_csv(export_dir / "schedules.csv", (
        "legacy_schedule_id", "teacher_account_id", "course", "year_level", "section",
        "subject_name", "day", "start_time", "end_time",
    ))
    enrollments = read_csv(export_dir / "enrollments.csv", ("legacy_account_id", "role", "legacy_schedule_id"))
    attendance = read_csv(export_dir / "attendance.csv", (
        "legacy_row_id", "legacy_account_id", "role", "legacy_schedule_id", "attendance_date",
        "attendance_time", "status", "method",
    ))
    mapping = load_account_map(account_map_path)

    # Validate only data that will be written; malformed source rows should be fixed/re-exported
    # rather than interpolated into executable SQL.
    schedule_rows: list[dict[str, str]] = []
    seen_schedule_ids: set[str] = set()
    for index, row in enumerate(schedules, start=2):
        legacy_id = row["legacy_schedule_id"]
        if not legacy_id or legacy_id in seen_schedule_ids:
            raise ValueError(f"schedules.csv row {index} has an empty or duplicate legacy_schedule_id")
        seen_schedule_ids.add(legacy_id)
        teacher_id = remap(row["teacher_account_id"], "TEACHER", mapping)
        subject = row["subject_name"].strip()
        day = row["day"].strip().title()
        if not subject or day not in ALLOWED_DAYS:
            raise ValueError(f"schedules.csv row {index} has an invalid subject/day")
        try:
            start = time.fromisoformat(row["start_time"][:8] if len(row["start_time"]) >= 8 else row["start_time"])
            end = time.fromisoformat(row["end_time"][:8] if len(row["end_time"]) >= 8 else row["end_time"])
        except ValueError as exc:
            raise ValueError(f"schedules.csv row {index} has an invalid start/end time") from exc
        if end <= start:
            raise ValueError(f"schedules.csv row {index} is overnight or ends before it starts; schema requires same-day sessions")
        if not all(row.get(k, "").strip() for k in ("course", "year_level", "section")):
            raise ValueError(f"schedules.csv row {index} is missing course/year/section")
        schedule_rows.append({
            "legacy_schedule_id": legacy_id,
            "teacher_account_id": teacher_id,
            "course": row["course"],
            "year_level": row["year_level"],
            "section": row["section"],
            "subject_name": subject,
            "day": day,
            "start_time": start.isoformat(timespec="seconds"),
            "end_time": end.isoformat(timespec="seconds"),
        })

    enrollment_rows: list[dict[str, str]] = []
    for i, row in enumerate(enrollments, start=2):
        if row["legacy_schedule_id"] not in seen_schedule_ids:
            raise ValueError(f"enrollments.csv row {i} references unknown schedule {row['legacy_schedule_id']!r}")
        role = row["role"].upper()
        if role != "STUDENT":
            raise ValueError(f"enrollments.csv row {i} is not a Student enrollment")
        enrollment_rows.append({
            "legacy_account_id": remap(row["legacy_account_id"], role, mapping),
            "role": role,
            "legacy_schedule_id": row["legacy_schedule_id"],
        })

    attendance_rows: list[dict[str, str]] = []
    for i, row in enumerate(attendance, start=2):
        if row["legacy_schedule_id"] not in seen_schedule_ids:
            raise ValueError(f"attendance.csv row {i} references unknown schedule {row['legacy_schedule_id']!r}")
        if row["role"].upper() != "STUDENT":
            raise ValueError(f"attendance.csv row {i} is not for a Student")
        status = row["status"].upper()
        method = row["method"].upper()
        if status not in ALLOWED_STATUSES or method not in ALLOWED_METHODS:
            raise ValueError(f"attendance.csv row {i} has unsupported status/method")
        try:
            date.fromisoformat(row["attendance_date"][:10])
            time.fromisoformat(row["attendance_time"][:8] if len(row["attendance_time"]) >= 8 else row["attendance_time"])
        except ValueError as exc:
            raise ValueError(f"attendance.csv row {i} has invalid date/time") from exc
        attendance_rows.append({
            "legacy_row_id": row["legacy_row_id"],
            "legacy_account_id": remap(row["legacy_account_id"], "STUDENT", mapping),
            "role": "STUDENT",
            "legacy_schedule_id": row["legacy_schedule_id"],
            "attendance_date": row["attendance_date"][:10],
            "attendance_time": row["attendance_time"][:8] if len(row["attendance_time"]) >= 8 else row["attendance_time"],
            "status": status,
            "method": method,
        })

    # Legacy accounts are deliberately not created here; this query is a preflight assertion only.
    remapped_accounts = []
    seen_accounts: set[tuple[str, str]] = set()
    for row in accounts:
        role = row["role"].upper()
        target = remap(row["legacy_account_id"], role, mapping)
        key = (role, target)
        if key not in seen_accounts:
            remapped_accounts.append({"role": role, "target_account_id": target})
            seen_accounts.add(key)

    sql = [
        "-- Generated by scripts/build_import_sql.py. Review this file before execution.",
        "-- Requires: profiles already recreated through Supabase Auth/AttendX; backup first.",
        "-- Inserts schedule/catalog, enrollments, and historical attendance only.",
        "-- No passwords, tokens, biometrics, face images, sensor IDs, or session tokens are imported.",
        "BEGIN;",
        "CREATE TEMP TABLE attendx_legacy_schedule_map (legacy_schedule_id text PRIMARY KEY, target_schedule_id bigint NOT NULL) ON COMMIT DROP;",
        "DO $attendx_accounts$ DECLARE r record; v_id uuid; BEGIN\n"
        "  FOR r IN SELECT * FROM " + values(remapped_accounts, ("role", "target_account_id")) + " LOOP\n"
        "    SELECT p.id INTO v_id FROM public.profiles p WHERE lower(btrim(p.account_id)) = lower(btrim(r.target_account_id)) AND p.role = r.role AND p.is_active = true;\n"
        "    IF v_id IS NULL THEN RAISE EXCEPTION 'Missing active target profile for role % / account ID %; create the account in AttendX first', r.role, r.target_account_id; END IF;\n"
        "    v_id := NULL;\n"
        "  END LOOP;\nEND $attendx_accounts$;",
        "DO $attendx_schedules$ DECLARE r record; v_teacher uuid; v_subject bigint; v_class bigint; v_schedule bigint; BEGIN\n"
        "  FOR r IN SELECT * FROM " + values(schedule_rows, ("legacy_schedule_id", "teacher_account_id", "course", "year_level", "section", "subject_name", "day", "start_time", "end_time")) + " LOOP\n"
        "    SELECT p.id INTO v_teacher FROM public.profiles p WHERE lower(btrim(p.account_id)) = lower(btrim(r.teacher_account_id)) AND p.role = 'TEACHER' AND p.is_active = true;\n"
        "    IF v_teacher IS NULL THEN RAISE EXCEPTION 'Missing active teacher account ID %', r.teacher_account_id; END IF;\n"
        "    INSERT INTO public.subjects(subject_name, created_by) VALUES (r.subject_name, v_teacher) ON CONFLICT (subject_name) DO UPDATE SET subject_name = EXCLUDED.subject_name RETURNING id INTO v_subject;\n"
        "    INSERT INTO public.classes(course, year_level, section) VALUES (r.course, r.year_level, r.section) ON CONFLICT (course, year_level, section) DO UPDATE SET updated_at = now() RETURNING id INTO v_class;\n"
        "    INSERT INTO public.schedules(teacher_id, class_id, subject_id, day, start_time, end_time, is_active)\n"
        "      VALUES (v_teacher, v_class, v_subject, r.day, r.start_time::time, r.end_time::time, true)\n"
        "      ON CONFLICT (teacher_id, class_id, subject_id, day, start_time, end_time) DO UPDATE SET is_active = true, updated_at = now() RETURNING id INTO v_schedule;\n"
        "    INSERT INTO pg_temp.attendx_legacy_schedule_map(legacy_schedule_id, target_schedule_id) VALUES (r.legacy_schedule_id, v_schedule) ON CONFLICT (legacy_schedule_id) DO UPDATE SET target_schedule_id = EXCLUDED.target_schedule_id;\n"
        "  END LOOP;\nEND $attendx_schedules$;",
        "DO $attendx_enrollments$ DECLARE r record; v_student uuid; v_schedule bigint; BEGIN\n"
        "  FOR r IN SELECT * FROM " + values(enrollment_rows, ("legacy_account_id", "role", "legacy_schedule_id")) + " LOOP\n"
        "    SELECT p.id INTO v_student FROM public.profiles p WHERE lower(btrim(p.account_id)) = lower(btrim(r.legacy_account_id)) AND p.role = 'STUDENT' AND p.is_active = true;\n"
        "    IF v_student IS NULL THEN RAISE EXCEPTION 'Missing active student account ID %', r.legacy_account_id; END IF;\n"
        "    SELECT m.target_schedule_id INTO v_schedule FROM pg_temp.attendx_legacy_schedule_map m WHERE m.legacy_schedule_id = r.legacy_schedule_id;\n"
        "    IF v_schedule IS NULL THEN RAISE EXCEPTION 'Unknown legacy schedule ID %', r.legacy_schedule_id; END IF;\n"
        "    INSERT INTO public.class_enrollments(student_id, schedule_id) VALUES (v_student, v_schedule) ON CONFLICT (student_id, schedule_id) DO NOTHING;\n"
        "  END LOOP;\nEND $attendx_enrollments$;",
        "DO $attendx_attendance$ DECLARE r record; v_student uuid; v_schedule bigint; v_date date; v_time time; BEGIN\n"
        "  FOR r IN SELECT * FROM " + values(attendance_rows, ("legacy_row_id", "legacy_account_id", "role", "legacy_schedule_id", "attendance_date", "attendance_time", "status", "method")) + " LOOP\n"
        "    SELECT p.id INTO v_student FROM public.profiles p WHERE lower(btrim(p.account_id)) = lower(btrim(r.legacy_account_id)) AND p.role = 'STUDENT' AND p.is_active = true;\n"
        "    IF v_student IS NULL THEN RAISE EXCEPTION 'Missing active student account ID %', r.legacy_account_id; END IF;\n"
        "    SELECT m.target_schedule_id INTO v_schedule FROM pg_temp.attendx_legacy_schedule_map m WHERE m.legacy_schedule_id = r.legacy_schedule_id;\n"
        "    IF v_schedule IS NULL THEN RAISE EXCEPTION 'Unknown legacy schedule ID %', r.legacy_schedule_id; END IF;\n"
        "    v_date := r.attendance_date::date; v_time := r.attendance_time::time;\n"
        "    INSERT INTO public.attendance_records(student_id, schedule_id, session_id, attendance_date, attendance_time, observed_at, status, method)\n"
        "      VALUES (v_student, v_schedule, NULL, v_date, v_time, (v_date + v_time) AT TIME ZONE 'Asia/Manila', r.status, r.method)\n"
        "      ON CONFLICT (student_id, schedule_id, attendance_date) DO NOTHING;\n"
        "  END LOOP;\nEND $attendx_attendance$;",
        "INSERT INTO public.audit_logs(actor_id, actor_role, action, entity_type, details) VALUES (NULL, NULL, 'legacy_data_import', 'migration', jsonb_build_object('schedules', " + str(len(schedule_rows)) + ", 'enrollments', " + str(len(enrollment_rows)) + ", 'attendance_rows', " + str(len(attendance_rows)) + ", 'timezone', 'Asia/Manila'));",
        "COMMIT;",
    ]
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("\n\n".join(sql) + "\n", encoding="utf-8")
    return {
        "output_file": str(output_file),
        "target_profiles_preflighted": len(remapped_accounts),
        "schedules": len(schedule_rows),
        "enrollments": len(enrollment_rows),
        "attendance_rows": len(attendance_rows),
        "account_map_used": str(account_map_path) if account_map_path else None,
        "sensitive_data_imported": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-dir", required=True, type=Path, help="Directory created by export_sqlite_migration.py")
    parser.add_argument("--out", type=Path, default=Path("migration_import.sql"), help="SQL path to write")
    parser.add_argument("--account-map", type=Path, help="Optional CSV: legacy_account_id,role,target_account_id")
    args = parser.parse_args()
    summary = build(args.export_dir, args.out, args.account_map)
    print(json.dumps(summary, indent=2))
    print("IMPORTANT: review the generated SQL, back up Supabase, and only then execute it with a privileged DB connection.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
