from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"


def all_sql() -> str:
    return "\n".join(path.read_text(encoding="utf-8").lower() for path in sorted(MIGRATIONS.glob("*.sql")))


def test_database_schema_has_two_roles_and_global_case_insensitive_account_uniqueness():
    sql = all_sql()
    assert "role in ('teacher', 'student')" in sql
    assert "profiles_account_id_unique_ci on public.profiles (lower(btrim(account_id)))" in sql


def test_attendance_is_unique_per_student_schedule_and_day():
    sql = all_sql()
    assert "attendance_once_per_schedule_day unique(student_id, schedule_id, attendance_date)" in sql
    assert "on conflict (student_id, schedule_id, attendance_date) do nothing" in sql


def test_attendance_writes_use_authorized_rpcs_not_direct_client_grants():
    sql = all_sql()
    assert "revoke all on function public._record_attendance(uuid, bigint, text) from public, anon, authenticated" in sql
    assert "grant execute on function public.record_manual_attendance(uuid, bigint, text) to authenticated" in sql
    assert "grant execute on function public.register_face_template(jsonb) to authenticated" in sql
    assert "grant insert, update, delete on public.attendance_records to authenticated" not in sql


def test_face_template_registration_has_embedding_validation_and_cross_user_check():
    sql = all_sql()
    assert "create or replace function public.register_face_template(p_embedding jsonb)" in sql
    assert "jsonb_array_length(p_embedding) <> 128" in sql
    assert "too similar to a descriptor registered to another account" in sql
    assert "drop policy if exists face_templates_insert_own" in sql


def test_client_example_has_no_service_role_key():
    env = (ROOT / ".env.example").read_text(encoding="utf-8").lower()
    assert "service_role" not in env
    assert "sb_secret_" not in env
    assert "supabase_publishable_key=" in env


def test_automatic_finalization_is_not_executable_by_clients():
    sql = all_sql()
    assert "revoke all on function public.auto_finalize_due_sessions() from public, anon, authenticated" in sql


def test_profile_validation_is_enforced_by_database_trigger():
    sql = all_sql()
    assert "create or replace function public.validate_normalize_profile_fields()" in sql
    assert "create trigger profiles_00_validate_normalize" in sql
    assert "new.first_name ~ '[0-9]'" in sql
    assert "new.sex not in ('male', 'female')" in sql
    assert "role in ('teacher', 'student')" in sql


def test_student_teacher_directory_exposes_only_minimal_active_teacher_names():
    sql = all_sql()
    assert "create or replace view public.teacher_directory" in sql
    assert "select id, first_name, middle_name, last_name" in sql
    assert "where role = 'teacher' and is_active = true" in sql
    assert "grant select on public.teacher_directory to authenticated" in sql
    assert "recovery_email" not in sql.split("create or replace view public.teacher_directory", 1)[1]


def test_pre_start_attendance_is_rejected_and_role_helpers_are_not_anon_callable():
    sql = all_sql()
    assert "if v_elapsed < 0 then" in sql
    assert "attendance cannot be recorded before the scheduled start time" in sql
    assert "revoke all on function public.is_teacher(uuid) from public, anon" in sql
    assert "revoke all on function public.student_enrolled(uuid, bigint) from public, anon" in sql


def test_finalization_rejects_future_dates_and_non_schedule_weekdays():
    sql = all_sql()
    assert "a future attendance date cannot be finalized" in sql
    assert "the selected date does not match this schedule weekday" in sql


def test_student_enrollment_policy_restricts_course_year_and_section():
    sql = all_sql()
    assert "drop policy if exists class_enrollments_student_insert on public.class_enrollments" in sql
    assert "lower(btrim(c.course)) = lower(btrim(p.course))" in sql
    assert "lower(btrim(c.year_level)) = lower(btrim(p.year_level))" in sql
    assert "lower(btrim(c.section)) = lower(btrim(p.section))" in sql
