-- Hardening pass: prevent direct client writes to face descriptors, reject cross-account
-- duplicate descriptors, preserve manual verification with an audit reason, and restrict
-- session starts to the schedule's published day.

-- Face writes must go through a server-side RPC so cross-account duplicate checks cannot
-- be bypassed by calling the REST table endpoint directly.
drop policy if exists face_templates_insert_own on public.face_templates;
drop policy if exists face_templates_update_own on public.face_templates;
revoke insert, update on public.face_templates from authenticated, anon, public;

create or replace function public.register_face_template(p_embedding jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_student uuid := auth.uid();
  v_existing record;
  v_i integer;
  v_j integer;
  v_distance double precision;
  v_sum double precision;
  v_a double precision;
  v_b double precision;
  v_old_embedding jsonb;
  v_algorithm text := 'face_recognition-128d';
begin
  if not public.is_student(v_student) then
    raise exception 'Only an active student can register their own face descriptor.';
  end if;
  if jsonb_typeof(p_embedding) <> 'array' or jsonb_array_length(p_embedding) <> 128 then
    raise exception 'Face descriptor must contain exactly 128 numeric values.';
  end if;
  for v_i in 0..127 loop
    if jsonb_typeof(p_embedding -> v_i) <> 'number' then
      raise exception 'Face descriptor contains a non-numeric value.';
    end if;
    v_a := (p_embedding ->> v_i)::double precision;
    if v_a = 'NaN'::double precision or v_a = 'Infinity'::double precision or v_a = '-Infinity'::double precision then
      raise exception 'Face descriptor contains a non-finite value.';
    end if;
  end loop;

  -- Reject a descriptor too close to another account. This is a conservative duplicate
  -- guard, not a guarantee against all twins/lookalikes; the live matcher also refuses
  -- ambiguous nearest matches and server attendance is still protected by account/session.
  for v_existing in
    select student_id, embedding from public.face_templates where student_id <> v_student limit 10000
  loop
    v_old_embedding := v_existing.embedding;
    if jsonb_typeof(v_old_embedding) = 'array' and jsonb_array_length(v_old_embedding) = 128 then
      v_sum := 0;
      for v_j in 0..127 loop
        v_a := (p_embedding ->> v_j)::double precision;
        v_b := (v_old_embedding ->> v_j)::double precision;
        v_sum := v_sum + ((v_a - v_b) * (v_a - v_b));
      end loop;
      v_distance := sqrt(v_sum);
      if v_distance < 0.20 then
        raise exception 'This face descriptor is too similar to a descriptor registered to another account. Ask the teacher to review identity verification.';
      end if;
    end if;
  end loop;

  insert into public.face_templates(student_id, embedding, algorithm, consented_at)
  values (v_student, p_embedding, v_algorithm, now())
  on conflict (student_id) do update set
    embedding = excluded.embedding,
    algorithm = excluded.algorithm,
    consented_at = now(),
    updated_at = now();
  insert into public.audit_logs(actor_id, actor_role, action, entity_type, entity_id, details)
  values (v_student, 'STUDENT', 'face_template_registered', 'face_templates', v_student::text,
    jsonb_build_object('algorithm', v_algorithm, 'dimensions', 128));
  return jsonb_build_object('ok', true, 'message', 'Face descriptor saved.');
end;
$$;

-- Manual attendance is a teacher-authorized exception for documented recovery cases only.
-- The same session/enrolment/time/status/duplicate checks are still applied by the shared helper.
create or replace function public.record_manual_attendance(
  p_student_id uuid,
  p_schedule_id bigint,
  p_reason text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_result jsonb;
  v_reason text := btrim(coalesce(p_reason, ''));
begin
  if not public.is_teacher(auth.uid()) or not public.teacher_owns_schedule(p_schedule_id) then
    raise exception 'Only the assigned teacher can record a manual attendance correction.';
  end if;
  if length(v_reason) < 10 or length(v_reason) > 500 then
    raise exception 'Provide an audit reason between 10 and 500 characters.';
  end if;
  v_result := public._record_attendance(p_student_id, p_schedule_id, 'MANUAL');
  if coalesce((v_result ->> 'ok')::boolean, false) then
    insert into public.audit_logs(actor_id, actor_role, action, entity_type, entity_id, details)
    values (auth.uid(), 'TEACHER', 'manual_attendance_recorded', 'attendance_records', v_result ->> 'record_id',
      jsonb_build_object('schedule_id', p_schedule_id, 'student_id', p_student_id, 'reason', v_reason));
  end if;
  return v_result;
end;
$$;

-- Replace the schedule session start function to enforce its configured weekday. We use the
-- Asia/Manila local date and don't assume the server timezone matches the school timezone.
create or replace function public.start_attendance_session(p_schedule_id bigint, p_session_token text)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_schedule public.schedules%rowtype;
  v_date date;
  v_local timestamp;
  v_local_day text;
  v_start timestamptz;
  v_end timestamptz;
  v_id bigint;
  v_status text;
begin
  if not public.is_teacher(auth.uid()) or not public.teacher_owns_schedule(p_schedule_id) then
    raise exception 'Only the assigned teacher can start this schedule.';
  end if;
  if length(coalesce(p_session_token, '')) < 24 then raise exception 'Invalid session token.'; end if;
  select * into v_schedule from public.schedules where id = p_schedule_id and is_active = true;
  if not found then raise exception 'Active schedule not found.'; end if;
  v_local := now() at time zone 'Asia/Manila';
  v_date := v_local::date;
  v_local_day := trim(to_char(v_date, 'Day'));
  if v_local_day <> v_schedule.day_of_week then
    raise exception 'This schedule is set for %, not today (%).', v_schedule.day_of_week, v_local_day;
  end if;
  if v_local::time >= v_schedule.end_time then raise exception 'This scheduled class has already ended for today.'; end if;
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
  return jsonb_build_object('ok', true, 'session_id', v_id, 'session_date', v_date,
    'starts_at', v_start, 'ends_at', v_end, 'status', v_status);
end;
$$;

-- Manual records use the exact same scheduled-start boundary classification as device scans.
create or replace function public._record_attendance(p_student_id uuid, p_schedule_id bigint, p_method text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_schedule public.schedules%rowtype;
  v_profile public.profiles%rowtype;
  v_session public.attendance_sessions%rowtype;
  v_now timestamptz := now();
  v_local timestamp;
  v_date date;
  v_time time;
  v_elapsed numeric;
  v_status text;
  v_record_id bigint;
  v_absences integer;
begin
  if p_method not in ('QR', 'FACE', 'FINGERPRINT', 'MANUAL') then raise exception 'Unsupported attendance method.'; end if;
  if p_method = 'MANUAL' and (not public.is_teacher(auth.uid()) or not public.teacher_owns_schedule(p_schedule_id)) then
    raise exception 'Teacher permission is required for manual attendance.';
  end if;
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
  if v_now >= v_session.ends_at or v_time >= v_schedule.end_time then
    return jsonb_build_object('ok', false, 'message', 'This class session has ended.');
  end if;
  v_elapsed := extract(epoch from (v_time - v_schedule.start_time));
  if v_elapsed < 0 then
    return jsonb_build_object('ok', false, 'message', 'Attendance cannot be recorded before the scheduled start time.');
  elsif v_elapsed = 0 then v_status := 'PRESENT';
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
  if v_status = 'LATE_ABSENT' then
    select count(*) into v_absences from public.attendance_records where student_id = p_student_id and status in ('ABSENT', 'LATE_ABSENT');
    if v_absences >= 3 then update public.profiles set student_status = 'DROPPED' where id = p_student_id; end if;
  end if;
  return jsonb_build_object('ok', true, 'record_id', v_record_id, 'status', v_status,
    'message', 'Attendance recorded: ' || replace(v_status, '_', ' '));
end;
$$;

revoke all on function public.register_face_template(jsonb) from public, anon;
revoke all on function public.record_manual_attendance(uuid, bigint, text) from public, anon;
revoke all on function public.start_attendance_session(bigint, text) from public, anon;
revoke all on function public._record_attendance(uuid, bigint, text) from public, anon, authenticated;
grant execute on function public.register_face_template(jsonb) to authenticated;
grant execute on function public.record_manual_attendance(uuid, bigint, text) to authenticated;
grant execute on function public.start_attendance_session(bigint, text) to authenticated;

create or replace function public.teacher_attendance_dashboard_stats()
returns jsonb
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  v_today date := (now() at time zone 'Asia/Manila')::date;
  v_week date := date_trunc('week', (now() at time zone 'Asia/Manila'))::date;
  v_month date := date_trunc('month', (now() at time zone 'Asia/Manila'))::date;
  v_result jsonb;
begin
  if not public.is_teacher(auth.uid()) then raise exception 'Teacher authentication is required.'; end if;
  select jsonb_build_object(
    'today', count(*) filter (where a.attendance_date = v_today),
    'week', count(*) filter (where a.attendance_date >= v_week and a.attendance_date <= v_today),
    'month', count(*) filter (where a.attendance_date >= v_month and a.attendance_date <= v_today),
    'present', count(*) filter (where a.attendance_date = v_today and a.status = 'PRESENT'),
    'late', count(*) filter (where a.attendance_date = v_today and a.status = 'LATE'),
    'late_absent', count(*) filter (where a.attendance_date = v_today and a.status = 'LATE_ABSENT'),
    'absent', count(*) filter (where a.attendance_date = v_today and a.status = 'ABSENT')
  ) into v_result
  from public.attendance_records a
  join public.schedules s on s.id = a.schedule_id
  where s.teacher_id = auth.uid();
  return coalesce(v_result, '{}'::jsonb);
end;
$$;
revoke all on function public.teacher_attendance_dashboard_stats() from public, anon;
grant execute on function public.teacher_attendance_dashboard_stats() to authenticated;

-- Database-owned finalization routine. It runs with owner privileges and is deliberately
-- not executable by regular authenticated/anonymous app clients. Schedule it with pg_cron
-- only after confirming your Supabase project supports/enables that extension.
create or replace function public.auto_finalize_due_sessions()
returns integer
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_local timestamp := now() at time zone 'Asia/Manila';
  v_date date := (now() at time zone 'Asia/Manila')::date;
  v_day text := trim(to_char((now() at time zone 'Asia/Manila')::date, 'Day'));
  v_schedule record;
  v_session_id bigint;
  v_inserted integer;
  v_total integer := 0;
  v_token_hash text;
begin
  for v_schedule in
    select s.* from public.schedules s
    where s.is_active = true and s.day_of_week = v_day and s.end_time <= v_local::time
  loop
    v_token_hash := encode(extensions.digest(convert_to(gen_random_uuid()::text, 'UTF8'), 'sha256'), 'hex');
    insert into public.attendance_sessions(schedule_id, teacher_id, session_token_hash, session_date, started_at, ends_at, status)
    values (v_schedule.id, v_schedule.teacher_id, v_token_hash, v_date,
      (v_date + v_schedule.start_time) at time zone 'Asia/Manila',
      (v_date + v_schedule.end_time) at time zone 'Asia/Manila', 'FINALIZED')
    on conflict (schedule_id, session_date) do update set status = 'FINALIZED', updated_at = now()
    where public.attendance_sessions.status <> 'FINALIZED'
    returning id into v_session_id;
    if v_session_id is null then continue; end if;

    insert into public.attendance_records(student_id, schedule_id, session_id, attendance_date, attendance_time, observed_at, status, method)
    select e.student_id, v_schedule.id, v_session_id, v_date, v_schedule.end_time,
      (v_date + v_schedule.end_time) at time zone 'Asia/Manila', 'ABSENT', 'SYSTEM'
    from public.class_enrollments e
    where e.schedule_id = v_schedule.id
      and not exists (select 1 from public.attendance_records a
                      where a.student_id = e.student_id and a.schedule_id = v_schedule.id and a.attendance_date = v_date)
    on conflict (student_id, schedule_id, attendance_date) do nothing;
    get diagnostics v_inserted = row_count;
    v_total := v_total + v_inserted;

    update public.profiles p set student_status = 'DROPPED'
    where p.role = 'STUDENT' and p.student_status <> 'DROPPED'
      and exists (select 1 from public.class_enrollments e where e.schedule_id = v_schedule.id and e.student_id = p.id)
      and (select count(*) from public.attendance_records a
           where a.student_id = p.id and a.status in ('ABSENT', 'LATE_ABSENT')) >= 3;

    insert into public.audit_logs(actor_id, actor_role, action, entity_type, entity_id, details)
    values (null, null, 'attendance_auto_finalized', 'schedules', v_schedule.id::text,
      jsonb_build_object('date', v_date, 'absent_records_added', v_inserted));
  end loop;
  return v_total;
end;
$$;
revoke all on function public.auto_finalize_due_sessions() from public, anon, authenticated;
