# START HERE — AttendX Flet for Windows

This is the **new project folder**. Do not run these commands from `C:\SchoolAttendanceSystem_apk` unless that is where you extracted this ZIP. The old Tkinter folder and this Flet folder are separate projects.

## 1) Extract and open the actual project folder

1. Download `AttendX_Flet_Complete.zip`.
2. In File Explorer, right-click the ZIP and choose **Extract All**.
3. Open the extracted folder named `AttendX_Flet` (the folder that contains `main.py`, `requirements.txt`, and `.env.example`).
4. You can double-click `Setup_AttendX_Windows.bat`, or use the PowerShell command below from that folder.

Before continuing, the folder must contain these files:

- `main.py`
- `requirements.txt`
- `requirements-desktop.txt`
- `.env.example`
- `supabase\migrations\`

## 2) Install on your existing Python 3.12

Your error showed Python 3.12 is installed. Python 3.11 is not required specifically. The project requires Python 3.11 or newer, so the setup script uses the `python` command that Windows already recognizes.

Open PowerShell in this folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\Setup_AttendX_Windows.ps1
```

The installer creates `.venv`, installs the core and desktop-camera dependencies, and creates `.env` from `.env.example` if needed. It never requires virtual-environment activation.

If it reports a DNS or `pypi.org` error, that is an internet/package-download problem, not a missing project file. Connect to working internet (a phone hotspot can help) and run the setup script again. This ZIP contains the source code and setup files, not a bundled Python installer or offline wheel repository.

## 3) Run the app

After the installer finishes, double-click `Run_AttendX.bat`, or run:

```powershell
.\.venv\Scripts\python.exe main.py
```

The app can open the portal screen without Supabase credentials. Real login, registration, accounts, and attendance require your own Supabase project to be configured.

## 4) Connect Supabase later

1. In the same folder, open `.env` in a text editor.
2. Replace the sample `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` values with your project's URL and publishable/anon key.
3. Apply `supabase\migrations\001_core_schema.sql` through `006_class_match_enrollment_policy.sql` in order, or use Supabase CLI as described in `README.md`.
4. Deploy the four Edge Functions listed in `README.md`.
5. Test with non-production accounts first.

**Never put a Supabase service-role/secret key in `.env` or the Flet client.** Never copy your old SQLite database, student exports, passwords, or biometric files into GitHub.

## 5) Optional hardware dependencies

The desktop QR camera path uses OpenCV, installed by the Windows setup. Face recognition additionally needs `requirements-face.txt` and a compatible `dlib`/C++ toolchain; it may not install cleanly on every Windows/Python combination. For a compatible serial fingerprint reader, install `requirements-fingerprint.txt`. That driver path must be validated with the exact AS608/R307 model, firmware, and USB-to-serial adapter.

If a camera or reader is unavailable, the app must display an error instead of fabricating a successful scan. Read `docs/PLATFORM_SUPPORT.md` and `docs/TEST_RESULTS.md` before using real student records.
