-- A minimal, safe teacher directory lets students see instructor names without
-- granting them SELECT access to private profile/account fields.
create or replace view public.teacher_directory
with (security_barrier = true)
as
select id, first_name, middle_name, last_name
from public.profiles
where role = 'TEACHER' and is_active = true;

grant select on public.teacher_directory to authenticated;
