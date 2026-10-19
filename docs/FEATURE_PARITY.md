# AttendX feature parity: Tkinter source → Flet replacement

This map was prepared by inspecting the supplied source archive and its connected modules (especially `main2.py`, `database.py`, `auth.py`, `attendance.py`, `audit_attendance.py`, `qr_system.py`, `face_system.py`, `face_registration.py`, `fingerprint_system.py`, `matching.py`, and supporting teacher/student/profile/report utilities). The original folder and local data files are not changed or copied into this deliverable.

**Status legend:** **Implemented in code** means the replacement workflow and code path exist; **configuration-dependent** means Supabase credentials/schema or an optional dependency are needed; **hardware/platform validation pending** means the implementation cannot be confirmed without the real supported device/OS; **legacy incomplete** means the inspected Tkinter source did not provide a complete working integration to preserve.

| Original workflow / behavior | Flet replacement | Status / notes |
|---|---|---|
| Intro/portal and separate teacher/student entry | `attendx/ui/pages/portal.py`, `auth.py`, `app_controller.py` | Implemented in code; Supabase settings required for real login. |
| Student/teacher login, registration, profile, logout | `services/auth_service.py`, `profile_service.py`, Supabase Auth Edge Functions | Registration accepts only Teacher/Student and validates names/sex/account IDs. Existing passwords are not migrated. |
| Global account ID uniqueness / profile data | `001_core_schema.sql`, `004_server_side_profile_validation.sql` | Database unique index and trigger validation; requires migrations applied. |
| Teacher dashboard statistics | `services/attendance_service.py`, `teacher.py`, database RPC | Implemented in code; live data/permissions need Supabase verification. |
| Subject catalogue and Add Subject | `services/teacher_service.py`, `teacher.py`, `subjects` table | Implemented in code; authenticated teacher authoring policies apply. |
| Class/course/year/section and schedule creation/listing | `teacher_service.py`, `student_service.py`, `schedules/classes` tables | Implemented in code; server constraints enforce schedule times/unique combinations. |
| Student enrollment and teacher's class/student list | `student_service.py`, `teacher_service.py`, enrollment tables and RLS | Implemented in code; teacher sees only authorized students through assigned schedules. |
| QR per-student pass | `services/qr_service.py`, `qr_tokens` table | Implemented in code. Raw QR token is returned once; only a hash is stored. |
| Teacher session QR generation / student scan | `services/attendance_service.py`, attendance session RPCs and `attendance.py` | Implemented in code; camera/scanner hardware and live server test pending. |
| Continuous face registration/recognition flow | `camera_service.py`, `biometric_service.py`, `attendance.py`, `face_templates` RPC | Optional face-recognition/dlib dependency. Loop is designed to remain open until Exit and release camera resources. No anti-spoof/liveness model is claimed. |
| Face matching and twin/lookalike ambiguity | Nearest 128D descriptor with ambiguity rejection in `biometric_service.py`; database duplicate-near-match check | Implemented in code. Actual accuracy, demographic performance and camera behavior require supervised validation; a face descriptor is sensitive biometric data. |
| Fingerprint screen / AS608/R307 hardware | `services/fingerprint_service.py`, fingerprint setup/scan UI | Serial adapter path is present, but legacy fingerprint module was a device/setup stub rather than a complete enrollment and verification system. Actual sensor model/firmware/serial protocol and permissions remain hardware validation pending. |
| Attendance status and duplicate prevention | `core/attendance_rules.py`, PostgreSQL RPCs and unique constraint | Implemented and unit-tested at exact timing boundaries. Uses Asia/Manila timezone. Pre-start scans are rejected; exact start is Present, +14:59 is Late and +15:00 is Late Absent. ABSENT is finalized after session end when no valid record exists. |
| Continuous scan, feedback, Exit and camera cleanup | `attendance.py`, QR/camera/fingerprint services | Implemented in code; hardware release behavior requires live test. Exit does not delete saved records. |
| Attendance history/audit/database tools | history UI, `attendance_service.py`, `audit_service.py`, Supabase database verification | Replaced legacy direct database-browser functionality with authorized live database checks/history. This is not an unrestricted SQL console. |
| Excel report per subject / CSV/PDF exports | `services/report_service.py`, Reports page | Real records are queried from the configured backend and exported locally. Excel uses OpenPyXL; PDF uses ReportLab. Validate report totals on a seeded test database. |
| Legacy local SQLite data | `scripts/export_sqlite_migration.py`, `scripts/build_import_sql.py` | Safe staged migration; credentials and biometric tokens/templates intentionally excluded. Run and verify manually before production import. |
| TC / Teacher Coordinator role | Not included | Explicitly removed; only Teacher and Student exist. |
| Grades or unrelated academic features | Not added | Not implemented unless present in supplied source and backed by its schema. |
| Notifications | No full push-notification service added | No unsupported notifications are claimed; mobile push delivery needs separate infrastructure. |

## Source and implementation boundaries

The legacy application mixes UI and SQLite work. The replacement separates UI pages, services, validation, settings, attendance rules and database migrations. The new application should not be described as an exact copy of every pixel or every internal implementation detail. It preserves the inspected user-facing workflows and migrates data into a server-authorized schema.

## Items to sign off before real use

- Apply migrations and deploy all Edge Functions in a test Supabase project.
- Test two-role authorization with direct API requests, including student-to-student and teacher-to-unassigned-class access attempts.
- Test QR expiry, duplicate attendance, session timing and scheduled absence finalization on the server.
- Validate face false matches, twins/lookalikes, lighting conditions, consent, fallback and deletion policy with actual school-approved procedures.
- Test each supported fingerprint model on its actual serial adapter, firmware and OS. Until this test passes, mark fingerprint attendance **not verified**.
- Verify Excel/CSV/PDF totals against controlled source data and separately review legacy migration row counts.
