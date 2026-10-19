-- ============================================================================
-- Maini ITSM portal - database schema (migration 001)
-- Postgres on Supabase. Roles: admin, manager, employee. Teams: Development, Support.
-- The FastAPI back end connects with the service-role key and enforces RBAC;
-- row level security is ON for every table with no public policies (deny by default),
-- so nobody can reach data except through the API.
-- ============================================================================

create extension if not exists pgcrypto;

-- ---------- enums -----------------------------------------------------------
create type user_role       as enum ('admin', 'manager', 'employee');
create type account_status  as enum ('pending', 'active', 'disabled');   -- 'pending' is for the future register screen
create type priority_level  as enum ('P1', 'P2', 'P3', 'P4');
create type level3          as enum ('High', 'Medium', 'Low');
create type record_type     as enum ('incident', 'problem', 'change', 'release');
create type approval_status as enum ('pending', 'approved', 'rejected');
create type change_type     as enum ('Standard', 'Normal', 'Emergency');
create type environment     as enum ('Production', 'UAT');

-- ---------- people and structure -------------------------------------------
create table teams (
  id          uuid primary key default gen_random_uuid(),
  name        text not null unique,
  created_at  timestamptz not null default now()
);

create table profiles (                      -- one row per login (Supabase auth.users)
  id          uuid primary key references auth.users(id) on delete cascade,
  email       text not null unique,
  full_name   text not null,
  role        user_role not null default 'employee',
  team_id     uuid references teams(id),
  status      account_status not null default 'active',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  -- admins may sit outside a team; everyone else belongs to exactly one
  constraint team_required check (role = 'admin' or team_id is not null)
);

-- at most one manager per team
create unique index one_manager_per_team on profiles(team_id) where role = 'manager' and status <> 'disabled';

create table services (                      -- "Projects & Services" screen
  id             uuid primary key default gen_random_uuid(),
  name           text not null unique,
  description    text,
  owner_team_id  uuid references teams(id),
  criticality    level3 not null default 'Medium',
  active         boolean not null default true,
  created_at     timestamptz not null default now()
);

create table sla_policies (                  -- tunable without code changes
  priority            priority_level primary key,
  response_minutes    integer not null check (response_minutes > 0),
  resolution_minutes  integer not null check (resolution_minutes > 0),
  updated_at          timestamptz not null default now()
);

create table settings (
  key    text primary key,
  value  text not null
);

-- ---------- numbering -------------------------------------------------------
create sequence incident_seq start 10001;
create sequence problem_seq  start 1;
create sequence change_seq   start 1;
create sequence release_seq  start 1;

-- ---------- incidents -------------------------------------------------------
create table incidents (
  id                 uuid primary key default gen_random_uuid(),
  number             text not null unique default 'INC-' || nextval('incident_seq'),
  short_description  text not null,
  description        text,
  requester_id       uuid not null references profiles(id),
  team_id            uuid references teams(id),          -- the requester's team, set by trigger
  service_id         uuid references services(id),
  impact             level3 not null default 'Medium',
  urgency            level3 not null default 'Medium',
  priority           priority_level not null,            -- computed from impact + urgency
  status             text not null default 'New',
  assignee_id        uuid references profiles(id),
  major_incident     boolean not null default false,
  resolution_notes   text,
  response_due       timestamptz,
  resolution_due     timestamptz,
  responded_at       timestamptz,
  resolved_at        timestamptz,
  closed_at          timestamptz,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  updated_by         uuid references profiles(id)
);
create index on incidents(requester_id);
create index on incidents(team_id, status);
create index on incidents(assignee_id);

create table incident_comments (
  id           uuid primary key default gen_random_uuid(),
  incident_id  uuid not null references incidents(id) on delete cascade,
  author_id    uuid not null references profiles(id),
  body         text not null,
  internal     boolean not null default false,   -- internal notes hidden from employees
  created_at   timestamptz not null default now()
);

-- ---------- problems --------------------------------------------------------
create table problems (
  id                  uuid primary key default gen_random_uuid(),
  number              text not null unique default 'PRB-' || lpad(nextval('problem_seq')::text, 4, '0'),
  title               text not null,
  description         text,                          -- business impact
  raised_by           uuid not null references profiles(id),
  team_id             uuid references teams(id),
  service_id          uuid references services(id),
  priority            priority_level not null default 'P3',
  owner_id            uuid references profiles(id),
  status              text not null default 'Identified',
  root_cause          text,
  workaround          text,
  permanent_solution  text,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  updated_by          uuid references profiles(id)
);

create table problem_incidents (
  problem_id   uuid references problems(id) on delete cascade,
  incident_id  uuid references incidents(id) on delete cascade,
  primary key (problem_id, incident_id)
);

-- ---------- changes (manager raises, admin approves) ------------------------
create table changes (
  id                    uuid primary key default gen_random_uuid(),
  number                text not null unique default 'CHG-' || lpad(nextval('change_seq')::text, 5, '0'),
  title                 text not null,
  type                  change_type not null default 'Normal',
  risk                  level3 not null default 'Medium',
  requester_id          uuid not null references profiles(id),
  team_id               uuid references teams(id),
  service_id            uuid references services(id),
  status                text not null default 'Draft',
  implementation_plan   text,
  test_plan             text,
  backout_plan          text,
  planned_start         timestamptz,
  planned_end           timestamptz,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),
  updated_by            uuid references profiles(id)
);

-- ---------- releases (manager raises, admin approves) -----------------------
create table releases (
  id               uuid primary key default gen_random_uuid(),
  number           text not null unique default 'REL-' || lpad(nextval('release_seq')::text, 3, '0'),
  name             text not null,
  environment      environment not null default 'Production',
  owner_id         uuid not null references profiles(id),
  team_id          uuid references teams(id),
  service_id       uuid references services(id),
  status           text not null default 'Planned',
  scope            text,
  rollback_plan    text,
  deployment_at    timestamptz,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  updated_by       uuid references profiles(id)
);

create table release_changes (
  release_id  uuid references releases(id) on delete cascade,
  change_id   uuid references changes(id) on delete cascade,
  primary key (release_id, change_id)
);

-- ---------- approvals -------------------------------------------------------
create table approvals (
  id             uuid primary key default gen_random_uuid(),
  record_type    record_type not null,
  record_id      uuid not null,
  record_number  text not null,
  approver_role  user_role not null,          -- incident: manager of the team; change/release: admin
  team_id        uuid references teams(id),   -- scopes which manager may decide an incident approval
  status         approval_status not null default 'pending',
  requested_by   uuid not null references profiles(id),
  decided_by     uuid references profiles(id),
  comment        text,
  created_at     timestamptz not null default now(),
  decided_at     timestamptz,
  constraint decided_consistent check ((status = 'pending') = (decided_at is null))
);
create index on approvals(status, approver_role);
create unique index one_open_approval on approvals(record_type, record_id) where status = 'pending';

-- ---------- audit trail -----------------------------------------------------
create table audit_log (
  id           bigint generated always as identity primary key,
  at           timestamptz not null default now(),
  actor_id     uuid,
  action       text not null,                 -- INSERT / UPDATE / DELETE
  table_name   text not null,
  record_id    uuid,
  old_values   jsonb,
  new_values   jsonb
);
create index on audit_log(table_name, record_id);
create index on audit_log(at desc);

-- ---------- workflow rules --------------------------------------------------
create table workflow_transitions (
  record_type  record_type not null,
  from_status  text not null,
  to_status    text not null,
  primary key (record_type, from_status, to_status)
);

insert into workflow_transitions values
  -- incidents
  ('incident','New','Assigned'),
  ('incident','Assigned','In Progress'),
  ('incident','In Progress','Pending'),
  ('incident','Pending','In Progress'),
  ('incident','In Progress','Resolved'),
  ('incident','Resolved','Pending Approval'),   -- P1/P2 only (enforced by trigger)
  ('incident','Resolved','Closed'),             -- P3/P4 only (enforced by trigger)
  ('incident','Resolved','In Progress'),        -- reopen
  ('incident','Pending Approval','Closed'),     -- on approval
  ('incident','Pending Approval','In Progress'),-- on rejection
  -- problems (no approval)
  ('problem','Identified','Investigating'),
  ('problem','Investigating','Root Cause Identified'),
  ('problem','Root Cause Identified','Fix Planned'),
  ('problem','Fix Planned','Resolved'),
  ('problem','Resolved','Closed'),
  ('problem','Resolved','Investigating'),
  -- changes
  ('change','Draft','Submitted'),
  ('change','Submitted','Under Review'),
  ('change','Under Review','Approval Pending'),
  ('change','Approval Pending','Scheduled'),    -- on approval
  ('change','Approval Pending','Draft'),        -- on rejection
  ('change','Scheduled','Implementation'),
  ('change','Implementation','Implemented'),
  ('change','Implemented','Closed'),
  -- releases
  ('release','Planned','Under Review'),
  ('release','Under Review','Approved'),        -- on approval
  ('release','Under Review','Planned'),         -- on rejection
  ('release','Approved','Ready to Deploy'),
  ('release','Ready to Deploy','Deployment'),
  ('release','Deployment','Validated'),
  ('release','Validated','Closed');

-- ---------- triggers: shared helpers ----------------------------------------
create or replace function touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at := now(); return new; end $$;

create or replace function check_transition() returns trigger language plpgsql as $$
declare rtype record_type := tg_argv[0]::record_type;
begin
  if tg_op = 'UPDATE' and new.status is distinct from old.status then
    if not exists (select 1 from workflow_transitions
                   where record_type = rtype and from_status = old.status and to_status = new.status) then
      raise exception 'invalid_transition: % cannot move from "%" to "%"', rtype, old.status, new.status
        using errcode = 'P0001';
    end if;
  end if;
  return new;
end $$;

-- ---------- triggers: incidents ---------------------------------------------
-- priority from impact x urgency
create or replace function priority_from(i level3, u level3) returns priority_level
language sql immutable as $$
  select case
    when i = 'High'   and u = 'High'   then 'P1'::priority_level
    when i = 'High'   and u = 'Medium' then 'P2'
    when i = 'Medium' and u = 'High'   then 'P2'
    when i = 'Low'    and u = 'Low'    then 'P4'
    when i = 'Low'    and u = 'Medium' then 'P4'
    when i = 'Medium' and u = 'Low'    then 'P4'
    else 'P3' end
$$;

create or replace function incident_rules() returns trigger language plpgsql as $$
declare sla sla_policies%rowtype;
begin
  new.priority := priority_from(new.impact, new.urgency);

  if tg_op = 'INSERT' then
    new.team_id := (select team_id from profiles where id = new.requester_id);
    new.status  := 'New';
  end if;

  -- SLA clocks (re-computed from creation time if priority changes)
  if tg_op = 'INSERT' or new.priority is distinct from old.priority then
    select * into sla from sla_policies where priority = new.priority;
    new.response_due   := new.created_at + make_interval(mins => sla.response_minutes);
    new.resolution_due := new.created_at + make_interval(mins => sla.resolution_minutes);
  end if;

  if tg_op = 'UPDATE' and new.status is distinct from old.status then
    -- approval gate: P1/P2 must go through Pending Approval, P3/P4 must not
    if old.status = 'Resolved' and new.status = 'Closed' and new.priority in ('P1','P2') then
      raise exception 'approval_required: P1/P2 incidents need manager approval before closing' using errcode = 'P0001';
    end if;
    if old.status = 'Resolved' and new.status = 'Pending Approval' and new.priority in ('P3','P4') then
      raise exception 'approval_not_needed: P3/P4 incidents close directly' using errcode = 'P0001';
    end if;
    if new.status = 'Assigned' and new.assignee_id is null then
      raise exception 'assignee_required: assign someone before moving to Assigned' using errcode = 'P0001';
    end if;
    if new.status = 'In Progress' and new.responded_at is null then new.responded_at := now(); end if;
    if new.status = 'Resolved' then
      if coalesce(trim(new.resolution_notes), '') = '' then
        raise exception 'resolution_notes_required' using errcode = 'P0001';
      end if;
      new.resolved_at := now();
    end if;
    if new.status = 'Closed' then new.closed_at := now(); end if;
    if old.status = 'Resolved' and new.status = 'In Progress' then new.resolved_at := null; end if;
  end if;
  return new;
end $$;

create trigger incidents_rules  before insert or update on incidents for each row execute function incident_rules();
create trigger incidents_flow   before update on incidents for each row execute function check_transition('incident');
create trigger incidents_touch  before update on incidents for each row execute function touch_updated_at();

-- opening a Pending Approval approval automatically for P1/P2 resolution
create or replace function incident_open_approval() returns trigger language plpgsql as $$
begin
  if new.status = 'Pending Approval' and old.status is distinct from 'Pending Approval' then
    insert into approvals(record_type, record_id, record_number, approver_role, team_id, requested_by)
    values ('incident', new.id, new.number, 'manager', new.team_id, coalesce(new.updated_by, new.requester_id));
  end if;
  return new;
end $$;
create trigger incidents_approval after update on incidents for each row execute function incident_open_approval();

-- ---------- triggers: problems / changes / releases -------------------------
create or replace function set_team_from() returns trigger language plpgsql as $$
begin
  if tg_op = 'INSERT' and new.team_id is null then
    new.team_id := (select team_id from profiles
                    where id = (to_jsonb(new) ->> tg_argv[0])::uuid);
  end if;
  return new;
end $$;

create trigger problems_team  before insert on problems  for each row execute function set_team_from('raised_by');
create trigger changes_team   before insert on changes   for each row execute function set_team_from('requester_id');
create trigger releases_team  before insert on releases  for each row execute function set_team_from('owner_id');

create trigger problems_flow  before update on problems  for each row execute function check_transition('problem');
create trigger changes_flow   before update on changes   for each row execute function check_transition('change');
create trigger releases_flow  before update on releases  for each row execute function check_transition('release');

create trigger problems_touch before update on problems  for each row execute function touch_updated_at();
create trigger changes_touch  before update on changes   for each row execute function touch_updated_at();
create trigger releases_touch before update on releases  for each row execute function touch_updated_at();
create trigger profiles_touch before update on profiles  for each row execute function touch_updated_at();

-- changes and releases: managers may raise them; admins have no restrictions
create or replace function managers_only() returns trigger language plpgsql as $$
declare who uuid := (to_jsonb(new) ->> tg_argv[0])::uuid; r user_role;
begin
  select role into r from profiles where id = who and status = 'active';
  if r is null or r = 'employee' then
    raise exception 'forbidden: only managers and admins can raise %', tg_table_name using errcode = 'P0001';
  end if;
  return new;
end $$;
create trigger changes_who  before insert on changes  for each row execute function managers_only('requester_id');
create trigger releases_who before insert on releases for each row execute function managers_only('owner_id');

-- change / release: submitting for approval opens an admin approval; deciding moves the record on
create or replace function open_admin_approval() returns trigger language plpgsql as $$
declare rtype record_type := tg_argv[0]::record_type; pending_status text := tg_argv[1];
        who uuid := coalesce(new.updated_by, (to_jsonb(new) ->> tg_argv[2])::uuid);
begin
  if new.status = pending_status and old.status is distinct from pending_status then
    insert into approvals(record_type, record_id, record_number, approver_role, team_id, requested_by)
    values (rtype, new.id, new.number, 'admin', new.team_id, who);
  end if;
  return new;
end $$;
create trigger changes_approval  after update on changes  for each row execute function open_admin_approval('change','Approval Pending','requester_id');
create trigger releases_approval after update on releases for each row execute function open_admin_approval('release','Under Review','owner_id');

-- Deciding an approval moves the linked record to its next state, in one transaction.
create or replace function apply_approval_decision() returns trigger language plpgsql as $$
declare dr user_role; dt uuid;
begin
  if old.status = 'pending' and new.status in ('approved','rejected') then
    if new.decided_by is null then
      raise exception 'decider_required' using errcode = 'P0001';
    end if;
    -- only the right person may decide: admin approvals need an admin; incident
    -- approvals need an admin or the manager of the incident's own team
    select role, team_id into dr, dt from profiles where id = new.decided_by and status = 'active';
    if dr is null
       or (old.approver_role = 'admin'   and dr <> 'admin')
       or (old.approver_role = 'manager' and not (dr = 'admin' or (dr = 'manager' and dt = old.team_id))) then
      raise exception 'forbidden: this user cannot decide this approval' using errcode = 'P0001';
    end if;
    -- separation of duties for managers: a manager cannot decide their own request
    -- (admins have no restrictions, so an admin may decide their own)
    if new.decided_by = old.requested_by and dr <> 'admin' then
      raise exception 'self_approval: you cannot approve your own request' using errcode = 'P0001';
    end if;
    new.decided_at := now();

    if new.record_type = 'incident' then
      update incidents set status = case when new.status = 'approved' then 'Closed' else 'In Progress' end,
                           updated_by = new.decided_by where id = new.record_id;
    elsif new.record_type = 'change' then
      update changes   set status = case when new.status = 'approved' then 'Scheduled' else 'Draft' end,
                           updated_by = new.decided_by where id = new.record_id;
    elsif new.record_type = 'release' then
      update releases  set status = case when new.status = 'approved' then 'Approved' else 'Planned' end,
                           updated_by = new.decided_by where id = new.record_id;
    end if;
  end if;
  return new;
end $$;
create trigger approvals_decide before update on approvals for each row execute function apply_approval_decision();

-- ---------- audit trail -----------------------------------------------------
create or replace function audit_row() returns trigger language plpgsql security definer set search_path = public as $$
declare actor uuid; rid uuid;
begin
  if tg_op = 'DELETE' then
    rid := (to_jsonb(old) ->> 'id')::uuid;
    insert into audit_log(actor_id, action, table_name, record_id, old_values)
    values (null, tg_op, tg_table_name, rid, to_jsonb(old));
    return old;
  end if;
  rid   := (to_jsonb(new) ->> 'id')::uuid;
  actor := coalesce((to_jsonb(new) ->> 'updated_by')::uuid, (to_jsonb(new) ->> 'requester_id')::uuid,
                    (to_jsonb(new) ->> 'raised_by')::uuid, (to_jsonb(new) ->> 'decided_by')::uuid);
  insert into audit_log(actor_id, action, table_name, record_id, old_values, new_values)
  values (actor, tg_op, tg_table_name, rid,
          case when tg_op = 'UPDATE' then to_jsonb(old) end, to_jsonb(new));
  return new;
end $$;

create trigger audit_incidents  after insert or update or delete on incidents  for each row execute function audit_row();
create trigger audit_problems   after insert or update or delete on problems   for each row execute function audit_row();
create trigger audit_changes    after insert or update or delete on changes    for each row execute function audit_row();
create trigger audit_releases   after insert or update or delete on releases   for each row execute function audit_row();
create trigger audit_approvals  after insert or update            on approvals  for each row execute function audit_row();
create trigger audit_profiles   after insert or update or delete on profiles   for each row execute function audit_row();
create trigger audit_sla        after update                      on sla_policies for each row execute function audit_row();

-- audit log is append-only
create or replace function audit_immutable() returns trigger language plpgsql as $$
begin raise exception 'audit_log is append-only' using errcode = 'P0001'; end $$;
create trigger audit_no_change before update or delete on audit_log for each row execute function audit_immutable();

-- ---------- security --------------------------------------------------------
-- Deny by default: with RLS on and no policies, only the service-role key (the API) can touch data.
alter table teams                enable row level security;
alter table profiles             enable row level security;
alter table services             enable row level security;
alter table sla_policies         enable row level security;
alter table settings             enable row level security;
alter table incidents            enable row level security;
alter table incident_comments    enable row level security;
alter table problems             enable row level security;
alter table problem_incidents    enable row level security;
alter table changes              enable row level security;
alter table releases             enable row level security;
alter table release_changes      enable row level security;
alter table approvals            enable row level security;
alter table audit_log            enable row level security;
alter table workflow_transitions enable row level security;

revoke all on all tables    in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke all on all functions in schema public from public, anon, authenticated;

-- Supabase grants new objects to anon/authenticated by default; stop that for later migrations too.
alter default privileges in schema public revoke all on tables    from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke all on functions from public, anon, authenticated;

-- The API connects as service_role (bypasses RLS) and needs explicit rights.
grant usage on schema public to service_role;
grant all on all tables    in schema public to service_role;
grant all on all sequences in schema public to service_role;
grant execute on all functions in schema public to service_role;

-- ---------- seed data -------------------------------------------------------
insert into teams(name) values ('Development'), ('Support');

insert into sla_policies(priority, response_minutes, resolution_minutes) values
  ('P1',   15,   240),     -- 15 min / 4 h
  ('P2',   60,  1440),     -- 1 h / 24 h
  ('P3',  240,  4320),     -- 4 h / 3 days
  ('P4', 1440,  7200);     -- 1 day / 5 days

insert into settings(key, value) values ('organization_name', 'CVS Health Care Systems');

insert into services(name, description, owner_team_id, criticality) values
  ('Oracle ERP Cloud',         'Finance and ERP',          (select id from teams where name = 'Development'), 'High'),
  ('HCM Cloud',                'HR technology',            (select id from teams where name = 'Development'), 'High'),
  ('Procurement Integrations', 'Supply chain interfaces',  (select id from teams where name = 'Development'), 'High'),
  ('Corporate IT',             'Laptops, VPN, accounts',   (select id from teams where name = 'Support'),     'High'),
  ('Identity & Access',        'Logins and permissions',   (select id from teams where name = 'Support'),     'High');
