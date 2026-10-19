# AttendX Flet deliverable manifest

This is a separate replacement project for the uploaded Tkinter source. It does not include the original `attendance.db` / `database/attendance.db`, saved student accounts, credentials, face images, face encodings, fingerprint data, or prior CSV/SQL exports.

## Deliverable map

- `main.py`, `attendx/ui/`: Flet portal, authentication, teacher/student workspaces, attendance screens, profile/settings, navigation.
- `attendx/core/`: settings, input validation, Asia/Manila attendance time rules, logging, pagination.
- `attendx/services/`: Supabase/Auth/data services, QR token handling, camera/face/fingerprint adapters, reports, attendance/audit, migration support.
- `supabase/migrations/001` through `006`: PostgreSQL tables, constraints/indexes, RLS, attendance RPCs, validation, authorized directory/enrollment rules.
- `supabase/functions/`: account registration, account-ID login, password reset and recovery page.
- `scripts/`: privacy-aware legacy SQLite export and staged SQL-import builder.
- `tests/`: unit/static tests.
- `docs/`: source feature map, platform limitations, security and actual test status.
- `assets/`: supplied CSU logo, AttendX logo and design reference.

## Automated checks run for this archive

- Python `compileall`: passed.
- `pytest -q`: 33 passed.
- Migration utility `--help` checks: passed in the build environment.
- ZIP content scan: no `.env`, legacy SQLite database, migration export, generated import SQL, cache folder or `.pyc` file is included.

## Not represented as completed acceptance tests

No live Supabase project was configured. Runtime Flet GUI imports and controls, PostgreSQL migrations/RLS on a real project, actual webcam/face matches, AS608/R307 hardware, or Windows/Linux/Android/iOS builds have not passed end-to-end acceptance testing in the build environment. Review `docs/TEST_RESULTS.md`, `docs/FEATURE_PARITY.md`, and `docs/PLATFORM_SUPPORT.md` before production deployment.
