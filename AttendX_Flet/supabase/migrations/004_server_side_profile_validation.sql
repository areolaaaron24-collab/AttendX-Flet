-- Apply validation and normalization at the database boundary too. This protects against
-- clients that call Supabase Auth directly instead of using the AttendX registration UI.

create or replace function public.validate_normalize_profile_fields()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  v_fields text[];
begin
  new.account_id := lower(btrim(coalesce(new.account_id, '')));
  if new.account_id !~ '^[a-z0-9][a-z0-9._-]{0,63}$' then
    raise exception 'Account ID must be 1-64 characters and contain only letters, numbers, dot, underscore, or hyphen.';
  end if;

  new.first_name := regexp_replace(btrim(coalesce(new.first_name, '')), '\s+', ' ', 'g');
  new.last_name := regexp_replace(btrim(coalesce(new.last_name, '')), '\s+', ' ', 'g');
  new.middle_name := regexp_replace(btrim(coalesce(new.middle_name, '')), '\s+', ' ', 'g');
  new.suffix := regexp_replace(btrim(coalesce(new.suffix, '')), '\s+', ' ', 'g');
  if new.first_name = '' or new.last_name = '' then
    raise exception 'First Name and Last Name are required.';
  end if;
  if char_length(new.first_name) > 80 or char_length(new.last_name) > 80
     or char_length(new.middle_name) > 80 or char_length(new.suffix) > 80 then
    raise exception 'Name fields must be 80 characters or fewer.';
  end if;
  if new.first_name ~ '[0-9]' or new.last_name ~ '[0-9]'
     or new.middle_name ~ '[0-9]' or new.suffix ~ '[0-9]' then
    raise exception 'Name fields must not contain numbers.';
  end if;

  new.sex := initcap(btrim(coalesce(new.sex, '')));
  if new.sex not in ('Male', 'Female') then
    raise exception 'Sex must be Male or Female.';
  end if;

  new.recovery_email := nullif(lower(btrim(coalesce(new.recovery_email, ''))), '');
  if new.recovery_email is not null
     and new.recovery_email !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' then
    raise exception 'Recovery email is invalid.';
  end if;

  new.course := nullif(regexp_replace(btrim(coalesce(new.course, '')), '\s+', ' ', 'g'), '');
  new.year_level := nullif(regexp_replace(btrim(coalesce(new.year_level, '')), '\s+', ' ', 'g'), '');
  new.section := nullif(regexp_replace(btrim(coalesce(new.section, '')), '\s+', ' ', 'g'), '');
  new.department := nullif(regexp_replace(btrim(coalesce(new.department, '')), '\s+', ' ', 'g'), '');
  new.office := nullif(regexp_replace(btrim(coalesce(new.office, '')), '\s+', ' ', 'g'), '');

  if new.role = 'STUDENT' and (
    new.course is null or new.year_level is null or new.section is null
    or char_length(new.course) > 120 or char_length(new.year_level) > 20 or char_length(new.section) > 40
  ) then
    raise exception 'Student Course, Year, and Section are required and must fit the supported lengths.';
  end if;
  if new.department is not null and char_length(new.department) > 120 then
    raise exception 'Department must be 120 characters or fewer.';
  end if;
  if new.office is not null and char_length(new.office) > 120 then
    raise exception 'Office must be 120 characters or fewer.';
  end if;

  return new;
end;
$$;

revoke all on function public.validate_normalize_profile_fields() from public, anon, authenticated;
drop trigger if exists profiles_00_validate_normalize on public.profiles;
create trigger profiles_00_validate_normalize
before insert or update on public.profiles
for each row execute function public.validate_normalize_profile_fields();
