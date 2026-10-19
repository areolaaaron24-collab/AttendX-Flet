# AttendX Smart Attendance System — Flet + Supabase

This repository is a **separate Flet implementation** created from the supplied Tkinter AttendX source and design assets. The source ZIP is not modified, and the original SQLite databases, passwords, QR/session secrets, biometric image files and face templates are deliberately **not bundled**.

The application uses Flet for its UI, Supabase Auth and PostgreSQL for live accounts/data, PostgreSQL RLS and security-definer RPCs for server-enforced permissions, and optional desktop hardware libraries for camera/face/fingerprint features. It does not silently fall back to a fake database when the Supabase URL/key are missing.

## What is included

- Portal selection, Teacher and Student login/registration/password-recovery flows, role-aware navigation, profile editing and settings.
- Teacher dashboard, students/enrollment, subjects, schedules, attendance center, scan/history, exports and database/connection verification tools.
- Student dashboard, subject/class enrollment, schedule and attendance history, personal QR pass, session QR scan, face registration and fingerprint setup.
- QR-based attendance, server-validated attendance RPCs, attendance status rules in `Asia/Manila`, duplicate prevention, audit events, and subject-based Excel/CSV/PDF reporting.
- Supabase schema, RLS policies, database-side registration validation, secure attendance RPCs, Edge Functions, tests, and migration tools.
- Supplied CSU logo and the design reference in `assets/`. The supplied CSU logo is used as provided; the reference image is kept for design traceability.

A feature map and known limitations are in [`docs/FEATURE_PARITY.md`](docs/FEATURE_PARITY.md), security notes in [`docs/SECURITY.md`](docs/SECURITY.md), platform requirements in [`docs/PLATFORM_SUPPORT.md`](docs/PLATFORM_SUPPORT.md), and actual test status in [`docs/TEST_RESULTS.md`](docs/TEST_RESULTS.md).

## 1. Requirements

Use Python 3.11 or newer (64-bit recommended). Create a project-specific virtual environment.

### Windows PowerShell (recommended)

Extract the ZIP, then open the **`AttendX_Flet` folder**—the same folder containing `main.py`, `requirements.txt`, and `.env.example`. You may use Python 3.11, 3.12, or newer (64-bit recommended); do not hard-code a Python version that is not installed.

The easiest route is to double-click `Setup_AttendX_Windows.bat`. Or run this from the project folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup_AttendX_Windows.ps1
```

The script creates `.venv`, installs core + desktop-camera dependencies, and copies `.env.example` to `.env`. It does not require activation. Run the UI using `Run_AttendX.bat` or:

```powershell
.\.venv\Scripts\python.exe main.py
```

If pip reports `Failed to resolve pypi.org`, `NameResolutionError`, or a proxy/network error, connect to a working internet connection and rerun setup. The project ZIP contains source/configuration files, not a bundled Python runtime or offline package wheel cache. Do not run setup from your old Tkinter folder; run it from the extracted `AttendX_Flet` folder.

### Linux / macOS

```bash
cd AttendX_Flet
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python main.py
```

For desktop QR camera support, the Windows setup installs `requirements-desktop.txt` (core requirements plus OpenCV/NumPy). On Linux/macOS, use:

```bash
pip install -r requirements-desktop.txt
```

Optional packages are intentionally separate because native dependencies differ by OS:

```bash
pip install -r requirements-face.txt         # face-recognition / dlib stack; desktop only
pip install -r requirements-fingerprint.txt  # USB/serial reader adapter
pip install -r requirements-dev.txt           # automated tests
```

The face-recognition dependency may require a C/C++ toolchain and compatible prebuilt wheels or a working dlib build. The fingerprint adapter is only for supported AS608/R307-family sensors that expose a supported serial protocol; it cannot use the fingerprint sensor built into a phone or laptop OS.

## 2. Configure Supabase

1. Create a Supabase project and keep the project URL and **publishable/anon client key** available. Do not use a service-role/secret key in the Flet client.
2. Copy `.env.example` to `.env` and fill in only the values from your project:

   ```dotenv
   SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
   SUPABASE_PUBLISHABLE_KEY=YOUR_PUBLIC_PUBLISHABLE_OR_ANON_KEY
   ATTENDX_LOG_LEVEL=INFO
   ATTENDX_ENV=development
   ```

3. The starter app deliberately reports a configuration error until real values are supplied; it does not pretend to be connected.
4. **IMPORTANT — existing AttendX-Web database compatibility:** Do **not** run `supabase db push` or apply this repository's `supabase/migrations/001` through `006` to the existing AttendX-Web Supabase project. These migrations define a different schema (including `class_enrollments`, `attendance_records`, and uppercase roles), while AttendX-Web uses `enrollments`, `attendance`, and lowercase roles. A compatibility migration has been added to the AttendX-Web repository at `supabase/migrations/202610190001_flet_desktop_compatibility.sql`; it is source code only and has **not** been applied to the live database or validated against production. Review and test it in a separate Supabase project before considering deployment. Never use production student data for this test.
5. **Do not redeploy this repository's Edge Functions over the existing AttendX-Web production functions yet.** The Web app already has its own account registration, login, password recovery, QR, face, and fingerprint functions. Keep using the deployed AttendX-Web versions unless the Flet/Web function differences have been reviewed and tested in a separate project.

   The functions use Supabase-provided server environment variables and perform privileged work server-side. Never copy a service-role/secret value into `.env`, Python source, GitHub, an Android/iOS package, or client logs.
6. Configure Supabase Auth's Site URL and Redirect URLs for the deployed `account-password-reset-page` URL. The default recovery redirect is `${SUPABASE_URL}/functions/v1/account-password-reset-page`. Configure SMTP/email delivery in Supabase before expecting password-recovery emails in production. If you change the recovery URL, set `ATTENDX_RECOVERY_REDIRECT_URL` as a **server-side Edge Function secret**, and keep it aligned with the Auth allowlist.
7. Use a new test account first. Registration supports only Teacher and Student. Do not create a TC role. Verify account creation, login, logout, permissions, password recovery, and attendance from two separate accounts before importing legacy records. Do not connect this Flet build to the existing AttendX-Web production database until the schema/RPC compatibility audit is complete.

### RLS and permissions

The SQL files set up tables, RLS, constraints, and controlled RPCs. Attendance is not written by a client-side direct insert; it uses server-side functions that check identity, role, schedule ownership/enrollment, session timing and duplicates. Apply all migrations before launching the application. Do not disable RLS to make a screen work.

## 3. Run and troubleshoot

```bash
python main.py
```

If there is no `.env`, a value is malformed, the project URL is unreachable, or the server denies access, the application should surface a readable configuration/connection/permission message. Check `logs/` if the configured logger has produced a log. Do not paste tokens or credentials into issues.

For Flet development mode, you can also use `flet run main.py` after installing the dependencies. Camera and face recognition require desktop packages and working camera permissions. The native mobile camera pipeline has not been implemented or validated in this project; mobile screens can package separately but hardware-dependent scanning is not yet equivalent to desktop scanning. See the platform-support document.

## 4. Migrate legacy SQLite data safely

Migration is a controlled one-time workflow, not a synchronization service. Back up the old source database before starting, and perform a trial import into a **separate test Supabase project** first. Review exported CSVs as sensitive student records.

1. Run the exporter against a copy of the original database (replace the path with the actual file):

   ```bash
   python scripts/export_sqlite_migration.py --db "PATH/TO/attendance.db" --out migration_export
   ```

2. Review `migration_export/migration_summary.json`, warnings, row counts and each CSV. The exporter intentionally omits old password hashes, QR/session tokens, raw face encodings/images, fingerprint secrets and old session/login payloads. Accounts must be re-created through Supabase Auth with new passwords.
3. Create accounts through the new registration/administrative workflow first. If an old account ID now maps to another ID, create a **local** `account_map.csv` with header `legacy_account_id,role,target_account_id` and one row per mapped account. Keep this private; do not commit it.
4. Build an import SQL script:

   ```bash
   python scripts/build_import_sql.py --export-dir migration_export --out migration_import.sql
   # Or, when using an account map:
   python scripts/build_import_sql.py --export-dir migration_export --account-map account_map.csv --out migration_import.sql
   ```

5. Read the generated SQL, confirm every mapping, back up the target, then run the script using the Supabase SQL Editor or another trusted database-admin connection. The SQL expects matching target `profiles`/Auth users to exist. It imports subject/class/schedule/enrollment/attendance history with ID remapping and duplicate conflict handling; it does **not** create Auth users or restore old passwords/biometrics.
6. Verify counts by role, enrollment, schedule, attendance date/status, and report totals. Keep the original copy read-only until a responsible owner signs off on migration results. Delete temporary CSVs and SQL securely when no longer required.

Never run a migration against the production project before a tested backup and a trial import. Supabase backup/PITR availability depends on your plan/settings; confirm your actual project's backup features. A privileged `pg_dump` or the project's dashboard backup is appropriate for a planned export, but do not put database passwords on the command line or into Git.

## 5. Tests and project quality checks

Install development requirements, then run:

```bash
python -m compileall -q main.py attendx scripts tests
pytest -q
```

The repository includes automated unit/static tests for attendance timing boundaries, account/name/role validation, and migration/security invariants. See [`docs/TEST_RESULTS.md`](docs/TEST_RESULTS.md) for what ran and what still requires your environment. A passing local unit suite is not the same as a completed remote Supabase, webcam, fingerprint or mobile acceptance test.

## 6. GitHub setup later

1. Create an empty private repository first if student project files/data are present.
2. Confirm `git status --ignored` and `git check-ignore .env migration_export migration_import.sql account_map.csv` before staging.
3. Review the staged diff. Only stage source, migrations, tests, docs and non-sensitive assets:

   ```bash
   git init
   git add .
   git status --short
   git commit -m "Create AttendX Flet and Supabase implementation"
   git branch -M main
   git remote add origin YOUR_PRIVATE_REPOSITORY_URL
   git push -u origin main
   ```

4. Do not upload `.env`, a database file, migrated CSVs, attendance exports, sensor IDs, biometric data, logs, or generated SQL with real account IDs. Rotate any secret that was ever committed.

## 7. Structure

```text
main.py
assets/                      # AttendX branding, provided CSU logo, UI reference
attendx/core/                # settings, validation, logging, time/status rules
attendx/services/            # Auth, Supabase, attendance, QR, biometrics, reports, migration
attendx/ui/                  # theme, reusable controls, controller and portal pages
supabase/migrations/         # schema, RLS, RPCs, field validation, safe directory
supabase/functions/          # account registration/login/password reset Edge Functions
scripts/                     # privacy-conscious SQLite export + SQL import builder
tests/                       # automated tests
```

## Design note

The UI uses a navy base, blue/cyan highlights and CSU-inspired gold/white accents. The original CSU logo file is in `assets/csu_logo.png`; swap that file in the same location if an updated approved logo is supplied. No AI-generated or substitute crest is used in place of the supplied file.
