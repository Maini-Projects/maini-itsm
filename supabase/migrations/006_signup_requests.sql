-- 006: self sign-up with Administrator approval.
-- A person who signs up gets a login (Supabase Auth) and a row here, but no profile, so they cannot use the
-- portal until an Administrator approves the request (which creates the profile with a role and team).
-- Safe to run more than once.

create table if not exists signup_requests (
  id          uuid primary key,                       -- the Supabase login created at sign-up
  email       text not null,
  full_name   text not null,
  status      text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  created_at  timestamptz not null default now(),
  decided_at  timestamptz,
  decided_by  uuid references profiles(id)
);
create unique index if not exists signup_requests_open_email on signup_requests(lower(email)) where status = 'pending';
create index if not exists signup_requests_status_idx on signup_requests(status, created_at);

alter table signup_requests enable row level security;
revoke all on signup_requests from anon, authenticated;
grant all on signup_requests to service_role;
