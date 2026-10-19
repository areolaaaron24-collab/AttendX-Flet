# Existing AttendX Supabase Setup (Flet Desktop)

Use the same Supabase project as AttendX-Web. Do not create another project.

- Project URL: `https://ligzoiktrdwcdqpkaudr.supabase.co`
- Supabase project reference: `ligzoiktrdwcdqpkaudr`
- Source of truth: the existing AttendX-Web PostgreSQL schema and deployed Edge Functions.

## Local setup

1. In the AttendX-Flet repository root (the folder containing `main.py`), copy `.env.example` to `.env`.
2. Open the existing project in Supabase Dashboard and navigate to Project Settings → API Keys → Legacy API Keys.
3. Copy the public `anon` / `public` key into `SUPABASE_ANON_KEY` in `.env`. The current Python Auth client needs this legacy JWT key; a `sb_publishable_...` key alone is not a substitute for this Auth flow.
4. Keep `SUPABASE_URL` set to the URL above. `SUPABASE_PUBLISHABLE_KEY` may remain blank unless you have the public publishable key and the Edge Function requests are configured to use it.
5. Save `.env`, restart the terminal/app, and run `python main.py`.

Never place a service-role key, secret key, database password, or other server secret in `.env`, source code, screenshots, or GitHub. Do not share your `.env` file.

## Attendance Center compatibility and safe rollout

- The Attendance Center's supported QR path is **teacher scans the student's personal QR Pass** for the selected schedule. This uses the existing AttendX-Web `verify-qr` Edge Function and `record_attendance` RPC. The old teacher-generated Session QR button was removed from the Flet screen because it depends on an un-applied compatibility migration.
- Fingerprint attendance uses the existing `register-fingerprint` Edge Function and `fingerprint_templates` table. It requires a compatible AS608/R307 reader over serial, `pyserial` + `pyfingerprint`, and the same configured reader/COM port for enrollment and scanning.
- The web app's `face_templates` table stores **face-api** descriptors. Flet uses Python `face_recognition` descriptors, which are not interchangeable. Flet now stores these in a separate `flet_face_templates` table so it cannot overwrite Web face registrations.
- To enable Flet face enrollment/recognition on the existing project, review and apply only the new additive migration `AttendX-Web/supabase/migrations/202610200001_flet_face_templates.sql` in Supabase SQL Editor. It creates the isolated table, student-owned RLS policies, and a teacher-authorized RPC. It does not replace Web face templates or change attendance records. Back up the project and review the SQL before applying it.
- Do **not** apply the older `202610190001_flet_desktop_compatibility.sql` blindly. It changes attendance/session RPCs and needs a separate production-schema review. Do not apply this repository's Flet migrations `001`–`006`; they describe a different schema.
- Do not redeploy Flet Edge Functions over existing Web functions. Registration depends on server-side Supabase secrets configured in the existing project.
- A successful Python compile or GitHub Actions test run does not prove live Supabase, camera, face model, or fingerprint hardware behavior. Test each method with a test account and enrolled test student before classroom use.

## If setup still fails

Run this from the project root. It reports only booleans and the public URL, never the key:

```powershell
python -c "from attendx.core.config import Settings; s=Settings.from_env(); print('URL configured:', bool(s.supabase_url)); print('Anon key configured:', bool(s.supabase_key)); print('URL:', s.supabase_url)"
```

If the key flag is false, check that `.env` is in the same folder as `main.py`, the variable is spelled `SUPABASE_ANON_KEY`, and the value is the legacy anon/public key from the correct project.