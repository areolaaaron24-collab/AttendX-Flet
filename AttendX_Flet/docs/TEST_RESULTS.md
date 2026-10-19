# Test results and verification limits

## Checks run in the build environment

The project was checked using the local Python 3.13 interpreter.

- `python -m compileall -q main.py attendx scripts tests` — passed; all Python source files compiled.
- `pytest -q` — **33 passed**. Tests cover attendance timing boundaries, validation and role constraints, pagination behavior, privacy-conscious SQLite export/SQL generation, and static SQL-security/migration invariants.
- `python scripts/export_sqlite_migration.py --help` — passed.
- `python scripts/build_import_sql.py --help` — passed.
- Migration tests use a **synthetic temporary SQLite database**. No real legacy student database, account data or biometric file is used in the tests.
- Archive contents are checked to exclude `.env`, legacy SQLite/database files, local migration exports, generated SQL, caches and bytecode.

## Tests not completed here

The environment did not have the `flet` and `supabase` runtime package distributions installed, and attempts to install them were blocked by unavailable package-index/DNS access. Therefore a true `python main.py` GUI/import smoke test could not be completed here. Syntax compilation does not confirm that every Flet control or Supabase client method works with the exact versions installed on your machine.

The following also require your configuration or real devices and remain unverified:

- Supabase project URL/key, migrations applied to a live PostgreSQL project, deployed Edge Functions, Auth email/SMTP delivery, and role/RLS behavior over the network.
- Server-side SQL execution against your project's actual PostgreSQL version/extensions; optional `pg_cron` job installation.
- Webcam access, OpenCV behavior, dlib/face-recognition native install, lighting/false-match tests, face privacy/consent workflow, and camera cleanup on physical hardware.
- Actual AS608/R307 model, firmware, serial driver, USB adapter, enrollment/identify round-trips and resource release. The inspected legacy fingerprint module itself did not contain a complete end-to-end enrollment/verification implementation.
- Windows/Linux packaging; Android/iOS builds, app permissions, signing, store submission, app sandbox exports and native mobile camera integration.
- Legacy data mapping and report reconciliation on a production-like data copy.

## Recommended acceptance run before production

1. Install the requirements in a clean Python 3.11+ virtual environment and run the GUI/import check.
2. Apply migrations to a separate test project, deploy functions, then test registration/login/recovery and denied access paths for both roles.
3. Create a test class and schedule, test a student enrollment, attendance before start (must reject), exact start, +14:59 and +15:00, duplicate scans, session end, and ABSENT finalization.
4. Try each attendance method with supported real hardware and confirm that Exit frees devices without removing records.
5. Generate Excel/CSV/PDF reports and reconcile them to a controlled attendance set.
6. Run the migration export/import against a copy and compare per-table counts before approving final data migration.
