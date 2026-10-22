-- 007: how long each Administrator wants audit history shown (default 10 days).
-- The audit log itself stays append-only; this only sets the window the Audit page displays.
-- Safe to run more than once.

create table if not exists audit_settings (
  user_id         uuid primary key references profiles(id) on delete cascade,
  retention_days  int not null default 10 check (retention_days in (1, 3, 7, 10, 30, 60, 90, 180, 365)),
  updated_at      timestamptz not null default now()
);

alter table audit_settings enable row level security;
revoke all on audit_settings from anon, authenticated;
grant all on audit_settings to service_role;
