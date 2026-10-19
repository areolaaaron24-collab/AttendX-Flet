-- Students may discover offerings globally, but can only enroll in the class cohort
-- represented by their own profile. This rule is enforced at the database boundary.
drop policy if exists class_enrollments_student_insert on public.class_enrollments;
create policy class_enrollments_student_insert
on public.class_enrollments
for insert to authenticated
with check (
  student_id = auth.uid()
  and public.is_student(auth.uid())
  and exists (
    select 1
    from public.schedules s
    join public.classes c on c.id = s.class_id
    join public.profiles p on p.id = auth.uid()
    where s.id = schedule_id
      and s.is_active = true
      and lower(btrim(c.course)) = lower(btrim(p.course))
      and lower(btrim(c.year_level)) = lower(btrim(p.year_level))
      and lower(btrim(c.section)) = lower(btrim(p.section))
  )
);
