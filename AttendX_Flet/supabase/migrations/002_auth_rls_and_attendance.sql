-- Secure role/profile trigger, RLS policies, and server-side attendance operations.

create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public, auth
as $$
declare
  v_role text;
  v_account_id text;
  v_first text;
  v_last text;
  v_sex text;
begin
  v_role := upper(coalesce(new.raw_user_meta_data->>'role', ''));
  v_account_id := lower(regexp_replace(btrim(coalesce(new.raw_user_meta_data->>'account_id', '')), '\s+', ' ', 'g'));
  v_first := regexp_replace(btrim(coalesce(new.raw_user_meta_data->>'first_name', '')), '\s+', ' ', 'g');
  v_last := regexp_replace(btrim(coalesce(new.raw_user_meta_data->>'last_name', '')), '\s+', ' ', 'g');
  v_sex := initcap(btrim(coalesce(new.raw_user_meta_data->>'sex', '')));

  if v_role not in ('TEACHER', 'STUDENT') then
    raise exception 'Only Teacher and Student accounts are supported.';
  end if;
  if v_account_id = '' or v_first = '' or v_last = '' then
    raise exception 'Account ID, first name, and last name are required.';
  end if;
  if v_first ~ '[0-9]' or v_last ~ '[0-9]' or coalesce(new.raw_user_meta_data->>'middle_name', '') ~ '[0-9]' then
    raise exception 'Name fields must not contain numbers.';
  end if;
  if v_sex not in ('Male', 'Female') then
    raise exception 'Sex must be Male or Female.';
  end if;
  if v_role = 'STUDENT' and (
    nullif(btrim(coalesce(new.raw_user_meta_data->>'course', '')), '') is null or
    nullif(btrim(coalesce(new.raw_user_meta_data->>'year_level', '')), '') is null or
    nullif(btrim(coalesce(new.raw_user_meta_data->>'section', '')), '') is null
  ) then
    raise exception 'Student course, year, and section are required.';
  end if;

  insert into public.profiles (
    id, account_id, role, first_name, last_name, middle_name, suffix, sex,
    recovery_email, course, year_level, section, department, office
  ) values (
    new.id, v_account_id, v_role, v_first, v_last,
    regexp_replace(btrim(coalesce(new.raw_user_meta_data->>'middle_name', '')), '\s+', ' ', 'g'),
    regexp_replace(btrim(coalesce(new.raw_user_meta_data->>'suffix', '')), '\s+', ' ', 'g'),
    v_sex,
    nullif(lower(btrim(coalesce(new.raw_user_meta_data->>'recovery_email', ''))), ''),
    nullif(regexp_replace(btrim(coalesce(new.raw_user_meta_data->>'course', '')), '\s+', ' ', 'g'), ''),
    nullif(regexp_replace(btrim(coalesce(new.raw_user_meta_data->>'year_level', '')), '\s+', ' ', 'g'), ''),
    nullif(regexp_replace(btrim(coalesce(new.raw_user_meta_data->>'section', '')), '\s+', ' ', 'g'), ''),
    nullif(regexp_replace(btrim(coalesce(new.raw_user_meta_data->>'department', '')), '\s+', ' ', 'g'), ''),
    nullif(regexp_replace(btrim(coalesce(new.raw_user_meta_data->>'office', '')), '\s+', ' ', 'g'), '')
  );
  return new;
end;
$$;

drop trigger if exists on_auth_user_created_attendx on auth.users;
create trigger on_auth_user_created_attendx
after insert on auth.users
for each row execute function public.handle_new_auth_user();

create or replace function public.is_teacher(p_user_id uuid default auth.uid())
returns boolean language sql stable security definer set search_path = public as $$
  select exists(select 1 from public.profiles p where p.id = p_user_id and p.role = 'TEACHER' and p.is_active = true)
$$;

create or replace function public.is_student(p_user_id uuid default auth.uid())
returns boolean language sql stable security definer set search_path = public as $$
  select exists(select 1 from public.profiles p where p.id = p_user_id and p.role = 'STUDENT' and p.is_active = true)
$$;

create or replace function public.teacher_owns_schedule(p_schedule_id bigint, p_teacher_id uuid default auth.uid())
returns boolean language sql stable security definer set search_path = public as $$
  select exists(select 1 from public.schedules s where s.id = p_schedule_id and s.teacher_id = p_teacher_id)
$$;

create or replace function public.student_enrolled(p_student_id uuid, p_schedule_id bigint)
returns boolean language sql stable security definer set search_path = public as $$
  select exists(select 1 from public.class_enrollments e where e.student_id = p_student_id and e.schedule_id = p_schedule_id)
$$;

create or replace function public.protect_profile_identity()
returns trigger language plpgsql set search_path = public as $$
begin
  if new.id <> old.id or new.account_id <> old.account_id or new.role <> old.role or new.is_active <> old.is_active then
    raise exception 'Account ID, role, and active state cannot be changed from the client.';
  end if;
  if new.student_status <> old.student_status and current_user in ('authenticated', 'anon') then
    raise exception 'Student status can only be changed by a trusted server operation.';
  end if;
  return new;
end;
$$;
drop trigger if exists profiles_protect_identity on public.profiles;
create trigger profiles_protect_identity before update on public.profiles for each row execute function public.protect_profile_identity();

alter table public.profiles enable row level security;
alter table public.subjects enable row level security;
alter table public.classes enable row level security;
alter table public.schedules enable row level security;
alter table public.class_enrollments enable row level security;
alter table public.attendance_sessions enable row level security;
alter table public.attendance_records enable row level security;
alter table public.qr_tokens enable row level security;
alter table public.face_templates enable row level security;
alter table public.fingerprint_credentials enable row level security;
alter table public.audit_logs enable row level security;
alter table public.login_history enable row level security;

-- Profiles: users see their own profile; a teacher sees students enrolled in their own schedules.
drop policy if exists profiles_read_scope on public.profiles;
create policy profiles_read_scope on public.profiles for select to authenticated using (
  id = auth.uid() or (
    public.is_teacher(auth.uid()) and role = 'STUDENT' and exists (
      select 1 from public.class_enrollments e join public.schedules s on s.id = e.schedule_id
      where e.student_id = profiles.id and s.teacher_id = auth.uid()
    )
  )
);
drop policy if exists profiles_update_own on public.profiles;
create policy profiles_update_own on public.profiles for update to authenticated using (id = auth.uid()) with check (id = auth.uid());

-- Subject catalog is visible to signed-in users; write access belongs to teachers.
drop policy if exists subjects_read_authenticated on public.subjects;
create policy subjects_read_authenticated on public.subjects for select to authenticated using (true);
drop policy if exists subjects_teacher_insert on public.subjects;
create policy subjects_teacher_insert on public.subjects for insert to authenticated with check (public.is_teacher(auth.uid()) and (created_by is null or created_by = auth.uid()));
drop policy if exists subjects_teacher_update on public.subjects;
create policy subjects_teacher_update on public.subjects for update to authenticated using (public.is_teacher(auth.uid())) with check (public.is_teacher(auth.uid()));
drop policy if exists subjects_teacher_delete on public.subjects;
create policy subjects_teacher_delete on public.subjects for delete to authenticated using (public.is_teacher(auth.uid()));

-- Classes visible to signed-in users because the student Add Subject flow browses schedules.
drop policy if exists classes_read_authenticated on public.classes;
create policy classes_read_authenticated on public.classes for select to authenticated using (true);
drop policy if exists classes_teacher_insert on public.classes;
create policy classes_teacher_insert on public.classes for insert to authenticated with check (public.is_teacher(auth.uid()));
drop policy if exists classes_teacher_update on public.classes;
create policy classes_teacher_update on public.classes for update to authenticated using (
  public.is_teacher(auth.uid()) and exists(select 1 from public.schedules s where s.class_id = classes.id and s.teacher_id = auth.uid())
) with check (public.is_teacher(auth.uid()));

-- Teachers manage their own schedules. Students can discover active offerings and see enrolled schedules.
drop policy if exists schedules_read_scope on public.schedules;
create policy schedules_read_scope on public.schedules for select to authenticated using (
  teacher_id = auth.uid() or (public.is_student(auth.uid()) and is_active = true) or public.student_enrolled(auth.uid(), id)
);
drop policy if exists schedules_teacher_insert on public.schedules;
create policy schedules_teacher_insert on public.schedules for insert to authenticated with check (public.is_teacher(auth.uid()) and teacher_id = auth.uid());
drop policy if exists schedules_teacher_update on public.schedules;
create policy schedules_teacher_update on public.schedules for update to authenticated using (teacher_id = auth.uid() and public.is_teacher(auth.uid())) with check (teacher_id = auth.uid() and public.is_teacher(auth.uid()));
drop policy if exists schedules_teacher_delete on public.schedules;
create policy schedules_teacher_delete on public.schedules for delete to authenticated using (teacher_id = auth.uid() and public.is_teacher(auth.uid()));

-- Student enrollments are schedule-specific, preserving the original student_classes workflow.
drop policy if exists class_enrollments_read_scope on public.class_enrollments;
create policy class_enrollments_read_scope on public.class_enrollments for select to authenticated using (
  student_id = auth.uid() or public.teacher_owns_schedule(schedule_id)
);
drop policy if exists class_enrollments_student_insert on public.class_enrollments;
create policy class_enrollments_student_insert on public.class_enrollments for insert to authenticated with check (
  student_id = auth.uid() and public.is_student(auth.uid()) and exists(select 1 from public.schedules s where s.id = schedule_id and s.is_active = true)
);
drop policy if exists class_enrollments_delete_scope on public.class_enrollments;
create policy class_enrollments_delete_scope on public.class_enrollments for delete to authenticated using (
  student_id = auth.uid() or public.teacher_owns_schedule(schedule_id)
);

-- Session access is limited to the teacher and students actually enrolled in the session schedule.
drop policy if exists sessions_read_scope on public.attendance_sessions;
create policy sessions_read_scope on public.attendance_sessions for select to authenticated using (
  teacher_id = auth.uid() or (status = 'ACTIVE' and public.student_enrolled(auth.uid(), schedule_id))
);

-- Direct client writes to attendance are intentionally absent: RPCs validate role, enrolment, session and status.
drop policy if exists attendance_read_scope on public.attendance_records;
create policy attendance_read_scope on public.attendance_records for select to authenticated using (
  student_id = auth.uid() or public.teacher_owns_schedule(schedule_id)
);

-- Only the owning student can list their issued passes. Creating/revoking tokens uses trusted RPCs.
drop policy if exists qr_tokens_read_own on public.qr_tokens;
create policy qr_tokens_read_own on public.qr_tokens for select to authenticated using (student_id = auth.uid());

-- Face descriptor access is limited to its student and a teacher with an enrolled schedule for that student.
drop policy if exists face_templates_read_scope on public.face_templates;
create policy face_templates_read_scope on public.face_templates for select to authenticated using (
  student_id = auth.uid() or (
    public.is_teacher(auth.uid()) and exists (
      select 1 from public.class_enrollments e join public.schedules s on s.id = e.schedule_id
      where e.student_id = face_templates.student_id and s.teacher_id = auth.uid()
    )
  )
);
drop policy if exists face_templates_insert_own on public.face_templates;
create policy face_templates_insert_own on public.face_templates for insert to authenticated with check (student_id = auth.uid() and public.is_student(auth.uid()));
drop policy if exists face_templates_update_own on public.face_templates;
create policy face_templates_update_own on public.face_templates for update to authenticated using (student_id = auth.uid() and public.is_student(auth.uid())) with check (student_id = auth.uid() and public.is_student(auth.uid()));
drop policy if exists face_templates_delete_own on public.face_templates;
create policy face_templates_delete_own on public.face_templates for delete to authenticated using (student_id = auth.uid());

-- Fingerprint mapping is readable only by the owner or teachers in that student's class; writes use RPC.
drop policy if exists fingerprints_read_scope on public.fingerprint_credentials;
create policy fingerprints_read_scope on public.fingerprint_credentials for select to authenticated using (
  student_id = auth.uid() or (
    public.is_teacher(auth.uid()) and exists (
      select 1 from public.class_enrollments e join public.schedules s on s.id = e.schedule_id
      where e.student_id = fingerprint_credentials.student_id and s.teacher_id = auth.uid()
    )
  )
);

-- Audit and login histories never expose another user's sign-in history by default.
drop policy if exists audit_logs_read_own on public.audit_logs;
create policy audit_logs_read_own on public.audit_logs for select to authenticated using (actor_id = auth.uid());
drop policy if exists login_history_read_own on public.login_history;
create policy login_history_read_own on public.login_history for select to authenticated using (profile_id = auth.uid());

-- Explicit safe client privileges. RLS still decides which rows a user can access.
grant select on public.profiles, public.subjects, public.classes, public.schedules, public.class_enrollments,
  public.attendance_sessions, public.attendance_records, public.qr_tokens, public.face_templates,
  public.fingerprint_credentials, public.audit_logs, public.login_history to authenticated;
grant update (first_name, last_name, middle_name, suffix, sex, course, year_level, section, department, office)
  on public.profiles to authenticated;
grant insert, update, delete on public.subjects to authenticated;
grant insert, update on public.classes to authenticated;
grant insert, update, delete on public.schedules to authenticated;
grant insert, delete on public.class_enrollments to authenticated;
grant insert, update, delete on public.face_templates to authenticated;
grant usage, select on all sequences in schema public to authenticated;

create or replace function public.write_audit_event(
  p_action text, p_entity_type text default null, p_entity_id text default null, p_details jsonb default '{}'::jsonb
)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_role text;
begin
  if auth.uid() is null then raise exception 'Authentication required.'; end if;
  if length(coalesce(p_action, '')) < 1 or length(p_action) > 120 then raise exception 'Invalid audit action.'; end if;
  if length(coalesce(p_details, '{}'::jsonb)::text) > 2000 then raise exception 'Audit details are too large.'; end if;
  select role into v_role from public.profiles where id = auth.uid();
  insert into public.audit_logs(actor_id, actor_role, action, entity_type, entity_id, details)
  values (auth.uid(), v_role, p_action, left(p_entity_type, 80), left(p_entity_id, 100),
    coalesce(p_details, '{}'::jsonb) - 'password' - 'token' - 'embedding' - 'face_image' - 'service_role_key');
  return jsonb_build_object('ok', true);
end;
$$;

create or replace function public.record_login_event()
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_role text;
begin
  if auth.uid() is null then raise exception 'Authentication required.'; end if;
  select role into v_role from public.profiles where id = auth.uid() and is_active = true;
  if v_role is null then raise exception 'Active profile required.'; end if;
  insert into public.login_history(profile_id, role) values (auth.uid(), v_role);
  insert into public.audit_logs(actor_id, actor_role, action, details) values (auth.uid(), v_role, 'login_succeeded', '{}'::jsonb);
  return jsonb_build_object('ok', true);
end;
$$;

create or replace function public.attendx_health_check()
returns jsonb language plpgsql stable security definer set search_path = public as $$
declare v_role text;
begin
  if auth.uid() is null then raise exception 'Authentication required.'; end if;
  select role into v_role from public.profiles where id = auth.uid() and is_active = true;
  if v_role is null then raise exception 'Active profile required.'; end if;
  return jsonb_build_object('ok', true, 'database', 'connected', 'role', v_role,
    'timezone', 'Asia/Manila', 'schema_version', '1.0.0', 'checked_at', now());
end;
$$;

create or replace function public.issue_student_qr_token(p_schedule_id bigint, p_token_text text, p_ttl_days integer default 180)
returns jsonb language plpgsql security definer set search_path = public, extensions as $$
declare v_id uuid; v_expires timestamptz; v_hash text;
begin
  if not public.is_student(auth.uid()) then raise exception 'Student authentication required.'; end if;
  if length(coalesce(p_token_text, '')) < 24 then raise exception 'Invalid QR token request.'; end if;
  if not public.student_enrolled(auth.uid(), p_schedule_id) then raise exception 'You are not enrolled in this schedule.'; end if;
  update public.qr_tokens set revoked_at = now() where student_id = auth.uid() and schedule_id = p_schedule_id and revoked_at is null;
  v_hash := encode(extensions.digest(convert_to(p_token_text, 'UTF8'), 'sha256'), 'hex');
  v_expires := now() + make_interval(days => greatest(1, least(coalesce(p_ttl_days, 180), 365)));
  insert into public.qr_tokens(student_id, schedule_id, token_hash, expires_at)
  values (auth.uid(), p_schedule_id, v_hash, v_expires) returning id into v_id;
  return jsonb_build_object('ok', true, 'id', v_id, 'expires_at', v_expires);
end;
$$;

create or replace function public.start_attendance_session(p_schedule_id bigint, p_session_token text)
returns jsonb language plpgsql security definer set search_path = public, extensions as $$
declare v_schedule public.schedules%rowtype; v_date date; v_now_local timestamp; v_start timestamptz; v_end timestamptz; v_id bigint; v_status text;
begin
  if not public.is_teacher(auth.uid()) or not public.teacher_owns_schedule(p_schedule_id) then raise exception 'Only the assigned teacher can start this schedule.'; end if;
  if length(coalesce(p_session_token, '')) < 24 then raise exception 'Invalid session token.'; end if;
  select * into v_schedule from public.schedules where id = p_schedule_id and is_active = true;
  if not found then raise exception 'Active schedule not found.'; end if;
  v_now_local := now() at time zone 'Asia/Manila';
  v_date := v_now_local::date;
  if v_now_local::time >= v_schedule.end_time then raise exception 'This scheduled class has already ended for today.'; end if;
  v_start := (v_date + v_schedule.start_time) at time zone 'Asia/Manila';
  v_end := (v_date + v_schedule.end_time) at time zone 'Asia/Manila';
  insert into public.attendance_sessions(schedule_id, teacher_id, session_token_hash, session_date, started_at, ends_at, status)
  values (p_schedule_id, auth.uid(), encode(extensions.digest(convert_to(p_session_token, 'UTF8'), 'sha256'), 'hex'), v_date, now(), v_end, 'ACTIVE')
  on conflict (schedule_id, session_date) do update set
    teacher_id = excluded.teacher_id,
    session_token_hash = excluded.session_token_hash,
    started_at = now(), ends_at = excluded.ends_at, status = 'ACTIVE', updated_at = now()
  where public.attendance_sessions.status <> 'FINALIZED'
  returning id, status into v_id, v_status;
  if v_id is null then raise exception 'This class attendance session has already been finalized for today.'; end if;
  return jsonb_build_object('ok', true, 'session_id', v_id, 'session_date', v_date, 'starts_at', v_start, 'ends_at', v_end, 'status', v_status);
end;
$$;

create or replace function public._record_attendance(p_student_id uuid, p_schedule_id bigint, p_method text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_schedule public.schedules%rowtype; v_profile public.profiles%rowtype; v_session public.attendance_sessions%rowtype;
  v_now timestamptz := now(); v_local timestamp; v_date date; v_time time; v_elapsed numeric; v_status text; v_record_id bigint; v_absences integer;
begin
  if p_method not in ('QR', 'FACE', 'FINGERPRINT') then raise exception 'Unsupported attendance method.'; end if;
  select * into v_profile from public.profiles where id = p_student_id and role = 'STUDENT' and is_active = true;
  if not found then return jsonb_build_object('ok', false, 'message', 'Student account not found or inactive.'); end if;
  if v_profile.student_status = 'DROPPED' then return jsonb_build_object('ok', false, 'message', 'This student account is marked DROPPED and cannot record further attendance.'); end if;
  select * into v_schedule from public.schedules where id = p_schedule_id and is_active = true;
  if not found then return jsonb_build_object('ok', false, 'message', 'Schedule does not exist or is inactive.'); end if;
  if not public.student_enrolled(p_student_id, p_schedule_id) then return jsonb_build_object('ok', false, 'message', 'Student is not enrolled in this class.'); end if;
  v_local := v_now at time zone 'Asia/Manila';
  v_date := v_local::date;
  v_time := v_local::time;
  select * into v_session from public.attendance_sessions s
    where s.schedule_id = p_schedule_id and s.session_date = v_date and s.status = 'ACTIVE' for update;
  if not found then return jsonb_build_object('ok', false, 'message', 'The teacher has not opened an active attendance session for this class.'); end if;
  if v_now > v_session.ends_at or v_time >= v_schedule.end_time then
    return jsonb_build_object('ok', false, 'message', 'This class session has ended.');
  end if;
  v_elapsed := extract(epoch from (v_time - v_schedule.start_time));
  if v_elapsed <= 0 then v_status := 'PRESENT';
  elsif v_elapsed < 900 then v_status := 'LATE';
  else v_status := 'LATE_ABSENT'; end if;

  insert into public.attendance_records(student_id, schedule_id, session_id, attendance_date, attendance_time, observed_at, status, method)
  values (p_student_id, p_schedule_id, v_session.id, v_date, v_time, v_now, v_status, p_method)
  on conflict (student_id, schedule_id, attendance_date) do nothing
  returning id into v_record_id;
  if v_record_id is null then
    return jsonb_build_object('ok', false, 'duplicate', true, 'message', 'Attendance already recorded for this class today.');
  end if;
  insert into public.audit_logs(actor_id, actor_role, action, entity_type, entity_id, details)
  values (auth.uid(), (select role from public.profiles where id = auth.uid()), 'attendance_recorded', 'attendance_records', v_record_id::text,
    jsonb_build_object('method', p_method, 'status', v_status, 'schedule_id', p_schedule_id));
  if v_status in ('LATE_ABSENT') then
    select count(*) into v_absences from public.attendance_records where student_id = p_student_id and status in ('ABSENT', 'LATE_ABSENT');
    if v_absences >= 3 then update public.profiles set student_status = 'DROPPED' where id = p_student_id; end if;
  end if;
  return jsonb_build_object('ok', true, 'record_id', v_record_id, 'status', v_status, 'message', 'Attendance recorded: ' || replace(v_status, '_', ' '));
end;
$$;

create or replace function public.record_attendance_by_student_qr(p_token_text text, p_schedule_id bigint)
returns jsonb language plpgsql security definer set search_path = public, extensions as $$
declare v_student uuid; v_token public.qr_tokens%rowtype;
begin
  if not public.is_teacher(auth.uid()) or not public.teacher_owns_schedule(p_schedule_id) then raise exception 'Teacher permission for this schedule is required.'; end if;
  if length(coalesce(p_token_text, '')) < 24 then return jsonb_build_object('ok', false, 'message', 'QR token is invalid.'); end if;
  select * into v_token from public.qr_tokens q where q.token_hash = encode(extensions.digest(convert_to(p_token_text, 'UTF8'), 'sha256'), 'hex')
    and q.schedule_id = p_schedule_id and q.revoked_at is null and q.expires_at > now();
  if not found then return jsonb_build_object('ok', false, 'message', 'QR pass is invalid, expired, revoked, or belongs to a different class.'); end if;
  v_student := v_token.student_id;
  return public._record_attendance(v_student, p_schedule_id, 'QR');
end;
$$;

create or replace function public.record_session_qr_attendance(p_token_text text)
returns jsonb language plpgsql security definer set search_path = public, extensions as $$
declare v_session public.attendance_sessions%rowtype;
begin
  if not public.is_student(auth.uid()) then raise exception 'Student authentication is required.'; end if;
  if length(coalesce(p_token_text, '')) < 24 then return jsonb_build_object('ok', false, 'message', 'Session QR token is invalid.'); end if;
  select * into v_session from public.attendance_sessions s
    where s.session_token_hash = encode(extensions.digest(convert_to(p_token_text, 'UTF8'), 'sha256'), 'hex')
      and s.status = 'ACTIVE' and s.session_date = (now() at time zone 'Asia/Manila')::date and s.ends_at >= now();
  if not found then return jsonb_build_object('ok', false, 'message', 'This class QR session is expired or no longer active.'); end if;
  return public._record_attendance(auth.uid(), v_session.schedule_id, 'QR');
end;
$$;

create or replace function public.record_biometric_attendance(p_student_id uuid, p_schedule_id bigint, p_method text)
returns jsonb language plpgsql security definer set search_path = public as $$
begin
  if not public.is_teacher(auth.uid()) or not public.teacher_owns_schedule(p_schedule_id) then raise exception 'Teacher permission for this schedule is required.'; end if;
  if p_method not in ('FACE', 'FINGERPRINT') then raise exception 'Unsupported biometric method.'; end if;
  return public._record_attendance(p_student_id, p_schedule_id, p_method);
end;
$$;

create or replace function public.close_attendance_session(p_session_id bigint)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_session public.attendance_sessions%rowtype;
begin
  select * into v_session from public.attendance_sessions where id = p_session_id for update;
  if not found or v_session.teacher_id <> auth.uid() or not public.is_teacher(auth.uid()) then raise exception 'Attendance session not found or not owned by this teacher.'; end if;
  if v_session.status = 'FINALIZED' then return jsonb_build_object('ok', true, 'message', 'Session was already finalized.'); end if;
  update public.attendance_sessions set status = 'CLOSED' where id = p_session_id;
  return jsonb_build_object('ok', true, 'message', 'Attendance session closed. Missing students are marked absent only after the scheduled end time.');
end;
$$;

create or replace function public.finalize_attendance_session(p_schedule_id bigint, p_session_date date default null)
returns jsonb language plpgsql security definer set search_path = public, extensions as $$
declare v_schedule public.schedules%rowtype; v_date date; v_now_local timestamp; v_end timestamptz; v_session_id bigint; v_token_hash text; v_inserted integer := 0; v_student uuid;
begin
  if not public.is_teacher(auth.uid()) or not public.teacher_owns_schedule(p_schedule_id) then raise exception 'Teacher permission for this schedule is required.'; end if;
  select * into v_schedule from public.schedules where id = p_schedule_id;
  if not found then raise exception 'Schedule not found.'; end if;
  v_now_local := now() at time zone 'Asia/Manila';
  v_date := coalesce(p_session_date, v_now_local::date);
  if v_date > v_now_local::date then raise exception 'A future attendance date cannot be finalized.'; end if;
  if trim(to_char(v_date, 'FMDay')) <> v_schedule.day_of_week then
    raise exception 'The selected date does not match this schedule weekday (%).', v_schedule.day_of_week;
  end if;
  v_end := (v_date + v_schedule.end_time) at time zone 'Asia/Manila';
  if now() < v_end then raise exception 'Attendance cannot be finalized before the scheduled class end time (%).', v_end; end if;
  v_token_hash := encode(extensions.digest(convert_to(gen_random_uuid()::text, 'UTF8'), 'sha256'), 'hex');
  insert into public.attendance_sessions(schedule_id, teacher_id, session_token_hash, session_date, started_at, ends_at, status)
  values (p_schedule_id, auth.uid(), v_token_hash, v_date, (v_date + v_schedule.start_time) at time zone 'Asia/Manila', v_end, 'FINALIZED')
  on conflict (schedule_id, session_date) do update set status = 'FINALIZED', updated_at = now()
  returning id into v_session_id;
  insert into public.attendance_records(student_id, schedule_id, session_id, attendance_date, attendance_time, observed_at, status, method)
    select e.student_id, p_schedule_id, v_session_id, v_date, v_schedule.end_time, v_end, 'ABSENT', 'SYSTEM'
    from public.class_enrollments e
    where e.schedule_id = p_schedule_id
      and not exists (select 1 from public.attendance_records a where a.student_id = e.student_id and a.schedule_id = p_schedule_id and a.attendance_date = v_date)
    on conflict (student_id, schedule_id, attendance_date) do nothing;
  get diagnostics v_inserted = row_count;
  for v_student in select e.student_id from public.class_enrollments e where e.schedule_id = p_schedule_id loop
    if (select count(*) from public.attendance_records a where a.student_id = v_student and a.status in ('ABSENT', 'LATE_ABSENT')) >= 3 then
      update public.profiles set student_status = 'DROPPED' where id = v_student and role = 'STUDENT';
    end if;
  end loop;
  insert into public.audit_logs(actor_id, actor_role, action, entity_type, entity_id, details)
  values (auth.uid(), 'TEACHER', 'attendance_finalized', 'schedules', p_schedule_id::text,
    jsonb_build_object('date', v_date, 'absent_records_added', v_inserted));
  return jsonb_build_object('ok', true, 'session_id', v_session_id, 'date', v_date, 'absent_records_added', v_inserted,
    'message', format('Session finalized. %s absent record(s) added.', v_inserted));
end;
$$;

create or replace function public.save_fingerprint_template(p_sensor_template_id integer, p_finger_name text)
returns jsonb language plpgsql security definer set search_path = public as $$
begin
  if not public.is_student(auth.uid()) then raise exception 'Student authentication required.'; end if;
  if p_sensor_template_id is null or p_sensor_template_id < 0 then raise exception 'Invalid sensor template ID.'; end if;
  if length(btrim(coalesce(p_finger_name, ''))) < 1 or length(p_finger_name) > 40 then raise exception 'Enter a valid finger label.'; end if;
  insert into public.fingerprint_credentials(student_id, sensor_template_id, finger_name)
  values (auth.uid(), p_sensor_template_id, btrim(p_finger_name))
  on conflict (student_id) do update set sensor_template_id = excluded.sensor_template_id, finger_name = excluded.finger_name, updated_at = now();
  return jsonb_build_object('ok', true, 'sensor_template_id', p_sensor_template_id);
end;
$$;

-- Do not grant EXECUTE on internal attendance helper directly to app clients.
revoke all on function public._record_attendance(uuid, bigint, text) from public, anon, authenticated;
revoke all on function public.handle_new_auth_user() from public, anon, authenticated;
revoke all on function public.protect_profile_identity() from public, anon, authenticated;
revoke all on function public.is_teacher(uuid) from public, anon;
revoke all on function public.is_student(uuid) from public, anon;
revoke all on function public.teacher_owns_schedule(bigint, uuid) from public, anon;
revoke all on function public.student_enrolled(uuid, bigint) from public, anon;
grant execute on function public.is_teacher(uuid) to authenticated;
grant execute on function public.is_student(uuid) to authenticated;
grant execute on function public.teacher_owns_schedule(bigint, uuid) to authenticated;
grant execute on function public.student_enrolled(uuid, bigint) to authenticated;
grant execute on function public.write_audit_event(text, text, text, jsonb) to authenticated;
grant execute on function public.record_login_event() to authenticated;
grant execute on function public.attendx_health_check() to authenticated;
grant execute on function public.issue_student_qr_token(bigint, text, integer) to authenticated;
grant execute on function public.start_attendance_session(bigint, text) to authenticated;
grant execute on function public.record_attendance_by_student_qr(text, bigint) to authenticated;
grant execute on function public.record_session_qr_attendance(text) to authenticated;
grant execute on function public.record_biometric_attendance(uuid, bigint, text) to authenticated;
grant execute on function public.close_attendance_session(bigint) to authenticated;
grant execute on function public.finalize_attendance_session(bigint, date) to authenticated;
grant execute on function public.save_fingerprint_template(integer, text) to authenticated;
