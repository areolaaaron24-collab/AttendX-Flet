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

## Important backend compatibility limits

- The web schema uses lowercase roles (`student`, `teacher`) and tables including `profiles`, `subjects`, `schedules`, `enrollments`, `attendance`, `qr_tokens`, `face_templates`, and `attendance_sessions`.
- Do not apply this repository's old Flet migrations `001`–`006` to the existing AttendX-Web project; they describe a different schema.
- The compatibility migration in AttendX-Web is source code only and has not been applied to the live database. Do not run it against production until all table columns, constraints, RLS policies, RPC signatures, and Edge Function behavior are reviewed and tested.
- Do not redeploy Flet Edge Functions over the existing web functions. Registration depends on server-side Supabase secrets configured in the existing project.
- A successful Python compile or GitHub Actions test run does not prove the live Supabase project has every RPC used by Flet. Test registration and login with a test account first, then verify each attendance method and permissions.

## If setup still fails

Run this from the project root. It reports only booleans and the public URL, never the key:

```powershell
python -c "from attendx.core.config import Settings; s=Settings.from_env(); print('URL configured:', bool(s.supabase_url)); print('Anon key configured:', bool(s.supabase_key)); print('URL:', s.supabase_url)"
```

If the key flag is false, check that `.env` is in the same folder as `main.py`, the variable is spelled `SUPABASE_ANON_KEY`, and the value is the legacy anon/public key from the correct project.