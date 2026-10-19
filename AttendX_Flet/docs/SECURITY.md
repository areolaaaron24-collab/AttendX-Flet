# Security and privacy notes

AttendX handles student records and potentially biometric identifiers. Treat production data as restricted educational information and obtain the school's privacy/security approval before enrolling real people.

## Credentials and Auth

- The desktop/mobile client may contain only a Supabase publishable/anon key. This key is not an admin credential; security depends on PostgreSQL RLS and the server-side RPC policies.
- A service-role or secret key must never be compiled into the app, copied into `.env`, committed, placed in an Edge Function response, or embedded in a build artifact. Privileged account operations belong in Supabase Edge Functions.
- `.env` is ignored by Git. Commit `.env.example` only, with placeholders. Rotate secrets that have ever been exposed.
- Use Auth email delivery/SMTP configuration and the approved password-reset redirect URL. Never log passwords, full tokens, or authorization headers.

## Database authorization

- RLS is enabled on exposed application tables; do not disable it to clear a permission error.
- Student queries must be scoped to the signed-in student. Teacher data access must be restricted to schedules/classes that teacher owns or is assigned to.
- Attendance writes are intended to use RPCs that validate session, schedule, role/enrollment, time and duplicate constraints. Do not grant direct client insert/update privileges on `attendance_records`.
- QR values are random tokens and the database stores hashes. Expire/revoke passes when no longer valid; never expose a service/session token in a report or log.
- The teacher directory view exposes only names/IDs for active teachers. It is deliberately narrower than the private profile table.
- Review every migration against the actual Supabase project and run authorization-negative tests before production.

## Biometric handling

- Face recognition is local on the authorized teacher device; a 128-number face descriptor (embedding), not a camera image, is stored server-side. **An embedding is still sensitive biometric data.** Limit access and retention, require meaningful consent/notice, support deletion according to policy, and do not export templates with reports.
- Fingerprint enrollment stores a sensor-local template ID and a label, not a fingerprint image/scan. The physical sensor keeps its template, so define what happens when hardware is reset/replaced.
- No liveness/anti-spoof model or secure sensor attestation is implemented or claimed. Local biometric matching can be tampered with on a compromised authorized teacher computer; the server then validates attendance authorization but cannot prove the sensor match itself occurred.
- Face tolerance and lookalike rejection are not substitutes for measured false-accept/false-reject testing. Do not treat an automatic match as infallible; provide an authorized fallback and audit path.
- Do not use the phone's built-in fingerprint sensor via this app. It is not an AS608/R307 serial reader.

## Operational safeguards

- Restrict Supabase project dashboard/database-admin membership to authorized maintainers and enable MFA for admin accounts.
- Back up before schema changes and data imports; perform trial imports in a separate project.
- Decide and document deletion/retention timelines for student profiles, attendance, face descriptors, audit events and exports. Use the minimum data required for the school's approved purpose.
- Keep exports in an access-controlled directory; they can contain names and attendance status. Securely delete temporary migration files after verification.
- Establish a recovery owner, incident procedure and audit review. Availability of point-in-time recovery/automatic backups depends on the actual Supabase plan/configuration.
