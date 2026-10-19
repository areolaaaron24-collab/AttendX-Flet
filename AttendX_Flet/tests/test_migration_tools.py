import csv
import json
import sqlite3
from pathlib import Path

from scripts.build_import_sql import build
from scripts.export_sqlite_migration import export


def make_legacy_db(path: Path) -> None:
    db = sqlite3.connect(path)
    db.executescript("""
    CREATE TABLE students (id INTEGER PRIMARY KEY, school_id TEXT, name TEXT, password TEXT, course TEXT, year TEXT, section TEXT, sex TEXT);
    CREATE TABLE teachers (id INTEGER PRIMARY KEY, teacher_id TEXT, name TEXT, password TEXT);
    CREATE TABLE schedules (id INTEGER PRIMARY KEY, teacher_id TEXT, course TEXT, year TEXT, section TEXT, subject TEXT, day TEXT, start_time TEXT, end_time TEXT);
    CREATE TABLE student_classes (id INTEGER PRIMARY KEY, student_id TEXT, schedule_id TEXT);
    CREATE TABLE attendance (id INTEGER PRIMARY KEY, student_id TEXT, schedule_id TEXT, attendance_date TEXT, attendance_time TEXT, status TEXT, method TEXT);
    CREATE TABLE qr_codes (id INTEGER PRIMARY KEY, token TEXT);
    CREATE TABLE face_data (id INTEGER PRIMARY KEY, encoding TEXT, image_path TEXT);
    CREATE TABLE fingerprints (id INTEGER PRIMARY KEY, sensor_template_id TEXT);
    CREATE TABLE attendance_sessions (id INTEGER PRIMARY KEY, session_token TEXT);
    CREATE TABLE login_history (id INTEGER PRIMARY KEY, password_snapshot TEXT);
    CREATE TABLE audit_logs (id INTEGER PRIMARY KEY, details TEXT);
    INSERT INTO students VALUES (1, 'S-100', 'Synthetic Student', 'DO_NOT_EXPORT_HASH', 'BSIT', '2', 'A', 'Female');
    INSERT INTO teachers VALUES (1, 'T-200', 'Synthetic Teacher', 'DO_NOT_EXPORT_TEACHER_HASH');
    INSERT INTO schedules VALUES (7, '1', 'BSIT', '2', 'A', 'IT101', 'Friday', '08:00:00', '09:00:00');
    INSERT INTO student_classes VALUES (4, '1', '7');
    INSERT INTO attendance VALUES (11, '1', '7', '2026-10-16', '08:00:01', 'LATE', 'QR');
    INSERT INTO qr_codes VALUES (1, 'DO_NOT_EXPORT_QR_TOKEN');
    INSERT INTO face_data VALUES (1, 'DO_NOT_EXPORT_FACE_ENCODING', 'DO_NOT_EXPORT_FACE_PATH');
    INSERT INTO fingerprints VALUES (1, 'DO_NOT_EXPORT_FINGERPRINT_ID');
    INSERT INTO attendance_sessions VALUES (1, 'DO_NOT_EXPORT_SESSION_TOKEN');
    INSERT INTO login_history VALUES (1, 'DO_NOT_EXPORT_LOGIN_SNAPSHOT');
    INSERT INTO audit_logs VALUES (1, 'DO_NOT_EXPORT_AUDIT_PAYLOAD');
    """)
    db.commit()
    db.close()


def test_export_omits_credentials_tokens_and_biometrics(tmp_path):
    database = tmp_path / "legacy.db"
    output = tmp_path / "export"
    make_legacy_db(database)
    summary = export(database, output)
    assert summary["exported"]["accounts"] == 2
    assert summary["exported"]["schedules"] == 1
    assert summary["exported"]["enrollments"] == 1
    assert summary["exported"]["attendance"] == 1
    contents = "\n".join(p.read_text(encoding="utf-8-sig", errors="ignore") for p in output.iterdir() if p.is_file())
    for forbidden in ("DO_NOT_EXPORT_HASH", "DO_NOT_EXPORT_TEACHER_HASH", "DO_NOT_EXPORT_QR_TOKEN",
                      "DO_NOT_EXPORT_FACE_ENCODING", "DO_NOT_EXPORT_FACE_PATH", "DO_NOT_EXPORT_FINGERPRINT_ID",
                      "DO_NOT_EXPORT_SESSION_TOKEN", "DO_NOT_EXPORT_LOGIN_SNAPSHOT", "DO_NOT_EXPORT_AUDIT_PAYLOAD"):
        assert forbidden not in contents


def test_sql_builder_generates_transactional_import_with_role_mapping(tmp_path):
    database = tmp_path / "legacy.db"
    output = tmp_path / "export"
    make_legacy_db(database)
    export(database, output)
    mapping_file = tmp_path / "account_map.csv"
    with mapping_file.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["legacy_account_id", "role", "target_account_id"])
        writer.writeheader()
        writer.writerows([
            {"legacy_account_id": "s-100", "role": "STUDENT", "target_account_id": "new-s-100"},
            {"legacy_account_id": "t-200", "role": "TEACHER", "target_account_id": "new-t-200"},
        ])
    sql_path = tmp_path / "import.sql"
    summary = build(output, sql_path, mapping_file)
    sql = sql_path.read_text(encoding="utf-8")
    assert summary["schedules"] == 1
    assert summary["attendance_rows"] == 1
    assert "BEGIN;" in sql and "COMMIT;" in sql
    assert "new-t-200" in sql and "new-s-100" in sql
    assert "AT TIME ZONE 'Asia/Manila'" in sql
    assert "ON CONFLICT (student_id, schedule_id, attendance_date) DO NOTHING" in sql
    assert "DO_NOT_EXPORT" not in sql


def test_export_summary_explicitly_excludes_sensitive_rows(tmp_path):
    database = tmp_path / "legacy.db"
    output = tmp_path / "export"
    make_legacy_db(database)
    export(database, output)
    summary = json.loads((output / "migration_summary.json").read_text(encoding="utf-8"))
    assert summary["credentials_exported"] is False
    assert summary["biometric_or_qr_secrets_exported"] is False
    assert summary["rows_reviewed_but_not_exported_as_sensitive_data"]["face_data_file_paths_or_encodings"] == 1
