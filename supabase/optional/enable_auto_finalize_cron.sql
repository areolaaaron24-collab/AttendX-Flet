-- OPTIONAL: run only after enabling the pg_cron extension in your Supabase project.
-- This calls the restricted database routine once per minute; it creates ABSENT rows
-- only after a scheduled class end in Asia/Manila and only once per schedule/date.
create extension if not exists pg_cron with schema extensions;
select cron.unschedule(jobid)
from cron.job
where jobname = 'attendx-auto-finalize-due-sessions';
select cron.schedule(
  'attendx-auto-finalize-due-sessions',
  '* * * * *',
  'select public.auto_finalize_due_sessions();'
);
