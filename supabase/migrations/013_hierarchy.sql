-- 013: reporting lines for internal organizations.
--   profiles.reports_to  - who a person reports to (their line manager)
--   projects.is_internal - the hierarchy only applies inside customers marked internal; external clients ignore it
alter table profiles add column if not exists reports_to uuid references profiles(id) on delete set null;
create index if not exists profiles_reports_to_idx on profiles(reports_to);
alter table profiles drop constraint if exists not_own_manager;
alter table profiles add constraint not_own_manager check (reports_to is null or reports_to <> id);
alter table projects add column if not exists is_internal boolean not null default false;
