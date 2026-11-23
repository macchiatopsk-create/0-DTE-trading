-- Supabase SQL (적용됨: 마이그레이션 odte_watchdog_cron). <ANON_KEY> = 프로젝트 legacy anon 키
create extension if not exists pg_cron;
create extension if not exists pg_net;
select cron.schedule('odte-watchdog', '* 13-21 * * 1-5', $$
  select net.http_post(
    url := 'https://nutfgkxaddvidqrcnvyj.supabase.co/functions/v1/odte-watchdog',
    headers := jsonb_build_object('Content-Type','application/json','Authorization','Bearer <ANON_KEY>'),
    body := '{}'::jsonb,
    timeout_milliseconds := 30000
  );
$$);
-- 끄기: select cron.unschedule('odte-watchdog');
